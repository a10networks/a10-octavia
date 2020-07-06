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

from octavia.network import data_models as n_data_models
from octavia.network.drivers.neutron import utils

from a10_octavia.common import config_options
from a10_octavia.common import data_models as a10_data_models
from a10_octavia.controller.worker.tasks import vthunder_tasks as task
from a10_octavia.network.drivers.neutron import a10_octavia_neutron
from a10_octavia.tests.common import a10constants
from a10_octavia.tests.unit import base

VTHUNDER = a10_data_models.VThunder()
VLAN_ID = '11'
VE_IP_VLAN_ID = '12'
DELETE_VLAN = True
TAG_INTERFACE = '5'
TAG_TRUNK_INTERFACE = '1'
ETH_DATA = {"action": "enable"}
SUBNET_MASK = ["10.0.11.0", "255.255.255.0", "10.0.11.0/24"]
VE_IP_SUBNET_MASK = ["10.0.12.0", "255.255.255.0", "10.0.12.0/24"]
RACK_DEVICE = {
    "project_id": "project-rack-vthunder",
    "ip_address": "10.0.0.1",
    "device_name": "rack_vthunder",
    "username": "abc",
    "password": "abc",
    "interface_vlan_map": {
        "device_1": {
            "ethernet_interfaces": [{
                "interface_num": "5",
                "vlan_map": [
                    {"vlan_id": 11, "use_dhcp": "True"},
                    {"vlan_id": 12, "ve_ip": ".10"}
                ]
            }]
        }
    }
}
RACK_DEVICE_TRUNK_INTERFACE = {
    "project_id": "project-rack-vthunder",
    "ip_address": "10.0.0.1",
    "device_name": "rack_vthunder",
    "username": "abc",
    "password": "abc",
    "interface_vlan_map": {
        "device_1": {
            "trunk_interfaces": [{
                "interface_num": "1",
                "vlan_map": [
                    {"vlan_id": 12, "ve_ip": ".10"}
                ]
            }]
        }
    }
}
DEL_VS_LIST = {"virtual-server-list": [{"ip-address": "10.0.1.1"}]}
DEL_SERVER_LIST = {"server-list": [{"host": "10.0.2.1"}]}
DEL_PORT_ID = "mock-port-id"
VE_IP = "10.0.11.10"
STATIC_VE_IP = "10.0.12.10"
NETWORK_11 = n_data_models.Network(id="mock-network-1", subnets=["mock-subnet-1"],
                                   provider_segmentation_id=11)
