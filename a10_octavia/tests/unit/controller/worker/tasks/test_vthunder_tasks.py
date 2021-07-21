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
VTHUNDER = a10_data_models.VThunder(
    project_id=PROJECT_ID, acos_version="5.2.1")
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
INTERFACES = {
    "interface": {
        "management": {
            "ip": {"dhcp": 1, "control-apps-use-mgmt-port": 0},
            "broadcast-rate-limit": {u'bcast-rate-limit-enable': 0},
            "flow-control": 0,
            "uuid": "6d4f3b4e-8beb-11eb-957b-fa163e54fddf",
            "a10-url": "/axapi/v3/interface/management"},
        "available-eth-list": {
            "uuid": "6d4f40c6-8beb-11eb-957b-fa163e54fddf",
            "a10-url": "/axapi/v3/interface/available-eth-list"},
        "brief": {
            "uuid": "6d4f42b0-8beb-11eb-957b-fa163e54fddf",
            "a10-url": "/axapi/v3/interface/brief"},
        "ethernet-list": [{
            "port-scan-detection": "disable",
            "uuid": "6d4f3fb8-8beb-11eb-957b-fa163e54fddf", "trap-source": 0,
            "ping-sweep-detection": "disable", "mtu": 1500, "ifnum": 1,
            "load-interval": 300, "a10-url": "/axapi/v3/interface/ethernet/1",
            "action": "disable", "virtual-wire": 0, "l3-vlan-fwd-disable": 0}],
        "a10-url": "/axapi/v3/interface",
        "common": {
            "uuid": "6d4f4224-8beb-11eb-957b-fa163e54fddf",
            "a10-url": "/axapi/v3/interface/common"}
    }
}

FLAVOR_DEV1 = a10_data_models.HardwareThunder(device_name="rack_thunder_1",
                                              undercloud=True, username="abc", password="abc",
                                              ip_address="10.10.10.10", partition_name="shared",
                                              device_name_as_key=True)
FLAVOR_DEV2 = a10_data_models.HardwareThunder(project_id="project-2", device_name="rack_thunder_2",
                                              undercloud=True, username="abc", password="abc",
                                              ip_address="10.10.10.10", partition_name="shared")
FLAVOR_DEV3 = a10_data_models.HardwareThunder(project_id="project-1", device_name="rack_thunder_1",
                                              undercloud=True, username="abc", password="abc",
                                              ip_address="10.10.10.10", partition_name="shared")
DEV_CONF_DICT = {'[dev]rack_thunder_1': FLAVOR_DEV1,
                 'project-1': FLAVOR_DEV3,
                 '[dev]rack_thunder_2': FLAVOR_DEV2,
                 'project-2': FLAVOR_DEV2}
DEV_FLAVOR = {'device_name': 'rack_thunder_1'}

VIP = o_data_models.Vip(ip_address="1.1.1.1")
AMPHORAE = [o_data_models.Amphora(id=a10constants.MOCK_AMPHORA_ID)]
LB = o_data_models.LoadBalancer(
    id=a10constants.MOCK_LOAD_BALANCER_ID, vip=VIP,
    amphorae=AMPHORAE, project_id=PROJECT_ID)
DEPLOYMENT_FLAVOR = {'deployment': {"dsr_type": "l2dsr_transparent"}}
SUBNET = n_data_models.Subnet()


