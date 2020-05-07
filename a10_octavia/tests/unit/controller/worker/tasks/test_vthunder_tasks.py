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
import json
try:
    from unittest import mock
except ImportError:
    import mock

from oslo_config import cfg
from oslo_config import fixture as oslo_fixture

from a10_octavia.common import config_options
from a10_octavia.common import data_models as a10_data_models
from a10_octavia.controller.worker.tasks import vthunder_tasks as task
from a10_octavia.tests.common import a10constants
from a10_octavia.tests.unit import base

VTHUNDER = a10_data_models.VThunder()
VLAN_ID = 11
DELETE_VLAN = True
TAG_INTERFACE = 5
ETH_DATA = {"action": "enable"}
SUBNET_MASK = ("10.0.1.0", "255.255.255.0")
RACK_DEVICE = {
    "project_id": "project-rack-vthunder",
    "ip_address": "10.0.0.1",
    "device_name": "rack_vthunder",
    "username": "abc",
    "password": "abc",
    "interface_vlan_map": {"5": {"11": {"use_dhcp": "True"}, "12": {"use_dhcp": "True"}}}
}
VS_LIST = {"virtual-server-list": [{"ip-address": "10.0.2.1"}]}
SERVER_LIST = {"server-list": [{"host": "10.0.3.1"}]}


