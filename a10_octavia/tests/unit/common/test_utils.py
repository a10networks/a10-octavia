# Copyright 2020, A10 Networks.
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

from a10_octavia.common import config_options
from a10_octavia.common import data_models
from a10_octavia.common import exceptions
from a10_octavia.common import utils
from a10_octavia.tests.common import a10constants
from a10_octavia.tests.unit import base

SHARED_HARDWARE_DEVICE = {'partition_name': 'shared'}
HARDWARE_DEVICE = {
    'partition_name': 'sample-1'
}

HARDWARE_INFO = {
    'project_id': 'project-1',
    'ip_address': '10.10.10.10',
    'device_name': 'rack_thunder_1',
    'username': 'abc',
    'password': 'abc'
}

HARDWARE_INFO_2 = {
    'project_id': 'project-2',
    'ip_address': '12.12.12.12',
    'device_name': 'rack_thunder_2',
    'username': 'def',
    'password': 'def',
    'partition_name': 'def-sample'
}

DUP_PARTITION_HARDWARE_INFO = {
    'project_id': 'project-3',
    'ip_address': '10.10.10.10',
    'device_name': 'rack_thunder_3',
    'username': 'abc',
    'password': 'abc'}

HARDWARE_INFO_WITH_HMT_ENABLED = [{
    'project_id': a10constants.MOCK_CHILD_PROJECT_ID,
    'ip_address': '13.13.13.13',
    'device_name': 'rack_thunder_3',
    'username': 'usr',
    'password': 'pwd',
    'hierarchical_multitenancy': 'enable',
    'partition_name': 'shared'
}]

VTHUNDER_1 = data_models.HardwareThunder(project_id="project-1", device_name="rack_thunder_1",
                                         undercloud=True, username="abc", password="abc",
                                         ip_address="10.10.10.10", partition_name="shared")
VTHUNDER_2 = data_models.HardwareThunder(project_id="project-2", device_name="rack_thunder_2",
                                         undercloud=True, username="def", password="def",
                                         ip_address="12.12.12.12", partition_name="def-sample")
VTHUNDER_3 = data_models.HardwareThunder(project_id=a10constants.MOCK_CHILD_PROJECT_ID,
                                         device_name="rack_thunder_3",
                                         undercloud=True, username="usr", password="pwd",
                                         hierarchical_multitenancy='enable',
                                         ip_address="13.13.13.13",
                                         partition_name=a10constants.MOCK_CHILD_PARTITION)

DUPLICATE_DICT = {'project_1': VTHUNDER_1,
                  'project_2': VTHUNDER_1}
DUP_LIST = ['10.10.10.10:shared']
NON_DUPLICATE_DICT = {'project_1': VTHUNDER_1, 'project_2': VTHUNDER_2}

DUPLICATE_PROJECT_HARDWARE_DEVICE_LIST = [
    HARDWARE_INFO, HARDWARE_INFO
]

HARDWARE_DEVICE_LIST = [
    HARDWARE_INFO, HARDWARE_INFO_2
]

DUPLICATE_PARTITION_HARDWARE_DEVICE_LIST = [DUP_PARTITION_HARDWARE_INFO, HARDWARE_INFO]
RESULT_HARDWARE_DEVICE_LIST = {'project-1': VTHUNDER_1,
                               'project-2': VTHUNDER_2}

RESULT_HMT_HARDWARE_DEVICE_LIST = {a10constants.MOCK_CHILD_PROJECT_ID: VTHUNDER_3}

INTERFACE_CONF = {"interface_num": 1,
                  "vlan_map": [
                      {"vlan_id": 11, "ve_ip": "10.20"},
                      {"vlan_id": 12, "use_dhcp": "True"},
                      {"vlan_id": 13, "ve_ip": "10.30"}]
                  }
INTERFACE = data_models.Interface(interface_num=1, tags=[11, 12, 13], ve_ips=[
                                  "10.20", "dhcp", "10.30"])
DEVICE_NETWORK_MAP = [data_models.DeviceNetworkMap(
    vcs_device_id=1, ethernet_interfaces=[INTERFACE])]
HARDWARE_VLAN_INFO = {
    "interface_vlan_map": {
        "device_1": {
            "vcs_device_id": 1,
            "ethernet_interfaces": [INTERFACE_CONF]
        }
    }
}


class FakeProject(object):
    def __init__(self, parent_id='default'):
        self.parent_id = parent_id