class TestVThunderTasks(base.BaseTaskTestCase):

    def setUp(self):
        super(TestVThunderTasks, self).setUp()
        self.conf = self.useFixture(oslo_fixture.Config(cfg.CONF))
        self.conf.register_opts(config_options.A10_GLOBAL_OPTS,
                                group=a10constants.A10_GLOBAL_CONF_SECTION)
        imp.reload(task)
        self.client_mock = mock.Mock()
        self.db_session = mock.patch(
            'a10_octavia.controller.worker.tasks.a10_database_tasks.db_apis.get_session')
        self.db_session.start()

    def tearDown(self):
        super(TestVThunderTasks, self).tearDown()
        self.conf.reset()
        self.db_session.stop()

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
        mock_task.get_subnet_and_mask.return_value = [
            SUBNET_MASK[0], SUBNET_MASK[1]]
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
                                                        tagged_eths=[
                                                            TAG_INTERFACE],
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
                                                        tagged_eths=[
                                                            TAG_INTERFACE],
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
                                                        tagged_trunks=[
                                                            TAG_TRUNK_INTERFACE],
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
        self.assertRaises(
            Exception, lambda: mock_task.execute(lb, mock_thunder))

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
        mock_task._network_driver.neutron_client.delete_port.assert_called_with(
            DEL_PORT_ID)

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
                                                        tagged_eths=[
                                                            TAG_INTERFACE],
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
        self.assertRaises(
            Exception, lambda: mock_task.execute(member, mock_thunder))

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
        mock_task._network_driver.neutron_client.delete_port.assert_called_with(
            DEL_PORT_ID)

    def test_TagInterfaceForMember_execute_log_warning_no_subnet_id(self):
        member = self._mock_member()
        member.id = "1234"
        member.subnet_id = None
        task_path = "a10_octavia.controller.worker.tasks.vthunder_tasks"
        log_message = str("Subnet id argument was not specified during "
                          "issuance of create command/API call for member %s. "
                          "Skipping TagInterfaceForMember task")
        expected_log = ["WARNING:{}:{}".format(
            task_path, log_message % member.id)]
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
        expected_log = ["WARNING:{}:{}".format(
            task_path, log_message % member.id)]
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
        expected_log = ["WARNING:{}:{}".format(
            task_path, log_message % member.id)]
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
        mock_task._network_driver.neutron_client.delete_port.assert_called_with(
            DEL_PORT_ID)

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
        mock_task._network_driver.neutron_client.delete_port.assert_called_with(
            DEL_PORT_ID)

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
        self.assertEqual(
            thunder.device_network_map[0].mgmt_ip_address, DEVICE1_MGMT_IP)
        self.assertEqual(thunder.device_network_map[1].vcs_device_id, 2)
        self.assertEqual(thunder.device_network_map[1].state, "vBlade")
        self.assertEqual(
            thunder.device_network_map[1].mgmt_ip_address, DEVICE2_MGMT_IP)

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
        self.assertEqual(
            thunder.device_network_map[0].mgmt_ip_address, DEVICE2_MGMT_IP)

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
        self.client_mock.system.action.write_memory.assert_called_with(
            partition='shared')

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
        self.client_mock.system.action.write_memory.assert_called_with(
            partition='shared')

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
        mock_thunder_config = copy.deepcopy(VTHUNDER)
        mock_thunder_config.partition_name = "PartitionA"
        task.HandleACOSPartitionChange().execute(LB, mock_thunder_config)
        mock_client.system.partition.create.assert_called_with("PartitionA")

    @mock.patch('a10_octavia.controller.worker.tasks.vthunder_tasks.a10_utils')
    def test_HandleACOSPartitionChange_execute_create_partition_fail(self, mock_utils):
        mock_client = mock.Mock()
        mock_client.system.partition.get.side_effect = acos_errors.NotFound()
        mock_client.system.action.write_memory.side_effect = acos_errors.ACOSException()
        mock_utils.get_axapi_client.return_value = mock_client
        mock_thunder_config = copy.deepcopy(VTHUNDER)
        mock_thunder_config.partition_name = "PartitionA"
        expected_error = acos_errors.ACOSException
        task_function = task.HandleACOSPartitionChange().execute
        self.assertRaises(expected_error, task_function, LB, mock_thunder_config)

    @mock.patch('a10_octavia.controller.worker.tasks.vthunder_tasks.a10_utils')
    def test_HandleACOSPartitionChange_execute_partition_found_active(self, mock_utils):
        partition = {
            'partition-name': 'PartitionA',
            'status': 'Active'
        }
        mock_client = mock.Mock()
        mock_client.system.partition.get.return_value = partition
        mock_utils.get_axapi_client.return_value = mock_client
        mock_thunder_config = copy.deepcopy(VTHUNDER)
        mock_thunder_config.partition_name = "PartitionA"
        task.HandleACOSPartitionChange().execute(LB, mock_thunder_config)
        mock_client.system.partition.create.assert_not_called()

    @mock.patch('a10_octavia.controller.worker.tasks.vthunder_tasks.a10_utils')
    def test_HandleACOSPartitionChange_execute_partition_found_not_active(self, mock_utils):
        partition = {
            'partition-name': 'PartitionA',
            'status': 'Not-Active'
        }
        mock_client = mock.Mock()
        mock_client.system.partition.get.return_value = partition
        mock_utils.get_axapi_client.return_value = mock_client
        mock_thunder = copy.deepcopy(VTHUNDER)
        mock_thunder.partition_name = "PartitionA"
        expected_error = exceptions.PartitionNotActiveError
        task_function = task.HandleACOSPartitionChange().execute
        self.assertRaises(expected_error, task_function, LB, mock_thunder)

    @mock.patch('a10_octavia.common.utils.get_parent_project',
                return_value=None)
    def test_HandleACOSPartitionChange_parent_partition_not_exists(
            self, mock_parent_project_id):
        self.conf.config(
            group=a10constants.A10_GLOBAL_CONF_SECTION,
            use_parent_partition=True)
        mock_lb = copy.deepcopy(LB)
        mock_lb.project_id = a10constants.MOCK_CHILD_PROJECT_ID
        mock_thunder_config = copy.deepcopy(VTHUNDER)
        mock_thunder_config.hierarchical_multitenancy = "enable"
        expected_error = exceptions.ParentProjectNotFound
        task_function = task.HandleACOSPartitionChange().execute
        self.assertRaises(expected_error, task_function, mock_lb, mock_thunder_config)

    @mock.patch('a10_octavia.common.utils.get_parent_project',
                return_value=a10constants.MOCK_PARENT_PROJECT_ID)
    @mock.patch('a10_octavia.controller.worker.tasks.vthunder_tasks.a10_utils')
    def test_HandleACOSPartitionChange_parent_partition_exists(
            self, mock_utils, mock_parent_project_id):
        self.conf.config(
            group=a10constants.A10_GLOBAL_CONF_SECTION,
            use_parent_partition=True)

        partition = {
            'partition-name': a10constants.MOCK_PARENT_PROJECT_ID[:14],
            'status': 'Active'
        }
        mock_client = mock.Mock()
        mock_client.system.partition.get.return_value = partition
        mock_utils.get_axapi_client.return_value = mock_client

        mock_lb = copy.deepcopy(LB)
        mock_lb.project_id = a10constants.MOCK_CHILD_PROJECT_ID
        mock_thunder_config = copy.deepcopy(VTHUNDER)
        mock_thunder_config.hierarchical_multitenancy = "enable"
        vthunder_config = task.HandleACOSPartitionChange().execute(
            LB, mock_thunder_config)
        self.assertEqual(vthunder_config.partition_name,
                         a10constants.MOCK_PARENT_PROJECT_ID[:14])

    @mock.patch('a10_octavia.common.utils.get_parent_project',
                return_value=a10constants.MOCK_PARENT_PROJECT_ID)
    @mock.patch('a10_octavia.controller.worker.tasks.vthunder_tasks.a10_utils')
    def test_HandleACOSPartitionChange_parent_partition_no_hmt(
            self, mock_utils, mock_parent_project_id):
        self.conf.config(group=a10constants.A10_GLOBAL_CONF_SECTION,
                         use_parent_partition=True)
        partition = {
            'partition-name': a10constants.MOCK_CHILD_PROJECT_ID[:14],
            'status': 'Active'
        }
        mock_client = mock.Mock()
        mock_client.system.partition.get.return_value = partition
        mock_utils.get_axapi_client.return_value = mock_client

        mock_lb = copy.deepcopy(LB)
        mock_lb.project_id = a10constants.MOCK_CHILD_PROJECT_ID
        mock_thunder_config = copy.deepcopy(VTHUNDER)
        mock_thunder_config.hierarchical_multitenancy = "disable"
        vthunder_config = task.HandleACOSPartitionChange().execute(
            LB, mock_thunder_config)

        self.assertEqual(vthunder_config.partition_name, a10constants.MOCK_CHILD_PROJECT_ID[:14])

    @mock.patch('a10_octavia.common.utils.get_parent_project',
                return_value=a10constants.MOCK_PARENT_PROJECT_ID)
    @mock.patch('a10_octavia.controller.worker.tasks.vthunder_tasks.a10_utils')
    def test_HandleACOSPartitionChange_parent_partition_hmt_no_use_parent_partition(
            self, mock_utils, mock_parent_project_id):
        self.conf.config(
            group=a10constants.A10_GLOBAL_CONF_SECTION,
            use_parent_partition=False)

        partition = {
            'partition-name': a10constants.MOCK_CHILD_PROJECT_ID[:14],
            'status': 'Active'
        }
        mock_client = mock.Mock()
        mock_client.system.partition.get.return_value = partition
        mock_utils.get_axapi_client.return_value = mock_client

        mock_lb = copy.deepcopy(LB)
        mock_lb.project_id = a10constants.MOCK_CHILD_PROJECT_ID
        mock_thunder_config = copy.deepcopy(VTHUNDER)
        mock_thunder_config.hierarchical_multitenancy = "enable"

        vthunder_config = task.HandleACOSPartitionChange().execute(
            LB, mock_thunder_config)
        self.assertEqual(vthunder_config.partition_name, a10constants.MOCK_CHILD_PROJECT_ID[:14])

    @mock.patch('a10_octavia.common.utils.get_parent_project',
                return_value=a10constants.MOCK_PARENT_PROJECT_ID)
    @mock.patch('a10_octavia.controller.worker.tasks.vthunder_tasks.a10_utils')
    def test_HandleACOSPartitionChange_child_partition_exists(
            self, mock_utils, mock_parent_project_id):
        self.conf.config(
            group=a10constants.A10_GLOBAL_CONF_SECTION,
            use_parent_partition=False)

        partition = {
            'partition-name': a10constants.MOCK_CHILD_PROJECT_ID[:14],
            'status': 'Active'
        }
        mock_client = mock.Mock()
        mock_client.system.partition.get.return_value = partition
        mock_utils.get_axapi_client.return_value = mock_client

        mock_lb = copy.deepcopy(LB)
        mock_lb.project_id = a10constants.MOCK_CHILD_PROJECT_ID
        mock_thunder_config = copy.deepcopy(VTHUNDER)
        mock_thunder_config.hierarchical_multitenancy = "enable"

        vthunder_config = task.HandleACOSPartitionChange().execute(
            LB, mock_thunder_config)
        self.assertEqual(vthunder_config.partition_name,
                         a10constants.MOCK_CHILD_PROJECT_ID[:14])

    @mock.patch('a10_octavia.common.utils.get_parent_project',
                return_value=a10constants.MOCK_PARENT_PROJECT_ID)
    @mock.patch('a10_octavia.controller.worker.tasks.vthunder_tasks.a10_utils')
    def test_HandleACOSPartitionChange_nlbaas_backwards_compat(
            self, mock_utils, mock_parent_project_id):
        self.conf.config(
            group=a10constants.A10_GLOBAL_CONF_SECTION,
            use_parent_partition=False)

        partition = {
            'partition-name': a10constants.MOCK_CHILD_PROJECT_ID[:13],
            'status': 'Active'
        }
        mock_client = mock.Mock()
        mock_client.system.partition.get.return_value = partition
        mock_utils.get_axapi_client.return_value = mock_client

        mock_lb = copy.deepcopy(LB)
        mock_lb.project_id = a10constants.MOCK_CHILD_PROJECT_ID
        mock_thunder_config = copy.deepcopy(VTHUNDER)
        mock_thunder_config.hierarchical_multitenancy = "enable"

        vthunder_config = task.HandleACOSPartitionChange().execute(
            LB, mock_thunder_config)
        self.assertEqual(vthunder_config.partition_name,
                         a10constants.MOCK_CHILD_PROJECT_ID[:13])

    @mock.patch('a10_octavia.controller.worker.tasks.vthunder_tasks.time')
    def test_AmphoraPostVipPlug_execute_for_reload_reboot(self, mock_time):
        thunder = copy.deepcopy(VTHUNDER)
        added_ports = {'amphora_id': '123'}
        mock_task = task.AmphoraePostVIPPlug()
        mock_task.axapi_client = self.client_mock
        mock_task.loadbalancer_repo = mock.MagicMock()
        mock_task.vthunder_repo = mock.MagicMock()
        mock_task.loadbalancer_repo.check_lb_with_distinct_subnet_and_project.return_value = True
        mock_task.vthunder_repo.get_vthunder_by_project_id_and_role.return_value = thunder
        vthunder = mock_task.vthunder_repo.get_vthunder_by_project_id_and_role.return_value
        mock_task.execute(LB, thunder, added_ports)
        self.client_mock.system.action.write_memory.assert_called_with()
        self.client_mock.system.action.reload_reboot_for_interface_attachment.assert_called_with(
            vthunder.acos_version)

    @mock.patch('a10_octavia.controller.worker.tasks.vthunder_tasks.time')
    def test_AmphoraPostVipPlug_execute_for_no_reload_reboot(self, mock_time):
        thunder = copy.deepcopy(VTHUNDER)
        added_ports = {'amphora_id': ''}
        mock_task = task.AmphoraePostVIPPlug()
        mock_task.axapi_client = self.client_mock
        mock_task.loadbalancer_repo = mock.MagicMock()
        mock_task.loadbalancer_repo.check_lb_with_distinct_subnet_and_project.return_value = False
        mock_task.execute(LB, thunder, added_ports)
        self.client_mock.system.action.write_memory.assert_not_called()
        self.client_mock.system.action.reload_reboot_for_interface_attachment.assert_not_called()

    def test_UpdateAcosVersionInVthunderEntry_execute_for_first_lb(self):
        thunder = copy.deepcopy(VTHUNDER)
        mock_task = task.UpdateAcosVersionInVthunderEntry()
        mock_task.axapi_client = mock.MagicMock()[1:999]
        mock_task.vthunder_repo = mock.MagicMock()[1:999]
        mock_task.vthunder_repo.get_vthunder_by_project_id.return_value = None
        mock_task.vthunder_repo.get_delete_compute_flag.return_value = True
        mock_task.execute(thunder, LB)
        mock_task.axapi_client.system.action.get_acos_version.assert_called_with()

    def test_UpdateAcosVersionInVthunderEntry_execute_for_lb_with_existing_vthunder(self):
        thunder = copy.deepcopy(VTHUNDER)
        mock_task = task.UpdateAcosVersionInVthunderEntry()
        mock_task.axapi_client = mock.MagicMock()[1:999]
        mock_task.vthunder_repo = mock.MagicMock()[1:999]
        mock_task.vthunder_repo.get_vthunder_by_project_id.return_value = VTHUNDER
        mock_task.vthunder_repo.get_delete_compute_flag.return_value = False
        mock_task.execute(thunder, LB)
        mock_task.axapi_client.system.action.get_acos_version.assert_not_called()

    @mock.patch('a10_octavia.controller.worker.tasks.vthunder_tasks.time')
    def test_AmphoraePostMemberNetworkPlug_execute_for_reload_reboot(self, mock_time):
        thunder = copy.deepcopy(VTHUNDER)
        thunder.acos_version = "5.2.1"
        added_ports = {'amphora_id': '123'}
        mock_task = task.AmphoraePostMemberNetworkPlug()
        mock_task.axapi_client = self.client_mock
        mock_task.execute(added_ports, LB, thunder)
        self.client_mock.system.action.write_memory.assert_called_with()
        self.client_mock.system.action.reload_reboot_for_interface_attachment.assert_called_with(
            "5.2.1")

    @mock.patch('a10_octavia.controller.worker.tasks.vthunder_tasks.time')
    def test_AmphoraePostMemberNetworkPlug_execute_for_no_reload_reboot(self, mock_time):
        thunder = copy.deepcopy(VTHUNDER)
        thunder.acos_version = "5.2.1"
        added_ports = {'amphora_id': ''}
        mock_task = task.AmphoraePostMemberNetworkPlug()
        mock_task.axapi_client = self.client_mock
        mock_task.execute(added_ports, LB, thunder)
        self.client_mock.system.action.write_memory.assert_not_called()
        self.client_mock.system.action.reload_reboot_for_interface_attachment.assert_not_called()

    @mock.patch('a10_octavia.controller.worker.tasks.vthunder_tasks.time')
    def test_AmphoraePostNetworkUnplug_execute_for_reload_reboot(self, mock_time):
        thunder = copy.deepcopy(VTHUNDER)
        added_ports = {'amphora_id': '123'}
        mock_task = task.AmphoraePostNetworkUnplug()
        mock_task.axapi_client = self.client_mock
        mock_task.execute(added_ports, LB, thunder)
        self.client_mock.system.action.write_memory.assert_called_with()
        self.client_mock.system.action.reload_reboot_for_interface_detachment.assert_called_with(
            "5.2.1")

    @mock.patch('a10_octavia.controller.worker.tasks.vthunder_tasks.time')
    def test_AmphoraePostNetworkUnplug_execute_no_port_no_verion_no_reload_reboot(self, mock_time):
        thunder = copy.deepcopy(VTHUNDER)
        added_ports = {'amphora_id': ''}
        mock_task = task.AmphoraePostNetworkUnplug()
        mock_task.axapi_client = self.client_mock
        mock_task.execute(added_ports, LB, thunder)
        self.client_mock.system.action.write_memory.assert_not_called()
        self.client_mock.system.action.reload_reboot_for_interface_detachment.assert_not_called()

    def test_GetVThunderInterface_execute_for_vMaster(self):
        thunder = copy.deepcopy(VTHUNDER)
        mock_task = task.GetVThunderInterface()
        mock_task.axapi_client = self.client_mock
        self.client_mock.system.action.get_vcs_summary_oper.return_value = VCS_MASTER_VBLADE
        self.client_mock.interface.get_list.return_value = INTERFACES
        thunder.ip_address = "10.0.0.1"
        mock_task.execute(thunder)
        self.client_mock.system.action.setInterface.assert_not_called()
        self.assertEqual(mock_task.execute(thunder), ([1], []))

    def test_GetVThunderInterface_execute_for_vBlade(self):
        thunder = copy.deepcopy(VTHUNDER)
        mock_task = task.GetVThunderInterface()
        mock_task.axapi_client = self.client_mock
        self.client_mock.system.action.get_vcs_summary_oper.return_value = VCS_MASTER_VBLADE
        self.client_mock.interface.get_list.return_value = INTERFACES
        thunder.ip_address = "10.0.0.2"
        mock_task.execute(thunder)
        self.client_mock.system.action.setInterface.assert_not_called()
        self.assertEqual(mock_task.execute(thunder), ([], [1]))

    def test_EnableInterface_execute_for_single_topology(self):
        thunder = copy.deepcopy(VTHUNDER)
        added_ports = {'amphora_id': ''}
        thunder.topology = "SINGLE"
        mock_task = task.EnableInterface()
        mock_task.loadbalancer_repo = mock.MagicMock()
        mock_task.loadbalancer_repo.check_lb_exists_in_project.return_value = True
        mock_task.axapi_client = self.client_mock
        self.client_mock.interface.get_list.return_value = INTERFACES
        mock_task.execute(thunder, LB, added_ports)
        self.client_mock.system.action.setInterface.assert_not_called()

    def test_EnableInterface_execute_for_active_standby_topology(self):
        thunder = copy.deepcopy(VTHUNDER)
        added_ports = {'amphora_id': ''}
        thunder.topology = "ACTIVE_STANDBY"
        mock_task = task.EnableInterface()
        mock_task.loadbalancer_repo = mock.MagicMock()
        mock_task.loadbalancer_repo.check_lb_exists_in_project.return_value = True
        mock_task.axapi_client = self.client_mock
        self.client_mock.interface.get_list.return_value = INTERFACES
        mock_task.execute(thunder, LB, added_ports)
        self.client_mock.system.action.setInterface.assert_not_called()

    def test_AmphoraePostNetworkUnplug_amophora_not_available(self):
        mock_thunder = copy.deepcopy(VTHUNDER)
        mock_LB = copy.deepcopy(LB)
        mock_LB.amphorae = []
        added_ports = {}
        mock_task = task.AmphoraePostNetworkUnplug()
        mock_task.axapi_client = self.client_mock
        mock_task.execute(added_ports, mock_LB, mock_thunder)
        self.client_mock.system.action.write_memory.assert_not_called()
        self.client_mock.system.action.reload_reboot_for_interface_detachment.assert_not_called()

    def test_GetVthunderConfByFlavor_with_flavor(self):
        conf = {}
        use_dev_flavor = False
        mock_LB = copy.deepcopy(LB)
        mock_task = task.GetVthunderConfByFlavor()
        mock_task.axapi_client = self.client_mock
        conf, use_dev_flavor = mock_task.execute(mock_LB, FLAVOR_DEV2, DEV_CONF_DICT, DEV_FLAVOR)
        self.assertEqual(use_dev_flavor, True)
        self.assertEqual(conf, FLAVOR_DEV1)

    def test_GetVthunderConfByFlavor_without_flavor(self):
        conf = {}
        use_dev_flavor = False
        mock_LB = copy.deepcopy(LB)
        mock_task = task.GetVthunderConfByFlavor()
        mock_task.axapi_client = self.client_mock
        conf, use_dev_flavor = mock_task.execute(mock_LB, FLAVOR_DEV2, DEV_CONF_DICT, None)
        self.assertEqual(use_dev_flavor, False)
        self.assertEqual(conf, FLAVOR_DEV2)

    def test_allowl2dsr_with_deployment_flavor(self):
        mock_task = task.AllowL2DSR()
        mock_task._network_driver = self.client_mock
        lb_count = 1
        mock_task.execute(SUBNET, AMPHORAE, lb_count, flavor_data=DEPLOYMENT_FLAVOR)
        self.client_mock.allow_use_any_source_ip_on_egress.assert_called_with(
            SUBNET.network_id, AMPHORAE[0])

    def test_allowl2dsr_without_deployment_flavor(self):
        mock_task = task.AllowL2DSR()
        mock_task._network_driver = self.client_mock
        lb_count = 1
        mock_task.execute(SUBNET, AMPHORAE, lb_count, flavor_data=DEV_FLAVOR)
        self.client_mock.allow_use_any_source_ip_on_egress.assert_not_called()

    def test_deletel2dsr_with_deployment_flavor(self):
        mock_task = task.DeleteL2DSR()
        mock_task._network_driver = self.client_mock
        lb_count = 1
        mock_task.execute(SUBNET, AMPHORAE, lb_count, lb_count, flavor_data=DEPLOYMENT_FLAVOR)
        self.client_mock.remove_any_source_ip_on_egress.assert_called_with(
            SUBNET.network_id, AMPHORAE[0])
