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

from oslo_config import cfg
from oslo_config import fixture as oslo_fixture
from taskflow.patterns import linear_flow as flow

from octavia.tests.unit import base

from a10_octavia.common import config_options
from a10_octavia.controller.worker.flows import a10_member_flows
from a10_octavia.tests.common import a10constants


RACK_DEVICE = {
    "project_id": "project-rack-vthunder",
    "ip_address": "10.0.0.1",
    "device_name": "rack_vthunder",
    "username": "abc",
    "password": "abc",
    "interface_vlan_map": {"1": {"11": {"use_dhcp": True}, "12": {"use_dhcp": True}}}
}


class TestMemberFlows(base.TestCase):
    def setUp(self):
        super(TestMemberFlows, self).setUp()
        self.conf = self.useFixture(oslo_fixture.Config(cfg.CONF))
        self.flows = a10_member_flows.MemberFlows()

    def tearDown(self):
        super(TestMemberFlows, self).tearDown()
        self.conf.reset()

    def test_create_member_rack_vthunder_vlan_flow(self):
        self.conf.register_opts(config_options.A10_GLOBAL_OPTS,
                                group=a10constants.A10_GLOBAL_CONF_SECTION)
        self.conf.config(group=a10constants.A10_GLOBAL_CONF_SECTION, network_type='vlan')
        create_flow = self.flows.get_rack_vthunder_create_member_flow()
        self.assertIsInstance(create_flow, flow.Flow)

    def test_delete_member_rack_vthunder_vlan_flow(self):
        self.conf.register_opts(config_options.A10_GLOBAL_OPTS,
                                group=a10constants.A10_GLOBAL_CONF_SECTION)
        self.conf.register_opts(config_options.A10_HARDWARE_THUNDER_OPTS,
                                group=a10constants.A10_HARDWARE_THUNDER_CONF_SECTION)
        self.conf.config(group=a10constants.A10_GLOBAL_CONF_SECTION, network_type='vlan')
        self.conf.config(group=a10constants.A10_HARDWARE_THUNDER_CONF_SECTION,
                         devices=[RACK_DEVICE])
        del_flow = self.flows.get_delete_member_flow()
        self.assertIsInstance(del_flow, flow.Flow)
