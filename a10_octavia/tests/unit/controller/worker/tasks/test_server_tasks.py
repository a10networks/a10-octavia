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

from a10_octavia.common import config_options
from a10_octavia.common import data_models
import a10_octavia.controller.worker.tasks.server_tasks as task
from a10_octavia.controller.worker.tasks import utils
from a10_octavia.tests.common import a10constants
from a10_octavia.tests.unit import base

VTHUNDER = data_models.VThunder()
POOL = o_data_models.Pool(id=a10constants.MOCK_POOL_ID,
                          protocol=a10constants.MOCK_SERVICE_GROUP_PROTOCOL)
MEMBER = o_data_models.Member(
    id=a10constants.MOCK_MEMBER_ID, protocol_port=t_constants.MOCK_PORT_ID,
    project_id=t_constants.MOCK_PROJECT_ID, ip_address=t_constants.MOCK_IP_ADDRESS,
    subnet_id=a10constants.MOCK_SUBNET_ID)

KEY_ARGS = {'server': utils.meta(MEMBER, 'server', {'conn_resume': None, 'conn_limit': 64000000})}
SERVER_NAME = '{}_{}'.format(MEMBER.project_id[:5],
                             MEMBER.ip_address.replace('.', '_'))


class TestHandlerServerTasks(base.BaseTaskTestCase):

    def setUp(self):
        super(TestHandlerServerTasks, self).setUp()
        imp.reload(task)
        self.client_mock = mock.Mock()
        self.conf = self.useFixture(oslo_fixture.Config(cfg.CONF))
        self.conf.register_opts(config_options.A10_SERVER_OPTS,
                                group=a10constants.SERVER_CONF_SECTION)
        self.conf.register_opts(config_options.A10_GLOBAL_OPTS,
                                group=a10constants.A10_GLOBAL_CONF_SECTION)

    def tearDown(self):
        super(TestHandlerServerTasks, self).tearDown()
        self.conf.reset()

    def _create_member_task_with_server_template(self, template_name, use_shared=False):
        member_task = task.MemberCreate()
        member_task.axapi_client = self.client_mock
        self.conf.config(group=a10constants.A10_GLOBAL_CONF_SECTION,
                         use_shared_for_template_lookup=use_shared)
        self.conf.config(group=a10constants.SERVER_CONF_SECTION, template_server=template_name)
        member_task.CONF = self.conf
        return member_task

    def test_MemberCreate_execute_create_with_server_template(self):
        member_port_count_ip = 1
        member_task = self._create_member_task_with_server_template('my_server_template')
        member_task.execute(MEMBER, VTHUNDER, POOL, member_port_count_ip)
        args, kwargs = self.client_mock.slb.server.create.call_args
        self.assertIn('template-server', kwargs['server_templates'])
        self.assertEqual(kwargs['server_templates']['template-server'], 'my_server_template')

    def test_MemberCreate_execute_create_with_shared_template_log_warning(self):
        member_port_count_ip = 1
        member_task = self._create_member_task_with_server_template(
            'my_server_template', use_shared=True)

        task_path = "a10_octavia.controller.worker.tasks.server_tasks"
        log_message = str("Shared partition template lookup for `[server]` "
                          "is not supported on template `template-server`")
        expected_log = ["WARNING:{}:{}".format(task_path, log_message)]
        with self.assertLogs(task_path, level='WARN') as cm:
            member_task.execute(MEMBER, VTHUNDER, POOL, member_port_count_ip)
            self.assertEqual(expected_log, cm.output)

    def test_MemberCreate_execute_create_with_flavor(self):
        mock_create_member = task.MemberCreate()
        member_port_count_ip = 1
        flavor = {"server": {"conn_limit": 65535, "conn_resume": 5000}}
        expect_key_args = {"server": {'conn_limit': 65535, 'conn_resume': 5000}}
        mock_create_member.CONF = self.conf
        mock_create_member.axapi_client = self.client_mock
        mock_create_member.execute(MEMBER, VTHUNDER, POOL,
                                   member_port_count_ip, flavor)
        self.client_mock.slb.server.create.assert_called_with(
            SERVER_NAME, MEMBER.ip_address, status=mock.ANY,
            server_templates=mock.ANY, **expect_key_args)

    def test_MemberCreate_execute_create_with_regex_overwrite_flavor(self):
        mock_create_member = task.MemberCreate()
        member_port_count_ip = 1
        flavor = {"server": {"conn_limit": 65535}}
        regex = {"name_expressions": [{"regex": "srv1", "json": {"conn_limit": 800}}]}
        flavor['server'] = regex
        expect_key_args = {"server": {'conn_limit': 800, 'conn_resume': None}}
        mock_create_member.CONF = self.conf
        member_obj = o_data_models.Member(
            id=a10constants.MOCK_MEMBER_ID, protocol_port=t_constants.MOCK_PORT_ID,
            project_id=t_constants.MOCK_PROJECT_ID, ip_address=t_constants.MOCK_IP_ADDRESS,
            name="srv1")
        mock_create_member.axapi_client = self.client_mock
        mock_create_member.execute(member_obj, VTHUNDER, POOL,
                                   member_port_count_ip, flavor)
        self.client_mock.slb.server.create.assert_called_with(
            SERVER_NAME, member_obj.ip_address, status=mock.ANY,
            server_templates=mock.ANY, **expect_key_args)

    def test_MemberCreate_execute_create_with_regex_flavor(self):
        mock_create_member = task.MemberCreate()
        member_port_count_ip = 1
        flavor = {}
        regex = {"name_expressions": [{"regex": "srv1", "json": {"conn_limit": 800}}]}
        flavor['server'] = regex
        expect_key_args = {"server": {'conn_limit': 800, 'conn_resume': None}}
        mock_create_member.CONF = self.conf
        member_obj = o_data_models.Member(
            id=a10constants.MOCK_MEMBER_ID, protocol_port=t_constants.MOCK_PORT_ID,
            project_id=t_constants.MOCK_PROJECT_ID, ip_address=t_constants.MOCK_IP_ADDRESS,
            name="srv1")
        mock_create_member.axapi_client = self.client_mock
        mock_create_member.execute(member_obj, VTHUNDER, POOL,
                                   member_port_count_ip, flavor)
        self.client_mock.slb.server.create.assert_called_with(
            SERVER_NAME, member_obj.ip_address, status=mock.ANY,
            server_templates=mock.ANY, **expect_key_args)

    def test_MemberCreate_execute_create_flavor_override_config(self):
        self.conf.config(group=a10constants.SERVER_CONF_SECTION, conn_resume=300)
        mock_create_member = task.MemberCreate()
        member_port_count_ip = 1
        flavor = {"server": {"conn_limit": 65535, "conn_resume": 5000}}
        expect_key_args = {"server": {'conn_limit': 65535, 'conn_resume': 5000}}
        mock_create_member.CONF = self.conf
        mock_create_member.axapi_client = self.client_mock
        mock_create_member.execute(MEMBER, VTHUNDER, POOL,
                                   member_port_count_ip, flavor)
        self.client_mock.slb.server.create.assert_called_with(
            SERVER_NAME, MEMBER.ip_address, status=mock.ANY,
            server_templates=mock.ANY, **expect_key_args)

    def test_MemberCreate_revert_created_member(self):
        mock_member = task.MemberCreate()
        member_port_count_ip = 1
        mock_member.axapi_client = self.client_mock
        mock_member.revert(MEMBER, VTHUNDER, POOL,
                           member_port_count_ip)
        self.client_mock.slb.server.delete.assert_called_with(
            SERVER_NAME)

    def test_create_member_task(self):
        mock_create_member = task.MemberCreate()
        member_port_count_ip = 1
        mock_create_member.CONF = self.conf
        mock_create_member.axapi_client = self.client_mock
        mock_create_member.execute(MEMBER, VTHUNDER, POOL,
                                   member_port_count_ip)
        self.client_mock.slb.server.create.assert_called_with(
            SERVER_NAME, MEMBER.ip_address, status=mock.ANY,
            server_templates=mock.ANY, **KEY_ARGS)
        self.client_mock.slb.service_group.member.create.assert_called_with(
            POOL.id, SERVER_NAME, MEMBER.protocol_port)

    def test_create_member_task_multi_port(self):
        mock_member = task.MemberCreate()
        mock_member.axapi_client = self.client_mock
        member_port_count_ip = 4
        mock_member.revert(MEMBER, VTHUNDER, POOL, member_port_count_ip)
        self.client_mock.slb.server.delete.assert_not_called()

    def test_delete_member_task_single_no_port(self):
        mock_delete_member = task.MemberDelete()
        mock_delete_member.axapi_client = self.client_mock
        mock_delete_member.execute(MEMBER, VTHUNDER, POOL, 0, 0)
        self.client_mock.slb.service_group.member.delete.assert_called_with(
            POOL.id, SERVER_NAME, MEMBER.protocol_port)
        self.client_mock.slb.server.delete.assert_called_with(SERVER_NAME)

    def test_delete_member_task_multi_port(self):
        member_port_count_ip = 2
        pool_protocol_tcp = 'tcp'
        mock_delete_member = task.MemberDelete()
        mock_delete_member.axapi_client = self.client_mock
        mock_delete_member.axapi_client.slb.service_group.TCP = \
            pool_protocol_tcp
        mock_delete_member.execute(MEMBER, VTHUNDER, POOL,
                                   member_port_count_ip, 0)
        self.client_mock.slb.service_group.member.delete.assert_called_with(
            POOL.id, SERVER_NAME, MEMBER.protocol_port)
        self.client_mock.slb.server.port.delete.assert_called_with(
            SERVER_NAME, MEMBER.protocol_port, pool_protocol_tcp)
