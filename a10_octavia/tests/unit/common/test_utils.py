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

from copy import deepcopy
from oslo_config.cfg import ConfigFileValueError

from a10_octavia.common.data_models import VThunder
import a10_octavia.common.utils as utils
from a10_octavia.tests.unit.base import BaseTaskTestCase

SHARED_RACK_DEVICE = {'partition': 'shared'}
RACK_DEVICE = {
    'partition': 'sample-1'
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
    'partition': 'def-sample'
}

DUP_PARTITION_RACK_INFO = {
    'project_id': 'project-3',
    'ip_address': '10.10.10.10',
    'device_name': 'rack_thunder_3',
    'username': 'abc',
    'password': 'abc'}

INVALID_RACK_INFO = {}
VTHUNDER_1 = VThunder(project_id="project-1", device_name="rack_thunder_1", undercloud=True,
                      username="abc", password="abc", ip_address="10.10.10.10", partition="shared")
VTHUNDER_2 = VThunder(project_id="project-2", device_name="rack_thunder_2", undercloud=True,
                      username="def", password="def", ip_address="12.12.12.12",
                      partition="def-sample")

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


class TestUtils(BaseTaskTestCase):

    def test_validate_ipv4(self):
        self.assertEqual(utils.validate_ipv4('10.43.12.122'), None)
        self.assertRaises(ConfigFileValueError, utils.validate_ipv4, '192.0.20')

    def test_validate_partition(self):
        self.assertEqual(utils.validate_partition(RACK_DEVICE), RACK_DEVICE)
        RACK_DEVICE['partition'] = 'sample_long_partition_name'
        self.assertRaises(ValueError, utils.validate_partition, RACK_DEVICE)
        EMPTY_RACK_DEVICE = {}
        self.assertEqual(utils.validate_partition(EMPTY_RACK_DEVICE), SHARED_RACK_DEVICE)

    def test_validate_params(self):
        SHARED_RACK_INFO = deepcopy(RACK_INFO)
        SHARED_RACK_INFO['partition'] = 'shared'
        self.assertEqual(utils.validate_params(RACK_INFO), SHARED_RACK_INFO)
        self.assertRaises(ConfigFileValueError, utils.validate_params, INVALID_RACK_INFO)

    def test_check_duplicate_entries(self):
        self.assertEqual(utils.check_duplicate_entries(DUPLICATE_DICT), DUP_LIST)
        self.assertEqual(utils.check_duplicate_entries(NON_DUPLICATE_DICT), [])

    def test_convert_to_rack_vthunder_conf(self):
        self.assertRaises(ConfigFileValueError, utils.convert_to_rack_vthunder_conf,
                          DUPLICATE_PROJECT_RACK_DEVICE_LIST)
        self.assertRaises(ConfigFileValueError, utils.convert_to_rack_vthunder_conf,
                          DUPLICATE_PARTITION_RACK_DEVICE_LIST)
        self.assertEqual(utils.convert_to_rack_vthunder_conf(RACK_DEVICE_LIST),
                         RESULT_RACK_DEVICE_LIST)
