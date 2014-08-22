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
__author__ = 'fbernitt'

import json
import ssl

import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.poolmanager import PoolManager


class EnforceTLSv1Adapter(HTTPAdapter):
    def init_poolmanager(self, connections, maxsize, block=False):
        self.poolmanager = PoolManager(num_pools=connections, maxsize=maxsize,
                                       block=block, ssl_version=ssl.PROTOCOL_TLSv1)


class PixelatedHTTPError(IOError):
    """A HTTP error occurred."""

    def __init__(self, *args, **kwargs):
        """ Initializes HTTPError with optional `response` object. """
        self.status_code = kwargs.pop('status_code', None)
        super(IOError, self).__init__(*args, **kwargs)

    def __str__(self):
        return '%d: %s' % (self.status_code, self.message)


class PixelatedNotAvailableHTTPError(PixelatedHTTPError):
    pass


class PixelatedDispatcherClient(object):
    __slots__ = ('_hostname', '_port', '_base_url', '_cacert', '_scheme')

    def __init__(self, hostname, port, cacert=True, ssl=True):
        self._hostname = hostname
        self._port = port
        self._scheme = 'https' if ssl else 'http'
        self._base_url = '%s://%s:%s' % (self._scheme, hostname, port)
        self._cacert = cacert

    def _get(self, path):
        uri = '%s%s' % (self._base_url, path)
        s = requests.Session()
        s.mount('https://', EnforceTLSv1Adapter())
        r = s.get(uri, verify=self._cacert)
        self._raise_error_for_status(r.status_code, r.reason)
        return r.json()

    def _put(self, path, json_data=None):
        uri = '%s%s' % (self._base_url, path)
        if json_data:
            json_data = json.dumps(json_data)

        s = requests.Session()
        s.mount('https://', EnforceTLSv1Adapter())
        r = s.put(uri, data=json_data, headers={'Content-Type': 'application/json'}, verify=self._cacert)

        self._raise_error_for_status(r.status_code, r.reason)
        return r.json()

    def _post(self, path, json_data=None):
        uri = '%s%s' % (self._base_url, path)
        if json_data:
            json_data = json.dumps(json_data)

        s = requests.Session()
        s.mount('https://', EnforceTLSv1Adapter())
        r = s.post(uri, data=json_data, headers={'Content-Type': 'application/json'}, verify=self._cacert)

        self._raise_error_for_status(r.status_code, r.reason)

        return r.json() if r.content else None

    def _raise_error_for_status(self, status_code, reason):
        if 503 == status_code:
            raise PixelatedNotAvailableHTTPError(reason, status_code=503)
        if 400 <= status_code < 600:
            raise PixelatedHTTPError(reason, status_code=status_code)

    def list(self):
        return self._get('/agents').get('agents')

    def get_agent(self, name):
        return self._get('/agents/%s' % name)

    def get_agent_runtime(self, name):
        return self._get('/agents/%s/runtime' % name)

    def start(self, name):
        payload = {'state': 'running'}
        return self._put('/agents/%s/state' % name, json_data=payload)

    def stop(self, name):
        payload = {'state': 'stopped'}
        return self._put('/agents/%s/state' % name, json_data=payload)

    def agent_exists(self, name):
        try:
            self.get_agent(name)
            return True
        except PixelatedHTTPError:
            return False

    def authenticate(self, name, password):
        payload = {'password': password}
        self._post('/agents/%s/authenticate' % name, json_data=payload)

    def add(self, agent_name, password):
        payload = {
            'name': agent_name,
            'password': password
        }
        self._post('/agents', json_data=payload)

    def memory_usage(self):
        return self._get('/stats/memory_usage')