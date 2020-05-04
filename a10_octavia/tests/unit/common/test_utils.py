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

SHARED_RACK_DEVICE = {'partition_name': 'shared'}
RACK_DEVICE = {
    'partition_name': 'sample-1'
}

RACK_INFO = {
    'project_id': 'project-1',
    'ip_address': '10.10.10.10',
    'device_name': 'rack_thunder_1',
    'username': 'abc',
    'password': 'abc'
}

RACK_INFO_2 = {
    'project_id': 'project-2',
    'ip_address': '12.12.12.12',
    'device_name': 'rack_thunder_2',
    'username': 'def',
    'password': 'def',
    'partition_name': 'def-sample'
}

DUP_PARTITION_RACK_INFO = {
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

DUPLICATE_PROJECT_RACK_DEVICE_LIST = [
    RACK_INFO, RACK_INFO
]

RACK_DEVICE_LIST = [
    RACK_INFO, RACK_INFO_2
]

DUPLICATE_PARTITION_RACK_DEVICE_LIST = [DUP_PARTITION_RACK_INFO, RACK_INFO]
RESULT_RACK_DEVICE_LIST = {'project-1': VTHUNDER_1,
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

    def test_validate_partition_valid(self):
        self.assertEqual(utils.validate_partition(RACK_DEVICE), RACK_DEVICE)
        empty_rack_device = {}
        self.assertEqual(utils.validate_partition(empty_rack_device), SHARED_RACK_DEVICE)

    def test_validate_partition_invalid(self):
        long_partition_rack_device = copy.deepcopy(RACK_DEVICE)
        long_partition_rack_device['partition_name'] = 'sample_long_partition_name'
        self.assertRaises(ValueError, utils.validate_partition, long_partition_rack_device)

    def test_validate_params_valid(self):
        shared_rack_info = copy.deepcopy(RACK_INFO)
        shared_rack_info['partition_name'] = 'shared'
        self.assertEqual(utils.validate_params(RACK_INFO), shared_rack_info)

    def test_validate_params_invalid(self):
        empty_param_rack_info = {}
        missing_param_rack_info = {'project_id': 'abc'}
        self.assertRaises(cfg.ConfigFileValueError, utils.validate_params, empty_param_rack_info)
        self.assertRaises(cfg.ConfigFileValueError, utils.validate_params, missing_param_rack_info)

    def test_check_duplicate_entries_dup_found(self):
        self.assertEqual(utils.check_duplicate_entries(DUPLICATE_DICT), DUP_LIST)

    def test_check_duplicate_entries_no_dup_found(self):
        self.assertEqual(utils.check_duplicate_entries(NON_DUPLICATE_DICT), [])

    def test_convert_to_rack_vthunder_conf_valid(self):
        self.assertEqual(utils.convert_to_rack_vthunder_conf(RACK_DEVICE_LIST),
                         RESULT_RACK_DEVICE_LIST)
        self.assertEqual(utils.convert_to_rack_vthunder_conf([]), {})

    def test_convert_to_rack_vthunder_conf_invalid(self):
        self.assertRaises(cfg.ConfigFileValueError, utils.convert_to_rack_vthunder_conf,
                          DUPLICATE_PROJECT_RACK_DEVICE_LIST)
        self.assertRaises(cfg.ConfigFileValueError, utils.convert_to_rack_vthunder_conf,
                          DUPLICATE_PARTITION_RACK_DEVICE_LIST)

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
