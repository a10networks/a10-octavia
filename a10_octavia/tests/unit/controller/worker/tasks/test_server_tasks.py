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


import imp
try:
    from unittest import mock
except ImportError:
    import mock

from octavia.common import data_models as o_data_models
from octavia.tests.common import constants as t_constants

from a10_octavia.common.data_models import VThunder
import a10_octavia.controller.worker.tasks.server_tasks as task
from a10_octavia.tests.common import a10constants
from a10_octavia.tests.unit.base import BaseTaskTestCase

VTHUNDER = VThunder()
POOL = o_data_models.Pool(id=a10constants.MOCK_POOL_ID)
MEMBER = o_data_models.Member(
    id=a10constants.MOCK_MEMBER_ID, protocol_port=t_constants.MOCK_PORT_ID)


class TestHandlerServerTasks(BaseTaskTestCase):

    def setUp(self):
        super(TestHandlerServerTasks, self).setUp()
        imp.reload(task)
        self.client_mock = mock.Mock()

    def test_revert_member_create_task(self):
        mock_member = task.MemberCreate()
        mock_member.axapi_client = self.client_mock
        mock_member.revert(MEMBER, VTHUNDER, POOL)
        self.client_mock.slb.service_group.member.delete.assert_called_with(
            POOL.id, MEMBER.id, MEMBER.protocol_port)
        self.client_mock.slb.server.delete.assert_called_with(
            MEMBER.id)
