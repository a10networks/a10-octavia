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
from oslo_config import cfg
from oslo_config import fixture as oslo_fixture

from a10_octavia.common import config_options
from a10_octavia.common import data_models
import a10_octavia.controller.worker.tasks.server_tasks as task
from a10_octavia.tests.common import a10constants
from a10_octavia.tests.unit import base

VTHUNDER = data_models.VThunder()
POOL = o_data_models.Pool(id=a10constants.MOCK_POOL_ID)
MEMBER = o_data_models.Member(
    id=a10constants.MOCK_MEMBER_ID, protocol_port=t_constants.MOCK_PORT_ID)


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

    def _create_member_task_with_server_template(self, template_name, use_shared=False):
        member_task = task.MemberCreate()
        member_task.axapi_client = self.client_mock
        self.conf.config(group=a10constants.A10_GLOBAL_CONF_SECTION, use_shared_for_template_lookup=use_shared)
        self.conf.config(group=a10constants.SERVER_CONF_SECTION, template_server=template_name)
        member_task.CONF = self.conf
        return member_task

    def test_MemberCreate_execute_create_with_server_template(self):
        member_task = self._create_member_task_with_server_template('my_server_template')
        member_task.execute(MEMBER, VTHUNDER, POOL)
        args, kwargs = self.client_mock.slb.server.create.call_args
        self.assertIn('template-server', kwargs['server_templates'])
        self.assertEqual(kwargs['server_templates']['template-server'], 'my_server_template')
        
    def test_MemberCreate_execute_create_with_shared_template_log_warning(self):
        member_task = self._create_member_task_with_server_template('my_server_template', use_shared=True)

        task_path = "a10_octavia.controller.worker.tasks.server_tasks"
        log_message = str("Shared partition template lookup for `[server]` "
                          "is not supported on template `template-server`")
        expected_log = ["WARNING:{}:{}".format(task_path, log_message)]
        with self.assertLogs(task_path, level='WARN') as cm:
            member_task.execute(MEMBER, VTHUNDER, POOL)

    def test_MemberCreate_revert_created_member(self):
        mock_member = task.MemberCreate()
        mock_member.axapi_client = self.client_mock
        mock_member.revert(MEMBER, VTHUNDER, POOL)
        self.client_mock.slb.server.delete.assert_called_with(
            MEMBER.id)
