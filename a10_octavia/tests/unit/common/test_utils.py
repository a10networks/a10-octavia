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
import unittest
try:
    from unittest import mock
except ImportError:
    import mock

from oslo_config import cfg

from a10_octavia.common import data_models
from a10_octavia.common import utils
from a10_octavia.tests.common import a10constants

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

VTHUNDER_1 = data_models.VThunder(project_id="project-1", device_name="rack_thunder_1",
                                  undercloud=True, username="abc", password="abc",
                                  ip_address="10.10.10.10", partition_name="shared")
VTHUNDER_2 = data_models.VThunder(project_id="project-2", device_name="rack_thunder_2",
                                  undercloud=True, username="def", password="def",
                                  ip_address="12.12.12.12", partition_name="def-sample")

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


class FakeProject(object):
    def __init__(self, parent_id='default'):
        self.parent_id = parent_id


class TestUtils(unittest.TestCase):

    def test_validate_ipv4_valid(self):
        self.assertEqual(utils.validate_ipv4('10.43.12.122'), None)

    def test_validate_ipv4_invalid(self):
        self.assertRaises(cfg.ConfigFileValueError, utils.validate_ipv4, '192.0.20')
        self.assertRaises(cfg.ConfigFileValueError, utils.validate_ipv4, 'abc')

    def test_validate_partial_ipv4_valid(self):
        self.assertEqual(utils.validate_partial_ipv4('10'), None)
        self.assertEqual(utils.validate_partial_ipv4('.10'), None)
        self.assertEqual(utils.validate_partial_ipv4('.5.11.10'), None)
        self.assertEqual(utils.validate_partial_ipv4('11.5.11.10'), None)

    def test_validate_partial_ipv4_invalid(self):
        self.assertRaises(cfg.ConfigFileValueError, utils.validate_partial_ipv4, '777')
        self.assertRaises(cfg.ConfigFileValueError, utils.validate_partial_ipv4, 'abc.cef')
        self.assertRaises(cfg.ConfigFileValueError, utils.validate_partial_ipv4, '11.10.0.11.10')
        self.assertRaises(cfg.ConfigFileValueError, utils.validate_partial_ipv4, '10.333.11.10')

    def test_validate_partition_valid(self):
        self.assertEqual(utils.validate_partition(HARDWARE_DEVICE), HARDWARE_DEVICE)
        empty_hardware_device = {}
        self.assertEqual(utils.validate_partition(empty_hardware_device), SHARED_HARDWARE_DEVICE)

    def test_validate_partition_invalid(self):
        long_partition_hardware_device = copy.deepcopy(HARDWARE_DEVICE)
        long_partition_hardware_device['partition_name'] = 'sample_long_partition_name'
        self.assertRaises(ValueError, utils.validate_partition, long_partition_hardware_device)

    def test_validate_params_valid(self):
        shared_hardware_info = copy.deepcopy(HARDWARE_INFO)
        shared_hardware_info['partition_name'] = 'shared'
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
        self.assertIsNone(utils.get_parent_project(a10constants.MOCK_CHILD_PROJECT_ID))

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