class TestUtils(base.BaseTaskTestCase):

    def setUp(self):
        super(TestUtils, self).setUp()
        imp.reload(utils)
        self.conf = self.useFixture(oslo_fixture.Config(cfg.CONF))
        self.conf.register_opts(config_options.A10_HARDWARE_THUNDER_OPTS,
                                group=a10constants.HARDWARE_THUNDER_CONF_SECTION)

    def tearDown(self):
        super(TestUtils, self).tearDown()
        self.conf.reset()

    def test_validate_ipv4_valid(self):
        self.assertEqual(utils.validate_ipv4('10.43.12.122'), None)

    def test_validate_ipv4_invalid(self):
        self.assertRaises(cfg.ConfigFileValueError, utils.validate_ipv4, '192.0.20')
        self.assertRaises(cfg.ConfigFileValueError, utils.validate_ipv4, 'abc')

    def test_validate_partial_ipv4_valid(self):
        self.assertEqual(utils.validate_partial_ipv4('10'), '10')
        self.assertEqual(utils.validate_partial_ipv4('.10'), '.10')
        self.assertEqual(utils.validate_partial_ipv4('.5.11.10'), '.5.11.10')
        self.assertEqual(utils.validate_partial_ipv4('11.5.11.10'), '11.5.11.10')

    def test_validate_partial_ipv4_invalid(self):
        self.assertRaises(cfg.ConfigFileValueError, utils.validate_partial_ipv4, '777')
        self.assertRaises(cfg.ConfigFileValueError, utils.validate_partial_ipv4, 'abc.cef')
        self.assertRaises(cfg.ConfigFileValueError, utils.validate_partial_ipv4, '11.10.0.11.10')
        self.assertRaises(cfg.ConfigFileValueError, utils.validate_partial_ipv4, '10.333.11.10')

    def test_validate_partition_valid(self):
        self.assertEqual(utils.validate_partition(HARDWARE_DEVICE), None)
        empty_hardware_device = {}
        self.assertEqual(utils.validate_partition(empty_hardware_device), None)

    def test_validate_partition_invalid(self):
        long_partition_hardware_device = copy.deepcopy(HARDWARE_DEVICE)
        long_partition_hardware_device['partition_name'] = 'sample_long_partition_name'
        self.assertRaises(ValueError, utils.validate_partition, long_partition_hardware_device)

    def test_validate_params_valid(self):
        shared_hardware_info = copy.deepcopy(HARDWARE_INFO)
        self.assertEqual(utils.validate_params(HARDWARE_INFO), shared_hardware_info)

    def test_validate_params_invalid(self):
        empty_param_hardware_info = {}
        missing_param_hardware_info = {'project_id': 'abc'}
        self.assertRaises(cfg.ConfigFileValueError, utils.validate_params,
                          empty_param_hardware_info)
        self.assertRaises(cfg.ConfigFileValueError, utils.validate_params,
                          missing_param_hardware_info)

    def test_check_duplicate_entries_dup_found(self):
        self.assertEqual(utils.check_duplicate_entries(DUPLICATE_DICT), DUP_LIST)

    def test_check_duplicate_entries_no_dup_found(self):
        self.assertEqual(utils.check_duplicate_entries(NON_DUPLICATE_DICT), [])

    def test_convert_to_hardware_thunder_conf_valid(self):
        self.assertEqual(utils.convert_to_hardware_thunder_conf(HARDWARE_DEVICE_LIST),
                         RESULT_HARDWARE_DEVICE_LIST)
        self.assertEqual(utils.convert_to_hardware_thunder_conf([]), {})

    def test_convert_to_hardware_thunder_conf_invalid(self):
        self.assertRaises(cfg.ConfigFileValueError, utils.convert_to_hardware_thunder_conf,
                          DUPLICATE_PROJECT_HARDWARE_DEVICE_LIST)
        self.assertRaises(cfg.ConfigFileValueError, utils.convert_to_hardware_thunder_conf,
                          DUPLICATE_PARTITION_HARDWARE_DEVICE_LIST)

    def test_convert_to_hardware_thunder_conf_with_hmt(self):
        self.assertEqual(utils.convert_to_hardware_thunder_conf(HARDWARE_INFO_WITH_HMT_ENABLED),
                         RESULT_HMT_HARDWARE_DEVICE_LIST)

    @mock.patch('octavia.common.keystone.KeystoneSession')
    @mock.patch('a10_octavia.common.utils.keystone_client.Client')
    def test_get_parent_project_exists(self, mock_key_client, mock_get_session):
        client_mock = mock.Mock()
        client_mock.projects.get.return_value = FakeProject(
            parent_id=a10constants.MOCK_PARENT_PROJECT_ID)
        mock_key_client.return_value = client_mock
        self.assertEqual(utils.get_parent_project(a10constants.MOCK_CHILD_PROJECT_ID),
                         a10constants.MOCK_PARENT_PROJECT_ID)

    @mock.patch('octavia.common.keystone.KeystoneSession')
    @mock.patch('a10_octavia.common.utils.keystone_client.Client')
    def test_get_parent_project_not_exists(self, mock_key_client, mock_get_session):
        client_mock = mock.Mock()
        client_mock.projects.get.return_value = FakeProject()
        mock_key_client.return_value = client_mock
        self.assertEqual(utils.get_parent_project(a10constants.MOCK_CHILD_PROJECT_ID), 'default')

    def test_get_net_info_from_cidr_valid(self):
        self.assertEqual(utils.get_net_info_from_cidr('10.10.10.1/32'),
                         ('10.10.10.1', '255.255.255.255'))
        self.assertEqual(utils.get_net_info_from_cidr('10.10.10.0/24'),
                         ('10.10.10.0', '255.255.255.0'))
        self.assertEqual(utils.get_net_info_from_cidr('10.10.0.0/16'),
                         ('10.10.0.0', '255.255.0.0'))

    def test_get_net_info_from_cidr_invalid(self):
        self.assertRaises(Exception, utils.get_net_info_from_cidr, '10.10.10.1/33')

    def test_check_ip_in_subnet_range_valid(self):
        self.assertEqual(utils.check_ip_in_subnet_range('10.10.10.1', '10.10.10.1',
                                                        '255.255.255.255'), True)
        self.assertEqual(utils.check_ip_in_subnet_range('10.10.10.1', '10.10.11.0',
                                                        '255.255.255.0'), False)
        self.assertEqual(utils.check_ip_in_subnet_range('10.10.10.1', '10.10.0.0',
                                                        '255.255.0.0'), True)
        self.assertEqual(utils.check_ip_in_subnet_range('10.11.10.2', '10.10.0.0',
                                                        '255.255.0.0'), False)

    def test_check_ip_in_subnet_range_invalid(self):
        self.assertRaises(Exception, utils.check_ip_in_subnet_range, '1010.10.10.2',
                          '10.10.10.1', '255.255.255.255')
        self.assertRaises(Exception, utils.check_ip_in_subnet_range, '10.10.10.2',
                          '10.333.10.0', '255.255.255.0')
        self.assertRaises(Exception, utils.check_ip_in_subnet_range, '10.11.10.2',
                          '10.10.0.0', '2555.255.0.0')

    def test_merge_host_and_network_ip_valid(self):
        self.assertEqual(utils.merge_host_and_network_ip('10.10.10.0/24', '0.0.0.9'),
                         '10.10.10.9')
        self.assertEqual(utils.merge_host_and_network_ip('10.10.10.0/24', '0.0.0.9'),
                         '10.10.10.9')
        self.assertEqual(utils.merge_host_and_network_ip('10.10.0.0/16', '0.0.11.9'),
                         '10.10.11.9')

    def test_merge_host_and_network_ip_invalid(self):
        self.assertRaises(Exception, utils.merge_host_and_network_ip, '10.10.10.0/42', '99')

    def test_get_patched_ip_address(self):
        self.assertEqual(utils.get_patched_ip_address('45', '10.10.0.0/24'), '10.10.0.45')
        self.assertEqual(utils.get_patched_ip_address('0.45', '10.10.0.0/24'), '10.10.0.45')
        self.assertEqual(utils.get_patched_ip_address('0.0.45', '10.10.0.0/24'), '10.10.0.45')
        self.assertEqual(utils.get_patched_ip_address('.45', '10.10.0.0/24'), '10.10.0.45')
        self.assertEqual(utils.get_patched_ip_address('11.45', '11.11.11.0/24'), '11.11.11.45')
        self.assertEqual(utils.get_patched_ip_address('3.45', '11.11.2.0/23'), '11.11.3.45')
        self.assertEqual(utils.get_patched_ip_address('3.45', '11.11.2.0/22'), '11.11.3.45')

    def test_get_patched_ip_address_invalid(self):
        vrid_exc = exceptions.VRIDIPNotInSubentRangeError
        cfg_err = cfg.ConfigFileValueError
        self.assertRaises(vrid_exc, utils.get_patched_ip_address, 'abc.cef', '10.10.0.0/24')
        self.assertRaises(vrid_exc, utils.get_patched_ip_address, '.0.11.10', '10.10.0.0/24')
        self.assertRaises(vrid_exc, utils.get_patched_ip_address, '1.0.0.23', '10.10.0.0/24')
        self.assertRaises(cfg_err, utils.get_patched_ip_address, '10.333.11.10', '10.10.0.0/24')
        self.assertRaises(cfg_err, utils.get_patched_ip_address, '1e.3d.4f.1o', '10.10.0.0/24')

    def test_get_vrid_floating_ip_for_project_with_only_local_config(self):
        vthunder = copy.deepcopy(VTHUNDER_1)
        vthunder.vrid_floating_ip = '10.10.0.75'
        vthunder.project_id = a10constants.MOCK_PROJECT_ID
        hardware_device_conf = [{"project_id": a10constants.MOCK_PROJECT_ID,
                                 "username": vthunder.username,
                                 "password": vthunder.password,
                                 "device_name": vthunder.device_name,
                                 "vrid_floating_ip": vthunder.vrid_floating_ip,
                                 "ip_address": vthunder.ip_address}]
        self.conf.config(group=a10constants.HARDWARE_THUNDER_CONF_SECTION,
                         devices=hardware_device_conf)
        self.conf.conf.hardware_thunder.devices = {a10constants.MOCK_PROJECT_ID: vthunder}
        utils.get_vrid_floating_ip_for_project.CONF = self.conf
        self.assertEqual(utils.get_vrid_floating_ip_for_project(
            a10constants.MOCK_PROJECT_ID), '10.10.0.75')
        self.assertEqual(utils.get_vrid_floating_ip_for_project('project-2'), None)

    def test_get_vrid_floating_ip_for_project_with_only_global_config(self):
        vthunder = copy.deepcopy(VTHUNDER_1)
        vthunder.project_id = a10constants.MOCK_PROJECT_ID
        hardware_device_conf = [{"project_id": a10constants.MOCK_PROJECT_ID,
                                 "username": vthunder.username,
                                 "password": vthunder.password,
                                 "device_name": vthunder.device_name,
                                 "vrid_floating_ip": None,
                                 "ip_address": vthunder.ip_address}]
        self.conf.config(group=a10constants.A10_GLOBAL_OPTS,
                         vrid_floating_ip='10.10.0.72')
        self.conf.config(group=a10constants.HARDWARE_THUNDER_CONF_SECTION,
                         devices=hardware_device_conf)
        self.conf.conf.hardware_thunder.devices = {a10constants.MOCK_PROJECT_ID: vthunder}
        utils.get_vrid_floating_ip_for_project.CONF = self.conf
        self.assertEqual(utils.get_vrid_floating_ip_for_project(
            a10constants.MOCK_PROJECT_ID), '10.10.0.72')

    def test_get_vrid_floating_ip_for_project_with_both_local_and_global_config(self):
        vthunder = copy.deepcopy(VTHUNDER_1)
        vthunder.vrid_floating_ip = '10.10.0.75'
        vthunder.project_id = a10constants.MOCK_PROJECT_ID
        hardware_device_conf = [{"project_id": a10constants.MOCK_PROJECT_ID,
                                 "username": vthunder.username,
                                 "password": vthunder.password,
                                 "device_name": vthunder.device_name,
                                 "vrid_floating_ip": vthunder.vrid_floating_ip,
                                 "ip_address": vthunder.ip_address}]
        self.conf.config(group=a10constants.HARDWARE_THUNDER_CONF_SECTION,
                         devices=hardware_device_conf)
        self.conf.config(group=a10constants.A10_GLOBAL_OPTS,
                         vrid_floating_ip='10.10.0.72')
        self.conf.conf.hardware_thunder.devices = {a10constants.MOCK_PROJECT_ID: vthunder}
        utils.get_vrid_floating_ip_for_project.CONF = self.conf
        self.assertEqual(utils.get_vrid_floating_ip_for_project(
            a10constants.MOCK_PROJECT_ID), '10.10.0.75')

    def test_validate_interface_vlan_map(self):
        self.assertEqual(utils.validate_interface_vlan_map(HARDWARE_VLAN_INFO), DEVICE_NETWORK_MAP)

    def test_convert_interface_to_data_model_with_valid_config(self):
        self.assertEqual(utils.convert_interface_to_data_model(INTERFACE_CONF), INTERFACE)

    def test_convert_interface_to_data_model_with_invalid_config(self):
        missing_iface_num_in_iface_obj = {}
        self.assertRaises(exceptions.MissingInterfaceNumConfigError,
                          utils.convert_interface_to_data_model, missing_iface_num_in_iface_obj)
        missing_vlan_id_in_iface_obj = {"interface_num": 1,
                                        "vlan_map": [{}]}
        self.assertRaises(exceptions.MissingVlanIDConfigError,
                          utils.convert_interface_to_data_model, missing_vlan_id_in_iface_obj)
        missing_ve_ip_in_iface_obj = {"interface_num": 1,
                                      "vlan_map": [
                                          {"vlan_id": 11}]}
        self.assertRaises(exceptions.VirtEthMissingConfigError,
                          utils.convert_interface_to_data_model, missing_ve_ip_in_iface_obj)
        ve_ips_collision_in_iface_obj = {"interface_num": 1,
                                         "vlan_map": [
                                             {"vlan_id": 11, "use_dhcp": "True", "ve_ip": "10.30"}]}
        self.assertRaises(exceptions.VirtEthCollisionConfigError,
                          utils.convert_interface_to_data_model, ve_ips_collision_in_iface_obj)
        missing_ve_ip_in_iface_obj = {"interface_num": 1,
                                      "vlan_map": [
                                          {"vlan_id": 11, "use_dhcp": "False"}]}
        self.assertRaises(exceptions.VirtEthMissingConfigError,
                          utils.convert_interface_to_data_model, missing_ve_ip_in_iface_obj)
        duplicate_vlan_ids_in_iface_obj = {"interface_num": 1,
                                           "vlan_map": [
                                               {"vlan_id": 11, "ve_ip": "10.20"},
                                               {"vlan_id": 11, "use_dhcp": "True"}]}
        self.assertRaises(exceptions.DuplicateVlanTagsConfigError,
                          utils.convert_interface_to_data_model, duplicate_vlan_ids_in_iface_obj)

    def test_validate_vcs_device_info_valid(self):
        interface = utils.convert_interface_to_data_model(INTERFACE_CONF)
        device1_network_map = data_models.DeviceNetworkMap(vcs_device_id=1,
                                                           ethernet_interfaces=[interface])
        device2_network_map = data_models.DeviceNetworkMap(vcs_device_id=2,
                                                           mgmt_ip_address="10.0.0.2",
                                                           ethernet_interfaces=[interface])
        device_network_map = []
        self.assertEqual(utils.validate_vcs_device_info(device_network_map), None)
        device_network_map = [device1_network_map]
        self.assertEqual(utils.validate_vcs_device_info(device_network_map), None)
        device1_network_map.mgmt_ip_address = "10.0.0.1"
        self.assertEqual(utils.validate_vcs_device_info(device_network_map), None)
        device_network_map = [device1_network_map, device2_network_map]
        self.assertEqual(utils.validate_vcs_device_info(device_network_map), None)

    def test_validate_vcs_device_info_invalid(self):
        interface = utils.convert_interface_to_data_model(INTERFACE_CONF)
        device1_network_map = data_models.DeviceNetworkMap(mgmt_ip_address="10.0.0.1",
                                                           ethernet_interfaces=[interface])
        device2_network_map = data_models.DeviceNetworkMap(mgmt_ip_address="10.0.0.2",
                                                           ethernet_interfaces=[interface])
        device1_network_map.vcs_device_id = 3
        device_network_map = [device1_network_map]
        self.assertRaises(exceptions.InvalidVcsDeviceIdConfigError,
                          utils.validate_vcs_device_info, device_network_map)
        device1_network_map.vcs_device_id = 0
        device_network_map = [device1_network_map]
        self.assertRaises(exceptions.InvalidVcsDeviceIdConfigError,
                          utils.validate_vcs_device_info, device_network_map)
        device1_network_map.vcs_device_id = 1
        device2_network_map.vcs_device_id = 3
        device_network_map = [device1_network_map, device2_network_map]
        self.assertRaises(exceptions.InvalidVcsDeviceIdConfigError,
                          utils.validate_vcs_device_info, device_network_map)
        device1_network_map.vcs_device_id = 0
        device2_network_map.vcs_device_id = 2
        device_network_map = [device1_network_map, device2_network_map]
        self.assertRaises(exceptions.InvalidVcsDeviceIdConfigError,
                          utils.validate_vcs_device_info, device_network_map)
        device1_network_map.vcs_device_id = 1
        device2_network_map.vcs_device_id = None
        device_network_map = [device1_network_map, device2_network_map]
        self.assertRaises(exceptions.InvalidVcsDeviceIdConfigError,
                          utils.validate_vcs_device_info, device_network_map)
        device_network_map = [device1_network_map, device2_network_map, device2_network_map]
        self.assertRaises(exceptions.VcsDevicesNumberExceedsConfigError,
                          utils.validate_vcs_device_info, device_network_map)
        device2_network_map.vcs_device_id = 2
        device2_network_map.mgmt_ip_address = None
        device_network_map = [device1_network_map, device2_network_map]
        self.assertRaises(exceptions.MissingMgmtIpConfigError,
                          utils.validate_vcs_device_info, device_network_map)