NETWORK_12 = n_data_models.Network(id="mock-network-2", subnets=["mock-subnet-2"],
                                   provider_segmentation_id=12)


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

    @mock.patch('keystoneauth1.session.Session', mock.Mock())
    @mock.patch('neutronclient.client.SessionClient', mock.Mock())
    @mock.patch('neutronclient.v2_0.client.Client', mock.Mock())
    def _mock_tag_task(self, mock_task):
        mock_task.axapi_client = self.client_mock
        mock_task.get_vlan_id = mock.Mock()
        mock_task.get_vlan_id.return_value = VLAN_ID
        mock_task._get_ve_ip = mock.Mock()
        mock_task._get_ve_ip.return_value = VE_IP
        mock_task.get_subnet_and_mask = mock.Mock()
        mock_task.get_subnet_and_mask.return_value = [SUBNET_MASK[0], SUBNET_MASK[1]]
        mock_task._subnet_ip = SUBNET_MASK[0]
        mock_task._subnet_mask = SUBNET_MASK[1]
        mock_task._subnet = mock.Mock()
        mock_task._subnet.cidr = SUBNET_MASK[2]
        mock_task._subnet = mock.Mock()
        mock_task._subnet.id = mock.Mock()
        mock_task._subnet.network_id = "mock-network-1"
        mock_task._network_driver = a10_octavia_neutron.A10OctaviaNeutronDriver()

    def test_TagInterfaceForLB_create_vlan_ve_with_dhcp(self):
        self.conf.register_opts(config_options.A10_HARDWARE_THUNDER_OPTS,
                                group=a10constants.A10_HARDWARE_THUNDER_CONF_SECTION)
        devices_str = json.dumps([RACK_DEVICE])
        self.conf.config(group=a10constants.A10_HARDWARE_THUNDER_CONF_SECTION,
                         devices=devices_str)
        lb = self._mock_lb()
        mock_task = task.TagInterfaceForLB()
        self._mock_tag_task(mock_task)
        self.client_mock.interface.ethernet.get.return_value = ETH_DATA
        self.client_mock.vlan.exists.return_value = False
        mock_task._network_driver.neutron_client.create_port = mock.Mock()
        utils.convert_port_dict_to_model = mock.Mock()
        mock_task._network_driver.get_network = mock.Mock()
        mock_task._network_driver.get_network.return_value = NETWORK_11
        mock_task._network_driver.list_networks = mock.Mock()
        mock_task._network_driver.list_networks.return_value = [NETWORK_11]
        mock_task.execute(lb, VTHUNDER)
        self.client_mock.vlan.create.assert_called_with(VLAN_ID,
                                                        tagged_eths=[TAG_INTERFACE],
                                                        veth=True)
        args, kwargs = mock_task._network_driver.neutron_client.create_port.call_args
        self.assertIn('port', args[0])
        port = args[0]['port']
        fixed_ip = port['fixed_ips'][0]
        self.assertEqual(VE_IP, fixed_ip['ip_address'])

    def test_TagInterfaceForLB_create_ethernet_vlan_ve_with_static_ip(self):
        self.conf.register_opts(config_options.A10_HARDWARE_THUNDER_OPTS,
                                group=a10constants.A10_HARDWARE_THUNDER_CONF_SECTION)
        devices_str = json.dumps([RACK_DEVICE])
        self.conf.config(group=a10constants.A10_HARDWARE_THUNDER_CONF_SECTION,
                         devices=devices_str)
        lb = self._mock_lb()
        mock_task = task.TagInterfaceForLB()
        self._mock_tag_task(mock_task)
        mock_task.get_vlan_id.return_value = VE_IP_VLAN_ID
        mock_task._subnet_ip = VE_IP_SUBNET_MASK[0]
        mock_task._subnet_mask = VE_IP_SUBNET_MASK[1]
        mock_task._subnet.cidr = VE_IP_SUBNET_MASK[2]
        self.client_mock.interface.ethernet.get.return_value = ETH_DATA
        self.client_mock.vlan.exists.return_value = False
        mock_task._network_driver.neutron_client.create_port = mock.Mock()
        mock_task._network_driver.get_network = mock.Mock()
        mock_task._network_driver.get_network.return_value = NETWORK_12
        mock_task._network_driver.list_networks = mock.Mock()
        mock_task._network_driver.list_networks.return_value = [NETWORK_12]
        mock_task.execute(lb, VTHUNDER)
        self.client_mock.vlan.create.assert_called_with(VE_IP_VLAN_ID,
                                                        tagged_eths=[TAG_INTERFACE],
                                                        veth=True)
        self.client_mock.interface.ve.update.assert_called_with(VE_IP_VLAN_ID,
                                                                ip_address=STATIC_VE_IP,
                                                                ip_netmask="255.255.255.0",
                                                                enable=True)

    def test_TagInterfaceForLB_create_trunk_vlan_ve_with_static_ip(self):
        self.conf.register_opts(config_options.A10_HARDWARE_THUNDER_OPTS,
                                group=a10constants.A10_HARDWARE_THUNDER_CONF_SECTION)
        devices_str = json.dumps([RACK_DEVICE_TRUNK_INTERFACE])
        self.conf.config(group=a10constants.A10_HARDWARE_THUNDER_CONF_SECTION,
                         devices=devices_str)
        lb = self._mock_lb()
        mock_task = task.TagInterfaceForLB()
        self._mock_tag_task(mock_task)
        mock_task.get_vlan_id.return_value = VE_IP_VLAN_ID
        mock_task._subnet_ip = VE_IP_SUBNET_MASK[0]
        mock_task._subnet_mask = VE_IP_SUBNET_MASK[1]
        mock_task._subnet.cidr = VE_IP_SUBNET_MASK[2]
        self.client_mock.interface.ethernet.get.return_value = ETH_DATA
        self.client_mock.vlan.exists.return_value = False
        mock_task._network_driver.neutron_client.create_port = mock.Mock()
        mock_task._network_driver.get_network = mock.Mock()
        mock_task._network_driver.get_network.return_value = NETWORK_12
        mock_task._network_driver.list_networks = mock.Mock()
        mock_task._network_driver.list_networks.return_value = [NETWORK_12]
        mock_task.execute(lb, VTHUNDER)
        self.client_mock.vlan.create.assert_called_with(VE_IP_VLAN_ID,
                                                        tagged_trunks=[TAG_TRUNK_INTERFACE],
                                                        veth=True)
        self.client_mock.interface.ve.update.assert_called_with(VE_IP_VLAN_ID,
                                                                ip_address=STATIC_VE_IP,
                                                                ip_netmask="255.255.255.0",
                                                                enable=True)

    def test_TagInterfaceForLB_revert_created_vlan(self):
        lb = self._mock_lb()
        mock_task = task.TagInterfaceForLB()
        self._mock_tag_task(mock_task)
        mock_task.axapi_client.slb.virtual_server.get.return_value = DEL_VS_LIST
        mock_task.axapi_client.slb.server.get.return_value = DEL_SERVER_LIST
        mock_task._network_driver.get_port_id_from_ip = mock.Mock()
        mock_task._network_driver.neutron_client.delete_port = mock.Mock()
        mock_task._network_driver.get_port_id_from_ip.return_value = DEL_PORT_ID
        mock_task.revert(lb, VTHUNDER)
        self.client_mock.vlan.delete.assert_called_with(VLAN_ID)
        mock_task._network_driver.neutron_client.delete_port.assert_called_with(DEL_PORT_ID)

    def test_TagInterfaceForMember_create_vlan_ve_with_dhcp(self):
        self.conf.register_opts(config_options.A10_HARDWARE_THUNDER_OPTS,
                                group=a10constants.A10_HARDWARE_THUNDER_CONF_SECTION)
        devices_str = json.dumps([RACK_DEVICE])
        self.conf.config(group=a10constants.A10_HARDWARE_THUNDER_CONF_SECTION,
                         devices=devices_str)
        member = self._mock_member()
        mock_task = task.TagInterfaceForMember()
        self._mock_tag_task(mock_task)
        self.client_mock.interface.ethernet.get.return_value = ETH_DATA
        self.client_mock.vlan.exists.return_value = False
        mock_task._network_driver.neutron_client.create_port = mock.Mock()
        mock_task._network_driver.get_network = mock.Mock()
        mock_task._network_driver.get_network.return_value = NETWORK_11
        mock_task._network_driver.list_networks = mock.Mock()
        mock_task._network_driver.list_networks.return_value = [NETWORK_11]
        mock_task.execute(member, VTHUNDER)
        self.client_mock.vlan.create.assert_called_with(VLAN_ID,
                                                        tagged_eths=[TAG_INTERFACE],
                                                        veth=True)
        args, kwargs = mock_task._network_driver.neutron_client.create_port.call_args
        self.assertIn('port', args[0])
        port = args[0]['port']
        fixed_ip = port['fixed_ips'][0]
        self.assertEqual(VE_IP, fixed_ip['ip_address'])

    def test_TagInterfaceForMember_revert_created_vlan(self):
        member = self._mock_member()
        mock_task = task.TagInterfaceForMember()
        self._mock_tag_task(mock_task)
        mock_task.axapi_client.slb.virtual_server.get.return_value = DEL_VS_LIST
        mock_task.axapi_client.slb.server.get.return_value = DEL_SERVER_LIST
        mock_task._network_driver.get_port_id_from_ip = mock.Mock()
        mock_task._network_driver.neutron_client.delete_port = mock.Mock()
        mock_task._network_driver.get_port_id_from_ip.return_value = DEL_PORT_ID
        mock_task.revert(member, VTHUNDER)
        self.client_mock.vlan.delete.assert_called_with(VLAN_ID)
        mock_task._network_driver.neutron_client.delete_port.assert_called_with(DEL_PORT_ID)

    def test_DeleteInterfaceTagIfNotInUseForLB_execute_delete_vlan(self):
        self.conf.register_opts(config_options.A10_HARDWARE_THUNDER_OPTS,
                                group=a10constants.A10_HARDWARE_THUNDER_CONF_SECTION)
        devices_str = json.dumps([RACK_DEVICE])
        self.conf.config(group=a10constants.A10_HARDWARE_THUNDER_CONF_SECTION,
                         devices=devices_str)
        lb = self._mock_lb()
        mock_task = task.DeleteInterfaceTagIfNotInUseForLB()
        self._mock_tag_task(mock_task)
        mock_task.axapi_client.slb.virtual_server.get.return_value = DEL_VS_LIST
        mock_task.axapi_client.slb.server.get.return_value = DEL_SERVER_LIST
        mock_task._network_driver.get_port_id_from_ip = mock.Mock()
        mock_task._network_driver.neutron_client.delete_port = mock.Mock()
        mock_task._network_driver.get_port_id_from_ip.return_value = DEL_PORT_ID
        mock_task.execute(lb, VTHUNDER)
        self.client_mock.vlan.delete.assert_called_with(VLAN_ID)
        mock_task._network_driver.neutron_client.delete_port.assert_called_with(DEL_PORT_ID)

    def test_DeleteInterfaceTagIfNotInUseForMember_execute_delete_vlan(self):
        self.conf.register_opts(config_options.A10_HARDWARE_THUNDER_OPTS,
                                group=a10constants.A10_HARDWARE_THUNDER_CONF_SECTION)
        devices_str = json.dumps([RACK_DEVICE])
        self.conf.config(group=a10constants.A10_HARDWARE_THUNDER_CONF_SECTION,
                         devices=devices_str)
        member = self._mock_member()
        mock_task = task.DeleteInterfaceTagIfNotInUseForMember()
        self._mock_tag_task(mock_task)
        mock_task.axapi_client.slb.virtual_server.get.return_value = DEL_VS_LIST
        mock_task.axapi_client.slb.server.get.return_value = DEL_SERVER_LIST
        mock_task._network_driver.get_port_id_from_ip = mock.Mock()
        mock_task._network_driver.neutron_client.delete_port = mock.Mock()
        mock_task._network_driver.get_port_id_from_ip.return_value = DEL_PORT_ID
        mock_task.execute(member, VTHUNDER)
        self.client_mock.vlan.delete.assert_called_with(VLAN_ID)
        mock_task._network_driver.neutron_client.delete_port.assert_called_with(DEL_PORT_ID)
