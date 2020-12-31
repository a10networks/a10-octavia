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


import copy
import imp
try:
    from unittest import mock
except ImportError:
    import mock
from oslo_config import cfg
from oslo_config import fixture as oslo_fixture

from octavia.common import constants as o_constants
from octavia.common import data_models as o_data_models
from octavia.common import exceptions

from a10_octavia.common import config_options
from a10_octavia.common import data_models
import a10_octavia.controller.worker.tasks.service_group_tasks as task
from a10_octavia.controller.worker.tasks import utils
from a10_octavia.tests.common import a10constants
from a10_octavia.tests.unit.base import BaseTaskTestCase

VTHUNDER = data_models.VThunder()
POOL = o_data_models.Pool(id=a10constants.MOCK_POOL_ID, name="sg1")
AXAPI_ARGS = {'service_group': utils.meta(POOL, 'service_group', {})}


class TestHandlerServiceGroupTasks(BaseTaskTestCase):

    def setUp(self):
        super(TestHandlerServiceGroupTasks, self).setUp()
        imp.reload(task)
        self.client_mock = mock.Mock()
        self.conf = self.useFixture(oslo_fixture.Config(cfg.CONF))
        self.conf.register_opts(config_options.A10_SERVICE_GROUP_OPTS,
                                group=a10constants.SERVICE_GROUP_CONF_SECTION)
        self.conf.register_opts(config_options.A10_GLOBAL_OPTS,
                                group=a10constants.A10_GLOBAL_CONF_SECTION)

    def tearDown(self):
        super(TestHandlerServiceGroupTasks, self).tearDown()
        self.conf.reset()

    def _create_service_group_task_with_template(self, config_template, use_shared=False):
        service_group_task = task.PoolCreate()
        service_group_task.axapi_client = self.client_mock
        self.conf.config(group=a10constants.A10_GLOBAL_CONF_SECTION,
                         use_shared_for_template_lookup=use_shared)
        self.conf.config(group=a10constants.SERVICE_GROUP_CONF_SECTION, **config_template)
        service_group_task.CONF = self.conf
        return service_group_task

    @mock.patch('a10_octavia.common.openstack_mappings.service_group_protocol', mock.Mock())
    @mock.patch('a10_octavia.common.openstack_mappings.service_group_lb_method', mock.Mock())
    def test_PoolCreate_execute_create_with_server_template(self, ):
        service_group_task = self._create_service_group_task_with_template(
            {'template_server': 'my_server_template'})
        service_group_task.execute(POOL, VTHUNDER)
        args, kwargs = self.client_mock.slb.service_group.create.call_args
        self.assertIn('template-server', kwargs['service_group_templates'])
        self.assertEqual(kwargs['service_group_templates']['template-server'], 'my_server_template')

    @mock.patch('a10_octavia.common.openstack_mappings.service_group_protocol', mock.Mock())
    @mock.patch('a10_octavia.common.openstack_mappings.service_group_lb_method', mock.Mock())
    def test_PoolCreate_execute_create_with_shared_server_template_log_warning(self):
        service_group_task = self._create_service_group_task_with_template(
            {'template_server': 'my_server_template'}, use_shared=True)

        task_path = "a10_octavia.controller.worker.tasks.service_group_tasks"
        log_message = str("Shared partition template lookup for `[service_group]` "
                          "is not supported on template `template-server`")
        expected_log = ["WARNING:{}:{}".format(task_path, log_message)]
        with self.assertLogs(task_path, level='WARN') as cm:
            service_group_task.execute(POOL, VTHUNDER)
            self.assertEqual(expected_log, cm.output)

    @mock.patch('a10_octavia.common.openstack_mappings.service_group_protocol', mock.Mock())
    @mock.patch('a10_octavia.common.openstack_mappings.service_group_lb_method', mock.Mock())
    def test_PoolCreate_execute_create_with_port_template(self):
        service_group_task = self._create_service_group_task_with_template(
            {'template_port': 'my_port_template'})
        service_group_task.execute(POOL, VTHUNDER)
        args, kwargs = self.client_mock.slb.service_group.create.call_args
        self.assertIn('template-port', kwargs['service_group_templates'])
        self.assertEqual(kwargs['service_group_templates']['template-port'], 'my_port_template')

    @mock.patch('a10_octavia.common.openstack_mappings.service_group_protocol', mock.Mock())
    @mock.patch('a10_octavia.common.openstack_mappings.service_group_lb_method', mock.Mock())
    def test_PoolCreate_execute_create_with_shared_port_template_log_warning(self):
        service_group_task = self._create_service_group_task_with_template(
            {'template_port': 'my_server_template'}, use_shared=True)

        task_path = "a10_octavia.controller.worker.tasks.service_group_tasks"
        log_message = str("Shared partition template lookup for `[service_group]` "
                          "is not supported on template `template-port`")
        expected_log = ["WARNING:{}:{}".format(task_path, log_message)]
        with self.assertLogs(task_path, level='WARN') as cm:
            service_group_task.execute(POOL, VTHUNDER)
            self.assertEqual(expected_log, cm.output)

    @mock.patch('a10_octavia.common.openstack_mappings.service_group_protocol', mock.Mock())
    @mock.patch('a10_octavia.common.openstack_mappings.service_group_lb_method', mock.Mock())
    def test_PoolCreate_execute_create_with_l3v_local_policy_template(self):
        vthunder = copy.deepcopy(VTHUNDER)
        vthunder.partition_name = "my_partition"
        service_group_task = self._create_service_group_task_with_template(
            {'template_policy': 'my_policy_template'})
        self.conf.config(group=a10constants.A10_GLOBAL_CONF_SECTION,
                         use_shared_for_template_lookup=True)
        device_templates = {"template": {
            "policy-list": [{
                "policy": {"name": "my_policy_template"}
            }]
        }
        }
        service_group_task.axapi_client.slb.template.templates.get.return_value = device_templates
        service_group_task.execute(POOL, vthunder)
        args, kwargs = self.client_mock.slb.service_group.create.call_args
        self.assertIn('template-policy-shared', kwargs['service_group_templates'])
        self.assertEqual(kwargs['service_group_templates']
                         ['template-policy-shared'], 'my_policy_template')

    @mock.patch('a10_octavia.common.openstack_mappings.service_group_protocol', mock.Mock())
    @mock.patch('a10_octavia.common.openstack_mappings.service_group_lb_method', mock.Mock())
    def test_PoolCreate_execute_create_with_shared_policy_template(self):
        vthunder = copy.deepcopy(VTHUNDER)
        vthunder.partition_name = "shared"
        service_group_task = self._create_service_group_task_with_template(
            {'template_policy': 'my_policy_template_other'})
        self.conf.config(group=a10constants.A10_GLOBAL_CONF_SECTION,
                         use_shared_for_template_lookup=True)
        device_templates = {"template": {
            "policy-list": [{
                "policy": {"name": "my_policy_template"}
            }]
        }
        }
        service_group_task.axapi_client.slb.template.templates.get.return_value = device_templates
        service_group_task.execute(POOL, vthunder)
        args, kwargs = self.client_mock.slb.service_group.create.call_args
        self.assertIn('template-policy', kwargs['service_group_templates'])
        self.assertEqual(kwargs['service_group_templates']
                         ['template-policy'], 'my_policy_template_other')

    @mock.patch('a10_octavia.common.openstack_mappings.service_group_protocol', mock.Mock())
    @mock.patch('a10_octavia.common.openstack_mappings.service_group_lb_method', mock.Mock())
    def test_PoolCreate_execute_create_with_flavor(self):
        vthunder = copy.deepcopy(VTHUNDER)
        service_group_task = task.PoolCreate()
        service_group_task.axapi_client = self.client_mock
        flavor = {"service_group": {"health_check_disable": 1}}
        expect_kwargs = {"health_check_disable": 1}
        service_group_task.execute(POOL, vthunder, flavor=flavor)
        args, kwargs = self.client_mock.slb.service_group.create.call_args
        self.assertEqual(kwargs['service_group'], expect_kwargs)

    @mock.patch('a10_octavia.common.openstack_mappings.service_group_protocol', mock.Mock())
    @mock.patch('a10_octavia.common.openstack_mappings.service_group_lb_method', mock.Mock())
    def test_PoolCreate_execute_create_with_flavor_over_conf(self):
        vthunder = copy.deepcopy(VTHUNDER)
        service_group_task = task.PoolCreate()
        service_group_task.axapi_client = self.client_mock
        conf = {'template_server': 'my_server_template'}
        self.conf.config(group=a10constants.SERVICE_GROUP_CONF_SECTION, **conf)
        flavor = {"service_group": {"template_server": 'tmpl1'}}
        expect_kwargs = {"template_server": 'tmpl1'}
        service_group_task.execute(POOL, vthunder, flavor=flavor)
        args, kwargs = self.client_mock.slb.service_group.create.call_args
        self.assertEqual(kwargs['service_group'], expect_kwargs)

    @mock.patch('a10_octavia.common.openstack_mappings.service_group_protocol', mock.Mock())
    @mock.patch('a10_octavia.common.openstack_mappings.service_group_lb_method', mock.Mock())
    def test_PoolCreate_execute_create_with_flavor_regex(self):
        vthunder = copy.deepcopy(VTHUNDER)
        service_group_task = task.PoolCreate()
        service_group_task.axapi_client = self.client_mock
        flavor = {}
        regex = {"name_expressions": [{"regex": "sg1", "json": {"health_check_disable": 1}}]}
        flavor["service_group"] = regex
        expect_kwargs = {"health_check_disable": 1}
        service_group_task.execute(POOL, vthunder, flavor=flavor)
        args, kwargs = self.client_mock.slb.service_group.create.call_args
        self.assertEqual(kwargs['service_group'], expect_kwargs)

    @mock.patch('a10_octavia.common.openstack_mappings.service_group_protocol', mock.Mock())
    @mock.patch('a10_octavia.common.openstack_mappings.service_group_lb_method', mock.Mock())
    def test_PoolCreate_execute_create_with_regex_over_regex(self):
        vthunder = copy.deepcopy(VTHUNDER)
        service_group_task = task.PoolCreate()
        service_group_task.axapi_client = self.client_mock
        flavor = {"service_group": {"health_check_disable": 0}}
        regex = {"name_expressions": [{"regex": "sg1", "json": {"health_check_disable": 1}}]}
        flavor["service_group"] = regex
        expect_kwargs = {"health_check_disable": 1}
        service_group_task.execute(POOL, vthunder, flavor=flavor)
        args, kwargs = self.client_mock.slb.service_group.create.call_args
        self.assertEqual(kwargs['service_group'], expect_kwargs)

    def test_revert_pool_create_task(self):
        mock_pool = task.PoolCreate()
        mock_pool.axapi_client = self.client_mock
        mock_pool.revert(POOL, VTHUNDER)
        self.client_mock.slb.service_group.delete.assert_called_with(POOL.id)

    def test_create_lb_algorithm_source_ip_hash_only(self):
        mock_pool = task.PoolCreate()
        mock_pool.axapi_client = self.client_mock
        mock_pool.CONF = self.conf
        pool = o_data_models.Pool(id=a10constants.MOCK_POOL_ID,
                                  protocol=o_constants.PROTOCOL_HTTP,
                                  lb_algorithm=o_constants.LB_ALGORITHM_SOURCE_IP)
        mock_pool.execute(pool, VTHUNDER)
        self.client_mock.slb.service_group.create.assert_called_with(
            a10constants.MOCK_POOL_ID,
            protocol=mock.ANY,
            lb_method=mock_pool.axapi_client.slb.service_group.SOURCE_IP_HASH_ONLY,
            service_group_templates=mock.ANY,
            hm_name=None,
            mem_list=None,
            **AXAPI_ARGS)

    def test_create_pool_with_protocol_proxy(self):
        mock_pool = task.PoolCreate()
        mock_pool.axapi_client = self.client_mock
        mock_pool.CONF = self.conf
        pool = o_data_models.Pool(id=a10constants.MOCK_POOL_ID,
                                  protocol=o_constants.PROTOCOL_PROXY,
                                  lb_algorithm=o_constants.LB_ALGORITHM_SOURCE_IP)
        self.assertRaises(exceptions.ProviderUnsupportedOptionError, mock_pool.execute, pool,
                          VTHUNDER)
