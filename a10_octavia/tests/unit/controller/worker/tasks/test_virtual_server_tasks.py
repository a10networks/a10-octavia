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

from octavia.common import data_models as o_data_models
from octavia.tests.common import constants as t_constants
from oslo_config import cfg
from oslo_config import fixture as oslo_fixture

from a10_octavia.common import config_options
from a10_octavia.common.data_models import VThunder
import a10_octavia.controller.worker.tasks.virtual_server_tasks as task
from a10_octavia.tests.common import a10constants
from a10_octavia.tests.unit.base import BaseTaskTestCase

VTHUNDER = VThunder()
AMPHORA = o_data_models.Amphora(id=t_constants.MOCK_AMP_ID1)
VIP = o_data_models.Vip(ip_address="1.1.1.1")
LOADBALANCER = o_data_models.LoadBalancer(id=a10constants.MOCK_LOAD_BALANCER_ID,
                                          amphorae=[AMPHORA], vip=VIP)


class TestHandlerVirtualServerTasks(BaseTaskTestCase):

    def setUp(self):
        super(TestHandlerVirtualServerTasks, self).setUp()
        imp.reload(task)
        self.client_mock = mock.Mock()
        self.conf = self.useFixture(oslo_fixture.Config(cfg.CONF))
        self.conf.register_opts(config_options.A10_SLB_OPTS,
                                group=a10constants.SERVICE_GROUP_CONF_SECTION)
        self.conf.register_opts(config_options.A10_GLOBAL_OPTS,
                                group=a10constants.A10_GLOBAL_CONF_SECTION)

    def tearDown(self):
        super(TestHandlerVirtualServerTasks, self).tearDown()
        self.conf.reset()

    def test_CreateVirtualServerTask_revert(self):
        mock_load_balancer = task.CreateVirtualServerTask()
        mock_load_balancer.axapi_client = self.client_mock
        mock_load_balancer.revert(LOADBALANCER, VTHUNDER)
        self.client_mock.slb.virtual_server.delete.assert_called_with(LOADBALANCER.id)

    @mock.patch('a10_octavia.controller.worker.tasks.utils.parse_name_expressions',
                mock.MagicMock())
    def test_CreateVirtualServerTask_execute_create_with_flavor(self):
        flavor = {"virtual_server": {"arp_disable": 1}}

        vthunder = copy.deepcopy(VTHUNDER)
        virtual_server_task = task.CreateVirtualServerTask()
        virtual_server_task.axapi_client = self.client_mock
        virtual_server_task.execute(LOADBALANCER, vthunder, flavor_data=flavor)
        args, kwargs = self.client_mock.slb.virtual_server.create.call_args
        self.assertEqual(kwargs['virtual_server']['arp_disable'], 1)

    @mock.patch('a10_octavia.controller.worker.tasks.utils.parse_name_expressions',
                mock.MagicMock())
    def test_CreateVirtualServerTask_execute_flavor_override_config(self):
        self.conf.config(group=a10constants.VIRTUAL_SERVER_CONFIG_SECTION,
                         arp_disable=False)
        flavor = {"virtual_server": {"arp_disable": 1}}

        vthunder = copy.deepcopy(VTHUNDER)
        virtual_server_task = task.CreateVirtualServerTask()
        virtual_server_task.axapi_client = self.client_mock
        virtual_server_task.execute(LOADBALANCER, vthunder, flavor_data=flavor)
        args, kwargs = self.client_mock.slb.virtual_server.create.call_args
        self.assertEqual(kwargs['virtual_server']['arp_disable'], 1)

    @mock.patch('a10_octavia.controller.worker.tasks.utils.parse_name_expressions')
    def test_CreateVirtualServerTask_execute_create_with_flavor_regex(self, mock_name_expr):
        mock_name_expr.return_value = {"arp_disable": 0}

        vthunder = copy.deepcopy(VTHUNDER)
        virtual_server_task = task.CreateVirtualServerTask()
        virtual_server_task.axapi_client = self.client_mock
        virtual_server_task.execute(LOADBALANCER, vthunder, flavor_data={})
        args, kwargs = self.client_mock.slb.virtual_server.create.call_args
        self.assertEqual(kwargs['arp_disable'], 0)

    @mock.patch('a10_octavia.controller.worker.tasks.utils.parse_name_expressions')
    def test_CreateVirtualServerTask_execute_name_expr_override_flavor(self, mock_name_expr):
        flavor = {"virtual_server": {"arp_disable": 1}}
        mock_name_expr.return_value = {"arp_disable": 0}

        vthunder = copy.deepcopy(VTHUNDER)
        virtual_server_task = task.CreateVirtualServerTask()
        virtual_server_task.axapi_client = self.client_mock
        virtual_server_task.execute(LOADBALANCER, vthunder, flavor_data=flavor)
        args, kwargs = self.client_mock.slb.virtual_server.create.call_args
        self.assertEqual(kwargs['arp_disable'], 0)

    def test_UpdateVirtualServerTask_Unset(self):
        update_dict = {"name": None, "description": None}
        virtual_server = {'virtual-server': {'name': '90d925bc-e39b-4be4-8826-bbfb0fd49caa',
                                             'ip-address': '1.1.1.1', 'description': 'LB1',
                                             'enable-disable-action': 'enable',
                                             'redistribution-flagged': 0,
                                             'arp-disable': 0,
                                             'stats-data-action': 'stats-data-enable',
                                             'extended-stats': 0, 'disable-vip-adv': 0,
                                             'uuid': '75865ac4-ee59-11eb-9424-6742a21a08a9',
                                             'a10-url': '/axapi/v3/slb/virtual-server/123'}}
        config_args = {'arp_disable': False, 'port_list': None, 'vrid': 0, 'virtual_server': {},
                       'status': mock.ANY, 'description': None}
        mock_load_balancer = task.UpdateVirtualServerTask()
        mock_load_balancer.axapi_client = self.client_mock
        self.client_mock.slb.virtual_server.get.return_value = virtual_server
        mock_load_balancer.execute(LOADBALANCER, VTHUNDER, update_dict)
        self.client_mock.slb.virtual_server.replace.assert_called()
        args, kwargs = self.client_mock.slb.virtual_server.replace.call_args
        self.assertEqual(kwargs, config_args)
