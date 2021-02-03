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
import json
try:
    from unittest import mock
except ImportError:
    import mock

from oslo_config import cfg
from oslo_config import fixture as oslo_fixture

from octavia.common import data_models as o_data_models
from octavia.network import data_models as n_data_models
from octavia.network.drivers.neutron import utils

from acos_client import errors as acos_errors

from a10_octavia.common import config_options
from a10_octavia.common import data_models as a10_data_models
from a10_octavia.common import exceptions
from a10_octavia.common import utils as a10_utils
from a10_octavia.controller.worker.tasks import vthunder_tasks as task
from a10_octavia.network.drivers.neutron import a10_octavia_neutron
from a10_octavia.tests.common import a10constants
from a10_octavia.tests.unit import base

PROJECT_ID = "project-rack-vthunder"
VTHUNDER = a10_data_models.VThunder(project_id=PROJECT_ID)
VLAN_ID = '11'
VE_IP_VLAN_ID = '12'
DELETE_VLAN = True
TAG_INTERFACE = '5'
TAG_TRUNK_INTERFACE = '1'
ETH_DATA = {"action": "enable"}
SUBNET_MASK = ["10.0.11.0", "255.255.255.0", "10.0.11.0/24"]
VE_IP_SUBNET_MASK = ["10.0.12.0", "255.255.255.0", "10.0.12.0/24"]
ETHERNET_INTERFACE = {
    "interface_num": 5,
    "vlan_map": [
        {"vlan_id": 11, "use_dhcp": "True"},
        {"vlan_id": 12, "ve_ip": ".10"}
    ]
}
TRUNK_INTERFACE = {
    "interface_num": 1,
    "vlan_map": [
        {"vlan_id": 12, "ve_ip": ".10"}
    ]
}
DEVICE1_MGMT_IP = "10.0.0.1"
DEVICE2_MGMT_IP = "10.0.0.2"
RACK_DEVICE = {
    "project_id": PROJECT_ID,
    "ip_address": "10.0.0.10",
    "device_name": "rack_vthunder",
    "username": "abc",
    "password": "abc",
    "interface_vlan_map": {
        "device_1": {
            "vcs_device_id": 1,
            "mgmt_ip_address": DEVICE1_MGMT_IP,
            "trunk_interfaces": [TRUNK_INTERFACE]
        }
    }
}
RACK_DEVICE_VCS = {
    "project_id": PROJECT_ID,
    "ip_address": "10.0.0.10",
    "device_name": "rack_vthunder",
    "username": "abc",
    "password": "abc",
    "interface_vlan_map": {
        "device_1": {
            "vcs_device_id": 1,
            "mgmt_ip_address": DEVICE1_MGMT_IP,
            "ethernet_interfaces": [ETHERNET_INTERFACE]
        },
        "device_2": {
            "vcs_device_id": 2,
            "mgmt_ip_address": DEVICE2_MGMT_IP,
            "ethernet_interfaces": [ETHERNET_INTERFACE]
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
VCS_DISABLED = {"vcs-summary": {"oper": {"vcs-enabled": "Invalid"}}}
VCS_MASTER_VBLADE = {
    "vcs-summary": {
        "oper": {
            "vcs-enabled": "Yes",
            "member-list": [{
                "port": 41216, "priority": 125, "state": "vMaster(*)",
                "ip-list": [{"ip": "10.0.0.1"}], "location": "Local", "id": 1
            }, {
                "port": 41216, "priority": 120, "state": "vBlade",
                "ip-list": [{"ip": "10.0.0.2"}], "location": "Remote", "id": 2
            }]
        }
    }
}
VCS_DEVICE1_FAILED = {
    "vcs-summary": {
        "oper": {
            "vcs-enabled": "Yes",
            "member-list": [{
                "port": 41216, "priority": 120, "state": "Unknown",
                "ip-list": [{"ip": "N/A"}], "location": "Remote", "id": 1
            }, {
                "port": 41216, "priority": 125, "state": "vMaster(*)",
                "ip-list": [{"ip": "10.0.0.2"}], "location": "Local", "id": 2
            }]
        }
    }
}

LB = o_data_models.LoadBalancer(id=a10constants.MOCK_LOAD_BALANCER_ID)


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
        intf = a10_utils.convert_interface_to_data_model(ETHERNET_INTERFACE)
        device1_network_map = a10_data_models.DeviceNetworkMap(vcs_device_id=1,
                                                               ethernet_interfaces=[intf])
        mock_thunder = copy.deepcopy(VTHUNDER)
        mock_thunder.device_network_map = [device1_network_map]
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
        mock_task.execute(lb, mock_thunder)
        self.client_mock.vlan.create.assert_called_with(VLAN_ID,
                                                        tagged_eths=[TAG_INTERFACE],
                                                        veth=True)
        args, kwargs = mock_task._network_driver.neutron_client.create_port.call_args
        self.assertIn('port', args[0])
        port = args[0]['port']
        fixed_ip = port['fixed_ips'][0]
        self.assertEqual(VE_IP, fixed_ip['ip_address'])

    def test_TagInterfaceForLB_create_ethernet_vlan_ve_with_static_ip(self):
        intf = a10_utils.convert_interface_to_data_model(ETHERNET_INTERFACE)
        device1_network_map = a10_data_models.DeviceNetworkMap(vcs_device_id=1,
                                                               ethernet_interfaces=[intf])
        mock_thunder = copy.deepcopy(VTHUNDER)
        mock_thunder.device_network_map = [device1_network_map]
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
        mock_task.execute(lb, mock_thunder)
        self.client_mock.vlan.create.assert_called_with(VE_IP_VLAN_ID,
                                                        tagged_eths=[TAG_INTERFACE],
                                                        veth=True)
        self.client_mock.interface.ve.create.assert_called_with(VE_IP_VLAN_ID,
                                                                ip_address=STATIC_VE_IP,
                                                                ip_netmask="255.255.255.0",
                                                                enable=True)

    def test_TagInterfaceForLB_create_trunk_vlan_ve_with_static_ip(self):
        intf = a10_utils.convert_interface_to_data_model(TRUNK_INTERFACE)
        device1_network_map = a10_data_models.DeviceNetworkMap(vcs_device_id=1,
                                                               trunk_interfaces=[intf])
        mock_thunder = copy.deepcopy(VTHUNDER)
        mock_thunder.device_network_map = [device1_network_map]
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
        mock_task.execute(lb, mock_thunder)
        self.client_mock.vlan.create.assert_called_with(VE_IP_VLAN_ID,
                                                        tagged_trunks=[TAG_TRUNK_INTERFACE],
                                                        veth=True)
        self.client_mock.interface.ve.create.assert_called_with(VE_IP_VLAN_ID,
                                                                ip_address=STATIC_VE_IP,
                                                                ip_netmask="255.255.255.0",
                                                                enable=True)

    def test_TagInterfaceForLB_create_vlan_ve_with_axapi_exception(self):
        intf = a10_utils.convert_interface_to_data_model(ETHERNET_INTERFACE)
        device1_network_map = a10_data_models.DeviceNetworkMap(vcs_device_id=1,
                                                               ethernet_interfaces=[intf])
        mock_thunder = copy.deepcopy(VTHUNDER)
        mock_thunder.device_network_map = [device1_network_map]
        lb = self._mock_lb()
        mock_task = task.TagInterfaceForLB()
        self._mock_tag_task(mock_task)
        self.client_mock.interface.ethernet.get.return_value = ETH_DATA
        self.client_mock.vlan.exists.side_effect = Exception
        self.assertRaises(Exception, lambda: mock_task.execute(lb, mock_thunder))

    def test_TagInterfaceForLB_revert_created_vlan(self):
        intf = a10_utils.convert_interface_to_data_model(ETHERNET_INTERFACE)
        device1_network_map = a10_data_models.DeviceNetworkMap(vcs_device_id=1,
                                                               ethernet_interfaces=[intf])
        mock_thunder = copy.deepcopy(VTHUNDER)
        mock_thunder.device_network_map = [device1_network_map]
        lb = self._mock_lb()
        mock_task = task.TagInterfaceForLB()
        self._mock_tag_task(mock_task)
        mock_task.axapi_client.slb.virtual_server.get.return_value = DEL_VS_LIST
        mock_task.axapi_client.slb.server.get.return_value = DEL_SERVER_LIST
        mock_task._network_driver.get_port_id_from_ip = mock.Mock()
        mock_task._network_driver.neutron_client.delete_port = mock.Mock()
        mock_task._network_driver.get_port_id_from_ip.return_value = DEL_PORT_ID
        mock_task.revert(lb, mock_thunder)
        self.client_mock.vlan.delete.assert_called_with(VLAN_ID)
        mock_task._network_driver.neutron_client.delete_port.assert_called_with(DEL_PORT_ID)

    def test_TagInterfaceForMember_create_vlan_ve_with_dhcp(self):
        intf = a10_utils.convert_interface_to_data_model(ETHERNET_INTERFACE)
        device1_network_map = a10_data_models.DeviceNetworkMap(vcs_device_id=1,
                                                               ethernet_interfaces=[intf])
        mock_thunder = copy.deepcopy(VTHUNDER)
        mock_thunder.device_network_map = [device1_network_map]
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
        mock_task.execute(member, mock_thunder)
        self.client_mock.vlan.create.assert_called_with(VLAN_ID,
                                                        tagged_eths=[TAG_INTERFACE],
                                                        veth=True)
        args, kwargs = mock_task._network_driver.neutron_client.create_port.call_args
        self.assertIn('port', args[0])
        port = args[0]['port']
        fixed_ip = port['fixed_ips'][0]
        self.assertEqual(VE_IP, fixed_ip['ip_address'])

    def test_TagInterfaceForMember_create_vlan_ve_with_neutron_exception(self):
        intf = a10_utils.convert_interface_to_data_model(ETHERNET_INTERFACE)
        device1_network_map = a10_data_models.DeviceNetworkMap(vcs_device_id=1,
                                                               ethernet_interfaces=[intf])
        mock_thunder = copy.deepcopy(VTHUNDER)
        mock_thunder.device_network_map = [device1_network_map]
        member = self._mock_member()
        mock_task = task.TagInterfaceForMember()
        self._mock_tag_task(mock_task)
        self.client_mock.interface.ethernet.get.return_value = ETH_DATA
        self.client_mock.vlan.exists.return_value = False
        mock_task._network_driver.neutron_client.create_port = mock.Mock()
        mock_task._network_driver.neutron_client.create_port.side_effect = Exception
        self.assertRaises(Exception, lambda: mock_task.execute(member, mock_thunder))

    def test_TagInterfaceForMember_revert_created_vlan(self):
        intf = a10_utils.convert_interface_to_data_model(ETHERNET_INTERFACE)
        device1_network_map = a10_data_models.DeviceNetworkMap(vcs_device_id=1,
                                                               ethernet_interfaces=[intf])
        mock_thunder = copy.deepcopy(VTHUNDER)
        mock_thunder.device_network_map = [device1_network_map]
        member = self._mock_member()
        mock_task = task.TagInterfaceForMember()
        self._mock_tag_task(mock_task)
        mock_task.axapi_client.slb.virtual_server.get.return_value = DEL_VS_LIST
        mock_task.axapi_client.slb.server.get.return_value = DEL_SERVER_LIST
        mock_task._network_driver.get_port_id_from_ip = mock.Mock()
        mock_task._network_driver.neutron_client.delete_port = mock.Mock()
        mock_task._network_driver.get_port_id_from_ip.return_value = DEL_PORT_ID
        mock_task.revert(member, mock_thunder)
        self.client_mock.vlan.delete.assert_called_with(VLAN_ID)
        mock_task._network_driver.neutron_client.delete_port.assert_called_with(DEL_PORT_ID)

    def test_TagInterfaceForMember_execute_log_warning_no_subnet_id(self):
        member = self._mock_member()
        member.id = "1234"
        member.subnet_id = None
        task_path = "a10_octavia.controller.worker.tasks.vthunder_tasks"
        log_message = str("Subnet id argument was not specified during "
                          "issuance of create command/API call for member %s. "
                          "Skipping TagInterfaceForMember task")
        expected_log = ["WARNING:{}:{}".format(task_path, log_message % member.id)]
        mock_task = task.TagInterfaceForMember()
        with self.assertLogs(task_path, level='WARN') as cm:
            mock_task.execute(member, VTHUNDER)
            self.assertEqual(expected_log, cm.output)

    def test_TagInterfaceForMember_revert_log_warning_no_subnet_id(self):
        member = self._mock_member()
        member.id = "1234"
        member.subnet_id = None
        task_path = "a10_octavia.controller.worker.tasks.vthunder_tasks"
        log_message = str("Subnet id argument was not specified during "
                          "issuance of create command/API call for member %s. "
                          "Skipping TagInterfaceForMember task")
        expected_log = ["WARNING:{}:{}".format(task_path, log_message % member.id)]
        mock_task = task.TagInterfaceForMember()
        with self.assertLogs(task_path, level='WARN') as cm:
            mock_task.revert(member, VTHUNDER)
            self.assertEqual(expected_log, cm.output)

    def test_DeleteInterfaceTagIfNotInUseForMember_execute_log_warning_no_subnet_id(self):
        member = self._mock_member()
        member.id = "1234"
        member.subnet_id = None
        task_path = "a10_octavia.controller.worker.tasks.vthunder_tasks"
        log_message = str("Subnet id argument was not specified during "
                          "issuance of create command/API call for member %s. "
                          "Skipping DeleteInterfaceTagIfNotInUseForMember task")
        expected_log = ["WARNING:{}:{}".format(task_path, log_message % member.id)]
        mock_task = task.DeleteInterfaceTagIfNotInUseForMember()
        with self.assertLogs(task_path, level='WARN') as cm:
            mock_task.execute(member, VTHUNDER)
            self.assertEqual(expected_log, cm.output)

    def test_DeleteInterfaceTagIfNotInUseForLB_execute_delete_vlan(self):
        intf = a10_utils.convert_interface_to_data_model(ETHERNET_INTERFACE)
        device1_network_map = a10_data_models.DeviceNetworkMap(vcs_device_id=1,
                                                               ethernet_interfaces=[intf])
        mock_thunder = copy.deepcopy(VTHUNDER)
        mock_thunder.device_network_map = [device1_network_map]
        lb = self._mock_lb()
        mock_task = task.DeleteInterfaceTagIfNotInUseForLB()
        self._mock_tag_task(mock_task)
        mock_task.axapi_client.slb.virtual_server.get.return_value = DEL_VS_LIST
        mock_task.axapi_client.slb.server.get.return_value = DEL_SERVER_LIST
        mock_task._network_driver.get_port_id_from_ip = mock.Mock()
        mock_task._network_driver.neutron_client.delete_port = mock.Mock()
        mock_task._network_driver.get_port_id_from_ip.return_value = DEL_PORT_ID
        mock_task.execute(lb, mock_thunder)
        self.client_mock.vlan.delete.assert_called_with(VLAN_ID)
        mock_task._network_driver.neutron_client.delete_port.assert_called_with(DEL_PORT_ID)

    def test_DeleteInterfaceTagIfNotInUseForMember_execute_delete_vlan(self):
        intf = a10_utils.convert_interface_to_data_model(ETHERNET_INTERFACE)
        device1_network_map = a10_data_models.DeviceNetworkMap(vcs_device_id=1,
                                                               ethernet_interfaces=[intf])
        mock_thunder = copy.deepcopy(VTHUNDER)
        mock_thunder.device_network_map = [device1_network_map]
        member = self._mock_member()
        mock_task = task.DeleteInterfaceTagIfNotInUseForMember()
        self._mock_tag_task(mock_task)
        mock_task.axapi_client.slb.virtual_server.get.return_value = DEL_VS_LIST
        mock_task.axapi_client.slb.server.get.return_value = DEL_SERVER_LIST
        mock_task._network_driver.get_port_id_from_ip = mock.Mock()
        mock_task._network_driver.neutron_client.delete_port = mock.Mock()
        mock_task._network_driver.get_port_id_from_ip.return_value = DEL_PORT_ID
        mock_task.execute(member, mock_thunder)
        self.client_mock.vlan.delete.assert_called_with(VLAN_ID)
        mock_task._network_driver.neutron_client.delete_port.assert_called_with(DEL_PORT_ID)

    def test_SetupDeviceNetworkMap_execute_vcs_disabled(self):
        self.conf.register_opts(config_options.A10_HARDWARE_THUNDER_OPTS,
                                group=a10constants.A10_HARDWARE_THUNDER_CONF_SECTION)
        devices_str = json.dumps([RACK_DEVICE])
        self.conf.config(group=a10constants.A10_HARDWARE_THUNDER_CONF_SECTION,
                         devices=devices_str)
        mock_task = task.SetupDeviceNetworkMap()
        self._mock_tag_task(mock_task)
        mock_task.axapi_client.system.action.get_vcs_summary_oper.return_value = VCS_DISABLED
        mock_thunder = copy.deepcopy(VTHUNDER)
        thunder = mock_task.execute(mock_thunder)
        self.assertEqual(len(thunder.device_network_map), 1)
        self.assertEqual(thunder.device_network_map[0].vcs_device_id, 1)

    def test_SetupDeviceNetworkMap_execute_vcs_master_vblade(self):
        self.conf.register_opts(config_options.A10_HARDWARE_THUNDER_OPTS,
                                group=a10constants.A10_HARDWARE_THUNDER_CONF_SECTION)

        devices_str = json.dumps([RACK_DEVICE_VCS])
        self.conf.config(group=a10constants.A10_HARDWARE_THUNDER_CONF_SECTION,
                         devices=devices_str)
        mock_task = task.SetupDeviceNetworkMap()
        self._mock_tag_task(mock_task)
        mock_task.axapi_client.system.action.get_vcs_summary_oper.return_value = VCS_MASTER_VBLADE
        mock_thunder = copy.deepcopy(VTHUNDER)
        thunder = mock_task.execute(mock_thunder)
        self.assertEqual(len(thunder.device_network_map), 2)
        self.assertEqual(thunder.device_network_map[0].vcs_device_id, 1)
        self.assertEqual(thunder.device_network_map[0].state, "Master")
        self.assertEqual(thunder.device_network_map[0].mgmt_ip_address, DEVICE1_MGMT_IP)
        self.assertEqual(thunder.device_network_map[1].vcs_device_id, 2)
        self.assertEqual(thunder.device_network_map[1].state, "vBlade")
        self.assertEqual(thunder.device_network_map[1].mgmt_ip_address, DEVICE2_MGMT_IP)

    def test_SetupDeviceNetworkMap_execute_vcs_device1_failed(self):
        self.conf.register_opts(config_options.A10_HARDWARE_THUNDER_OPTS,
                                group=a10constants.A10_HARDWARE_THUNDER_CONF_SECTION)
        devices_str = json.dumps([RACK_DEVICE_VCS])
        self.conf.config(group=a10constants.A10_HARDWARE_THUNDER_CONF_SECTION,
                         devices=devices_str)
        mock_task = task.SetupDeviceNetworkMap()
        self._mock_tag_task(mock_task)
        mock_task.axapi_client.system.action.get_vcs_summary_oper.return_value = VCS_DEVICE1_FAILED
        mock_thunder = copy.deepcopy(VTHUNDER)
        thunder = mock_task.execute(mock_thunder)
        self.assertEqual(len(thunder.device_network_map), 1)
        self.assertEqual(thunder.device_network_map[0].vcs_device_id, 2)
        self.assertEqual(thunder.device_network_map[0].state, "Master")
        self.assertEqual(thunder.device_network_map[0].mgmt_ip_address, DEVICE2_MGMT_IP)

    def test_SetupDeviceNetworkMap_execute_delete_flow_after_error_no_fail(self):
        ret_val = task.SetupDeviceNetworkMap().execute(vthunder=None)
        self.assertIsNone(ret_val)

    def test_WriteMemory_execute_save_shared_mem(self):
        self.conf.register_opts(config_options.A10_HOUSE_KEEPING_OPTS,
                                group=a10constants.A10_HOUSE_KEEPING)
        self.conf.config(group=a10constants.A10_HOUSE_KEEPING,
                         use_periodic_write_memory='disable')
        mock_thunder = copy.deepcopy(VTHUNDER)
        mock_task = task.WriteMemory()
        mock_task.axapi_client = self.client_mock
        mock_task.execute(mock_thunder)
        self.client_mock.system.action.write_memory.assert_called_with(partition='shared')

    def test_WriteMemory_execute_save_specific_partition_mem(self):
        self.conf.register_opts(config_options.A10_HOUSE_KEEPING_OPTS,
                                group=a10constants.A10_HOUSE_KEEPING)
        self.conf.config(group=a10constants.A10_HOUSE_KEEPING,
                         use_periodic_write_memory='disable')
        thunder = copy.deepcopy(VTHUNDER)
        thunder.partition_name = "testPartition"
        mock_task = task.WriteMemory()
        mock_task.axapi_client = self.client_mock
        mock_task.execute(thunder)
        self.client_mock.system.action.write_memory.assert_called_with(
            partition='specified',
            specified_partition='testPartition')

    def test_WriteMemoryHouseKeeper_execute_save_shared_mem(self):
        mock_thunder = copy.deepcopy(VTHUNDER)
        mock_thunder.loadbalancer_id = a10constants.MOCK_LOAD_BALANCER_ID
        lb_list = []
        lb_list.append(LB)
        mock_task = task.WriteMemoryHouseKeeper()
        mock_task.axapi_client = self.client_mock
        mock_task.execute(mock_thunder, lb_list, True)
        self.client_mock.system.action.write_memory.assert_called_with(partition='shared')

    def test_WriteMemoryHouseKeeper_execute_save_specific_partition_mem(self):
        thunder = copy.deepcopy(VTHUNDER)
        thunder.loadbalancer_id = a10constants.MOCK_LOAD_BALANCER_ID
        lb_list = []
        lb_list.append(LB)
        thunder.partition_name = "testPartition"
        mock_task = task.WriteMemoryHouseKeeper()
        mock_task.axapi_client = self.client_mock
        mock_task.execute(thunder, lb_list)
        self.client_mock.system.action.write_memory.assert_called_with(
            partition='specified',
            specified_partition='testPartition')

    def test_WriteMemory_execute_not_called(self):
        self.conf.register_opts(config_options.A10_HOUSE_KEEPING_OPTS,
                                group=a10constants.A10_HOUSE_KEEPING)
        self.conf.config(group=a10constants.A10_HOUSE_KEEPING,
                         use_periodic_write_memory='enable')
        mock_thunder = copy.deepcopy(VTHUNDER)
        mock_task = task.WriteMemory()
        mock_task.axapi_client = self.client_mock
        mock_task.execute(mock_thunder)
        self.client_mock.system.action.write_memory.assert_not_called()

    def test_WriteMemory_execute_delete_flow_after_error_no_fail(self):
        self.conf.register_opts(config_options.A10_HOUSE_KEEPING_OPTS,
                                group=a10constants.A10_HOUSE_KEEPING)
        self.conf.config(group=a10constants.A10_HOUSE_KEEPING,
                         use_periodic_write_memory='enable')
        ret_val = task.WriteMemory().execute(vthunder=None)
        self.assertIsNone(ret_val)

    @mock.patch('a10_octavia.controller.worker.tasks.vthunder_tasks.a10_utils')
    def test_HandleACOSPartitionChange_execute_create_partition(self, mock_utils):
        mock_client = mock.Mock()
        mock_client.system.partition.get.side_effect = acos_errors.NotFound()
        mock_utils.get_axapi_client.return_value = mock_client
        mock_thunder = copy.deepcopy(VTHUNDER)
        mock_thunder.partition_name = "PartitionA"
        task.HandleACOSPartitionChange().execute(mock_thunder)
        mock_client.system.partition.create.assert_called_with("PartitionA")

    @mock.patch('a10_octavia.controller.worker.tasks.vthunder_tasks.a10_utils')
    def test_HandleACOSPartitionChange_execute_create_partition_fail(self, mock_utils):
        mock_client = mock.Mock()
        mock_client.system.partition.get.side_effect = acos_errors.NotFound()
        mock_client.system.action.write_memory.side_effect = acos_errors.ACOSException()
        mock_utils.get_axapi_client.return_value = mock_client
        mock_thunder = copy.deepcopy(VTHUNDER)
        mock_thunder.partition_name = "PartitionA"
        expected_error = acos_errors.ACOSException
        task_function = task.HandleACOSPartitionChange().execute
        self.assertRaises(expected_error, task_function, mock_thunder)

    @mock.patch('a10_octavia.controller.worker.tasks.vthunder_tasks.a10_utils')
    def test_HandleACOSPartitionChange_execute_partition_found_active(self, mock_utils):
        partition = {'status': 'Active'}
        mock_client = mock.Mock()
        mock_client.system.partition.get.return_value = partition
        mock_utils.get_axapi_client.return_value = mock_client
        mock_thunder = copy.deepcopy(VTHUNDER)
        mock_thunder.partition_name = "PartitionA"
        task.HandleACOSPartitionChange().execute(mock_thunder)
        mock_client.system.partition.create.assert_not_called()

    @mock.patch('a10_octavia.controller.worker.tasks.vthunder_tasks.a10_utils')
    def test_HandleACOSPartitionChange_execute_partition_found_not_active(self, mock_utils):
        partition = {'status': 'Not-Active'}
        mock_client = mock.Mock()
        mock_client.system.partition.get.return_value = partition
        mock_utils.get_axapi_client.return_value = mock_client
        mock_thunder = copy.deepcopy(VTHUNDER)
        mock_thunder.partition_name = "PartitionA"
        expected_error = exceptions.PartitionNotActiveError
        task_function = task.HandleACOSPartitionChange().execute
        self.assertRaises(expected_error, task_function, mock_thunder)
