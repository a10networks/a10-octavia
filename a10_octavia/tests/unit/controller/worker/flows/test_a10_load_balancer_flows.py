#    Copyright 2019, A10 Networks
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

try:
    from unittest import mock
except ImportError:
    import mock

from oslo_config import cfg
from oslo_config import fixture as oslo_fixture
from taskflow.patterns import linear_flow as flow

from octavia.common import constants
from octavia.common import data_models as o_data_models
from octavia.tests.unit import base

from a10_octavia.common import config_options
from a10_octavia.controller.worker.flows import a10_load_balancer_flows
from a10_octavia.tests.common import a10constants


RACK_DEVICE = {
    "project_id": "project-rack-vthunder",
    "ip_address": "10.0.0.1",
    "device_name": "rack_vthunder",
    "username": "abc",
    "password": "abc",
    "interface_vlan_map": {"1": {"11": {"use_dhcp": True}, "12": {"use_dhcp": True}}}
}


@mock.patch("octavia.controller.worker.tasks.database_tasks.UpdateAmphoraVIPData")
class TestLoadBalancerFlows(base.TestCase):
    def setUp(self):
        super(TestLoadBalancerFlows, self).setUp()
        self.conf = self.useFixture(oslo_fixture.Config(cfg.CONF))

        self.conf.config(
            group="controller_worker")
        #    amphora_driver='a10')
        self.conf.config(group="nova", enable_anti_affinity=False)
        self.flows = a10_load_balancer_flows.LoadBalancerFlows()

    def tearDown(self):
        super(TestLoadBalancerFlows, self).tearDown()
        self.conf.reset()

    def test_create_lb_flows(self, mock_net_driver):
        target = self.flows.get_create_load_balancer_flow(constants.TOPOLOGY_SINGLE)
        self.assertIsInstance(target, flow.Flow)
        self.assertIn("vthunder", target.provides)

    def test_create_lb_rack_vthunder_vlan_flow(self, mock_net_driver):
        self.conf.register_opts(config_options.A10_GLOBAL_OPTS,
                                group=a10constants.A10_GLOBAL_CONF_SECTION)
        self.conf.config(group=a10constants.A10_GLOBAL_CONF_SECTION, network_type='vlan')
        target = self.flows.get_create_rack_vthunder_load_balancer_flow(
            RACK_DEVICE, constants.TOPOLOGY_SINGLE)
        self.assertIsInstance(target, flow.Flow)

    def test_delete_lb_rack_vthunder_vlan_flow(self, mock_net_driver):
        self.conf.register_opts(config_options.A10_GLOBAL_OPTS,
                                group=a10constants.A10_GLOBAL_CONF_SECTION)
        self.conf.register_opts(config_options.A10_HARDWARE_THUNDER_OPTS,
                                group=a10constants.A10_HARDWARE_THUNDER_CONF_SECTION)
        self.conf.config(group=a10constants.A10_GLOBAL_CONF_SECTION, network_type='vlan')
        self.conf.config(group=a10constants.A10_HARDWARE_THUNDER_CONF_SECTION,
                         devices=[RACK_DEVICE])
        lb = o_data_models.LoadBalancer(id=a10constants.MOCK_LOAD_BALANCER_ID,
                                        project_id='project-rack-vthunder')
        (del_flow, store) = self.flows.get_delete_load_balancer_flow(lb, False)
        self.assertIsInstance(del_flow, flow.Flow)
