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

from oslo_config import cfg
from oslo_config import fixture as oslo_fixture

from octavia.common import data_models as o_data_models
from octavia.tests.common import constants as t_constants

from a10_octavia.common.config_options import A10_SERVER_OPTS
from a10_octavia.common.data_models import VThunder
import a10_octavia.controller.worker.tasks.server_tasks as task
from a10_octavia.controller.worker.tasks import utils
from a10_octavia.tests.common import a10constants
from a10_octavia.tests.unit.base import BaseTaskTestCase

VTHUNDER = VThunder()
POOL = o_data_models.Pool(id=a10constants.MOCK_POOL_ID, 
        protocol=a10constants.MOCK_SERVICE_GROUP_PROTOCOL)
MEMBER = o_data_models.Member(
    id=a10constants.MOCK_MEMBER_ID, protocol_port=t_constants.MOCK_PORT_ID,
    project_id=t_constants.MOCK_PROJECT_ID, ip_address=t_constants.MOCK_IP_ADDRESS)
AXAPI_ARGS = {'server': utils.meta(MEMBER, 'server', {'conn-resume': None, 'conn-limit': 64000000})}


class TestHandlerServerTasks(BaseTaskTestCase):

    def setUp(self):
        super(TestHandlerServerTasks, self).setUp()
        imp.reload(task)
        self.client_mock = mock.Mock()
        self.conf = self.useFixture(oslo_fixture.Config(cfg.CONF))
        self.conf.register_opts(A10_SERVER_OPTS,
                                group=a10constants.SERVER_CONF_SECTION)

    def tearDown(self):
        super(TestHandlerServerTasks, self).tearDown()
        self.conf.reset()

    def test_revert_member_create_task(self):
        mock_member = task.MemberCreate()
        mock_member.axapi_client = self.client_mock
        mock_member.revert(MEMBER, VTHUNDER, POOL, 1)
        self.client_mock.slb.server.delete.assert_called_with(
           'mock-_10_0_0_1')
       
    def test_create_member_task(self):
        mock_create_member = task.MemberCreate()
        mock_create_member.CONF = self.conf
        mock_create_member.axapi_client = self.client_mock
        mock_create_member.execute(MEMBER, VTHUNDER, POOL, 1)
        self.client_mock.slb.server.create.assert_called_with(
                'mock-_10_0_0_1', MEMBER.ip_address, status=mock.ANY, 
                server_templates=mock.ANY, axapi_args=AXAPI_ARGS)
        self.client_mock.slb.service_group.member.create.assert_called_with(
                POOL.id, 'mock-_10_0_0_1', MEMBER.protocol_port)

    def test_create_member_task_mult_port(self):
        mock_member = task.MemberCreate()
        mock_member.axapi_client = self.client_mock
        mock_member.revert(MEMBER, VTHUNDER, POOL, 4)
        self.client_mock.slb.server.delete.assert_not_called()

        

    def test_delete_member_task_single_no_port(self):
        mock_delete_member = task.MemberDelete()
        mock_delete_member.axapi_client = self.client_mock
        mock_delete_member.execute(MEMBER, VTHUNDER, POOL)
        self.client_mock.slb.service_group.member.delete.assert_called_with(
                POOL.id,'mock-_10_0_0_1', MEMBER.protocol_port)
        self.client_mock.slb.server.delete.assert_called_with('mock-_10_0_0_1')

    def test_delete_member_task_multi_port(self):
        mock_delete_member = task.MemberDelete()
        mock_delete_member.axapi_client = self.client_mock
        mock_delete_member.axapi_client.slb.service_group.TCP = 'tcp'
        mock_delete_member.execute(MEMBER, VTHUNDER, POOL, 2)
        self.client_mock.slb.service_group.member.delete.assert_called_with(
                POOL.id,'mock-_10_0_0_1', MEMBER.protocol_port)
        self.client_mock.slb.server.port.delete.assert_called_with(
                'mock-_10_0_0_1', MEMBER.protocol_port, 'tcp')
