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


class DockerAdapter(object):
    def app_name(self):
        raise NotImplementedError

    def run_command(self):
        raise NotImplementedError

    def after_run(self):
        pass

    def setup_command(self):
        raise NotImplementedError

    def port(self):
        raise NotImplementedError

    def environment(self, data_path):
        raise NotImplementedError