class TestVThunderTasks(base.BaseTaskTestCase):

    def setUp(self):
        super(TestVThunderTasks, self).setUp()
        self.conf = self.useFixture(oslo_fixture.Config(cfg.CONF))
        imp.reload(task)
        self.client_mock = mock.Mock()

    def tearDown(self):
        super(TestVThunderTasks, self).tearDown()
        self.conf.reset()

    def _mock_lb(self):
        lb = mock.Mock()
        lb.id = a10constants.MOCK_LOAD_BALANCER_ID
        lb.project_id = "project-rack-vthunder"
        lb.vip.subnet_id = "mock-subnet-1"
        return lb

    def _mock_member(self):
        member = mock.Mock()
        member.id = a10constants.MOCK_MEMBER_ID
        member.project_id = "project-rack-vthunder"
        member.subnet_id = "mock-subnet-1"
        return member

    def test_tag_ethernet_for_lb(self):
        self.conf.register_opts(config_options.A10_RACK_VTHUNDER_OPTS,
                                group=a10constants.A10_RACK_VTHUNDER_CONF_SECTION)
        devices_str = json.dumps([RACK_DEVICE])
        self.conf.config(group=a10constants.A10_RACK_VTHUNDER_CONF_SECTION,
                         devices=devices_str)
        lb = self._mock_lb()
        tag_ethernet = task.TagEthernetForLB()
        tag_ethernet.axapi_client = self.client_mock
        tag_ethernet.get_vlan_id = mock.Mock()
        tag_ethernet.get_vlan_id.return_value = VLAN_ID
        self.client_mock.interface.ethernet.get.return_value = ETH_DATA
        self.client_mock.vlan.exists.return_value = False
        tag_ethernet.execute(lb, VTHUNDER)
        self.client_mock.vlan.create.assert_called_with(VLAN_ID,
                                                        tagged_eths=[TAG_INTERFACE],
                                                        veth=True)

    def test_revert_tag_ethernet_for_lb(self):
        lb = self._mock_lb()
        tag_ethernet = task.TagEthernetForLB()
        tag_ethernet.axapi_client = self.client_mock
        tag_ethernet.get_vlan_id = mock.Mock()
        tag_ethernet.get_vlan_id.return_value = VLAN_ID
        tag_ethernet.revert(lb, VTHUNDER)
        self.client_mock.vlan.delete.assert_called_with(VLAN_ID)

    def test_tag_ethernet_for_member(self):
        self.conf.register_opts(config_options.A10_RACK_VTHUNDER_OPTS,
                                group=a10constants.A10_RACK_VTHUNDER_CONF_SECTION)
        devices_str = json.dumps([RACK_DEVICE])
        self.conf.config(group=a10constants.A10_RACK_VTHUNDER_CONF_SECTION,
                         devices=devices_str)
        member = self._mock_member()
        tag_ethernet = task.TagEthernetForMember()
        tag_ethernet.axapi_client = self.client_mock
        tag_ethernet.get_vlan_id = mock.Mock()
        tag_ethernet.get_vlan_id.return_value = VLAN_ID
        self.client_mock.interface.ethernet.get.return_value = ETH_DATA
        self.client_mock.vlan.exists.return_value = False
        tag_ethernet.execute(member, VTHUNDER)
        self.client_mock.vlan.create.assert_called_with(VLAN_ID,
                                                        tagged_eths=[TAG_INTERFACE],
                                                        veth=True)

    def test_revert_tag_ethernet_for_member(self):
        member = self._mock_member()
        tag_ethernet = task.TagEthernetForMember()
        tag_ethernet.axapi_client = self.client_mock
        tag_ethernet.get_vlan_id = mock.Mock()
        tag_ethernet.get_vlan_id.return_value = VLAN_ID
        tag_ethernet.revert(member, VTHUNDER)
        self.client_mock.vlan.delete.assert_called_with(VLAN_ID)

    def test_delete_ethernet_tag_if_not_in_use_for_lb(self):
        self.conf.register_opts(config_options.A10_RACK_VTHUNDER_OPTS,
                                group=a10constants.A10_RACK_VTHUNDER_CONF_SECTION)
        devices_str = json.dumps([RACK_DEVICE])
        self.conf.config(group=a10constants.A10_RACK_VTHUNDER_CONF_SECTION,
                         devices=devices_str)
        lb = self._mock_lb()
        untag_ethernet = task.DeleteEthernetTagIfNotInUseForLB()
        untag_ethernet.axapi_client = self.client_mock
        untag_ethernet.get_vlan_id = mock.Mock()
        untag_ethernet.get_subnet_and_mask = mock.Mock()
        untag_ethernet.is_vlan_deletable = mock.Mock()
        untag_ethernet.get_vlan_id.return_value = VLAN_ID
        untag_ethernet.get_subnet_and_mask.return_value = SUBNET_MASK
        untag_ethernet.is_vlan_deletable.return_value = True
        untag_ethernet.axapi_client.slb.virtual_server.get.return_value = VS_LIST
        untag_ethernet.axapi_client.slb.server.get.return_value = SERVER_LIST
        untag_ethernet.execute(lb, VTHUNDER)
        self.client_mock.vlan.delete.assert_called_with(VLAN_ID)

    def test_delete_ethernet_tag_if_not_in_use_for_member(self):
        self.conf.register_opts(config_options.A10_RACK_VTHUNDER_OPTS,
                                group=a10constants.A10_RACK_VTHUNDER_CONF_SECTION)
        devices_str = json.dumps([RACK_DEVICE])
        self.conf.config(group=a10constants.A10_RACK_VTHUNDER_CONF_SECTION,
                         devices=devices_str)
        member = self._mock_member()
        untag_ethernet = task.DeleteEthernetTagIfNotInUseForMember()
        untag_ethernet.axapi_client = self.client_mock
        untag_ethernet.get_vlan_id = mock.Mock()
        untag_ethernet.get_subnet_and_mask = mock.Mock()
        untag_ethernet.is_vlan_deletable = mock.Mock()
        untag_ethernet.get_vlan_id.return_value = VLAN_ID
        untag_ethernet.get_subnet_and_mask.return_value = SUBNET_MASK
        untag_ethernet.is_vlan_deletable.return_value = True
        untag_ethernet.axapi_client.slb.virtual_server.get.return_value = VS_LIST
        untag_ethernet.axapi_client.slb.server.get.return_value = SERVER_LIST
        untag_ethernet.execute(member, VTHUNDER)
        self.client_mock.vlan.delete.assert_called_with(VLAN_ID)
