#    Copyright 2020, A10 Networks
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import mock
import uuid
from a10_octavia.controller.worker.tasks.virtual_server_tasks import CreateVirtualServerTask, DeleteVirtualServerTask
from a10_octavia.tests.test_base import TestBase

USERNAME = "user"
PASSWORD = "pass"


class TestCreateVirtualServerTask(TestBase):
    def setUp(self):
        super(TestCreateVirtualServerTask, self).setUp()
        self.lb_mock = mock.MagicMock()
        self.vthunder_mock = mock.MagicMock(username=USERNAME, password=PASSWORD)
        self.lb_id = str(uuid.uuid4())

    def test_revert_create_virtual_server_task(self):
        target = CreateVirtualServerTask()
        actual = target.execute(self.lb_id, self.lb_mock, self.vthunder_mock)
        self.assertEqual(self.lb_id, actual["loadbalancers"][0]["id"])
