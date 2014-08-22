#
# Copyright 2014 ThoughtWorks Deutschland GmbH
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
import traceback
import sys

from tornado import web
from tornado.httpclient import AsyncHTTPClient
from tornado.httpserver import HTTPServer

from client.dispatcher_api_client import PixelatedHTTPError, PixelatedNotAvailableHTTPError
from common import logger

__author__ = 'fbernitt'

import os
import tornado.ioloop
import tornado.web
import tornado.escape
import time

from tornado import gen

COOKIE_NAME = 'pixelated_user'


class BaseHandler(tornado.web.RequestHandler):
    def get_current_user(self):
        cookie = self.get_secure_cookie(COOKIE_NAME)
        if cookie:
            return tornado.escape.json_decode(cookie)
        else:
            return None


class MainHandler(BaseHandler):
    __slots__ = '_client'

    def initialize(self, client):
        self._client = client

    @tornado.web.authenticated
    @tornado.web.asynchronous
    @gen.engine
    def get(self):
        runtime = self._client.get_agent_runtime(self.current_user)
        if runtime['state'] == 'running':
            port = runtime['port']
            self.forward(port, '127.0.0.1')
        else:
            logger.info('Starting agent for %s' % self.current_user)
            self._client.start(self.current_user)
            # wait til agent is running
            runtime = self._client.get_agent_runtime(self.current_user)
            max_wait_seconds = 3
            waited = 0
            while runtime['state'] != 'running' and waited < max_wait_seconds:
                yield gen.Task(tornado.ioloop.IOLoop.current().add_timeout, time.time() + 1)
                runtime = self._client.get_agent_runtime(self.current_user)
                waited += 1

            if runtime['state'] == 'running':
                port = runtime['port']
                self.forward(port, '127.0.0.1')
            else:
                logger.error('Failed to start agent for %s' % self.current_user)
                self.set_status(503)
                self.write("Could not connect to instance %s!\n" % self.current_user)
                self.finish()

    def handle_response(self, response):
        if response.error and not isinstance(response.error, tornado.httpclient.HTTPError):
            logger.error('Got error %s from user %s agent: %s' % (self.current_user, response.error))
            self.set_status(500)
            self.write("Internal server error:\n" + str(response.error))
            self.finish()
        else:
            self.set_status(response.code)
            for header in ("Date", "Cache-Control", "Server", "Content-Type", "Location"):
                v = response.headers.get(header)
                if v:
                    self.set_header(header, v)
            if response.body:
                self.write(response.body)
            self.finish()

    def forward(self, port=None, host=None):
        url = "%s://%s:%s%s" % (
            'http', host or "127.0.0.1", port or 80, self.request.uri)
        try:
            tornado.httpclient.AsyncHTTPClient().fetch(
                tornado.httpclient.HTTPRequest(
                    url=url,
                    method=self.request.method,
                    body=None if not self.request.body else self.request.body,
                    headers=self.request.headers,
                    follow_redirects=False,
                    request_timeout=1),
                self.handle_response)
        except tornado.httpclient.HTTPError, x:
            if hasattr(x, 'response') and x.response:
                self.handle_response(x.response)
        except e:
            logger.error('Error forwarding request %s: %s' % (url, e.message))
            self.set_status(500)
            self.write("Internal server error:\n" + ''.join(traceback.format_exception(*sys.exc_info())))
            self.finish()


class AuthLoginHandler(tornado.web.RequestHandler):
    def initialize(self, client):
        self._client = client

    def get(self):
        self.render('login.html')

    def post(self):

        username = self.get_argument("username", "")
        password = self.get_argument("password", "")

        try:
            agent = self._client.get_agent(username)

            # now authenticate with server...
            self._client.authenticate(username, password)
            self.set_current_user(username)
            self.redirect(u'/')
            logger.info('Successful login of user %s' % username)
        except PixelatedNotAvailableHTTPError:
            logger.error('Login attempt while service not available by user: %s' % username)
            self.redirect(u'/auth/login?error=%s' % tornado.escape.url_escape('Service currently not available'))
        except PixelatedHTTPError:
            logger.warn('Login attempt with invalid credentials by user %s' % username)
            self.redirect(u'/auth/login?error=%s' % tornado.escape.url_escape('Invalid credentials'))

    def set_current_user(self, username):
        if username:
            self.set_secure_cookie(COOKIE_NAME, tornado.escape.json_encode(username))
        else:
            self.clear_cookie(COOKIE_NAME)


class AuthLogoutHandler(tornado.web.RequestHandler):
    def get(self):
        logger.info('User %s logged out' % self.current_user)
        self.clear_cookie(COOKIE_NAME)
        self.write("You are now logged out")


class Dispatcher(object):
    __slots__ = ('_port', '_client', '_bindaddr', '_ioloop', '_certfile', '_keyfile', '_server')

    def __init__(self, dispatcher_client, bindaddr='127.0.0.1', port=8080, certfile=None, keyfile=None):
        self._port = port
        self._client = dispatcher_client
        self._bindaddr = bindaddr
        self._certfile = certfile
        self._keyfile = keyfile
        self._ioloop = None
        self._server = None

    def create_app(self):
        app = tornado.web.Application(
            [
                (r"/auth/login", AuthLoginHandler, dict(client=self._client)),
                (r"/auth/logout", AuthLogoutHandler),
                (r"/dispatcher_static/", web.StaticFileHandler),
                (r"/.*", MainHandler, dict(client=self._client))
            ],
            cookie_secret='quwoqwjladsfasdlfjqsdojqwojqofdlsfasofhqwo0qoqsflasdnfaslfjo0324rsd',
            login_url='/auth/login',
            template_path=os.path.join(os.path.dirname(__file__), '..', 'files', "templates"),
            static_path=os.path.join(os.path.dirname(__file__), '..', 'files', "static"),
            static_url_prefix='/dispatcher_static/',  # needs to be bound to a different prefix as agent uses static
            xsrf_cookies=True,
            debug=True)
        return app

    @property
    def ssl_options(self):
        if self._certfile:
            return {
                'certfile': os.path.join(self._certfile),
                'keyfile': os.path.join(self._keyfile),
            }
        else:
            return None

    def serve_forever(self):
        app = self.create_app()
        # app.listen(port=self._port, address=self._bindaddr, ssl_options=self.ssl_options)
        if self.ssl_options:
            logger.info('Using SSL certfile %s and keyfile %s' % (self.ssl_options['certfile'], self.ssl_options['keyfile']))
        else:
            logger.warn('No SSL configured!')
        logger.info('Listening on %s:%d' % (self._bindaddr, self._port))
        self._server = HTTPServer(app, ssl_options=self.ssl_options)
        self._server.listen(port=self._port, address=self._bindaddr)
        self._ioloop = tornado.ioloop.IOLoop.instance()
        self._ioloop.start()  # this is a blocking call, server has stopped on next line
        self._ioloop = None

    def shutdown(self):
        if self._ioloop:
            self._server.stop()
            self._ioloop.stop()
            logger.info('Stopped dispatcher')