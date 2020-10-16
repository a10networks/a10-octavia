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


import json

from oslo_config import cfg
from oslo_config import fixture as oslo_fixture

from octavia.tests.unit import base

from a10_octavia.common import config_options
from a10_octavia.common import config_types
from a10_octavia.common import data_models as data_models
from a10_octavia.tests.common import a10constants

CONF = cfg.CONF

RACK_DEVICE_1 = {
    "project_id": "project-1",
    "ip_address": "10.0.0.1",
    "device_name": "rack_thunder_1",
    "username": "abc",
    "password": "abc",
    "interface_vlan_map": {
        "device_1": {
            "ethernet_interfaces": [{
                "interface_num": 5,
                "vlan_map": [
                    {"vlan_id": 11, "use_dhcp": "True"},
                    {"vlan_id": 12, "ve_ip": ".10"}
                ]
            }]
        }
    }
}

RACK_DEVICE_2 = {
    "project_id": "project-2",
    "ip_address": "11.0.0.1",
    "device_name": "rack_thunder_2",
    "username": "abc",
    "password": "abc",
    'partition_name': 'def-sample'
}

VTHUNDER_1 = data_models.HardwareThunder(project_id="project-1", device_name="rack_thunder_1",
                                         undercloud=True, username="abc", password="abc",
                                         ip_address="10.0.0.1", partition_name="shared",
                                         device_network_map='"device_1":{"ethernet_interfaces":'
                                         '[{"interface_num": 5, "vlan_map": ['
                                         '{"vlan_id": 11, "use_dhcp": "True"},'
                                         '{"vlan_id": 12, "ve_ip": ".10"}]}]}}')
VTHUNDER_2 = data_models.HardwareThunder(project_id="project-2", device_name="rack_thunder_2",
                                         undercloud=True, username="def", password="def",
                                         ip_address="11.0.0.1", partition_name="def-sample")

RESULT_RACK_DEVICE_LIST = {'project-1': VTHUNDER_1,
                           'project-2': VTHUNDER_2}


class TestConfigTypes(base.TestCase):

    def setUp(self):
        super(TestConfigTypes, self).setUp()
        self.conf = self.useFixture(oslo_fixture.Config(cfg.CONF))

    def tearDown(self):
        super(TestConfigTypes, self).tearDown()
        self.conf.reset()

    def test_rack_device_valid_devices(self):
        self.conf.register_opts(config_options.A10_HARDWARE_THUNDER_OPTS,
                                group=a10constants.A10_HARDWARE_THUNDER_CONF_SECTION)
        devices_str = json.dumps([RACK_DEVICE_1, RACK_DEVICE_2])
        self.conf.config(group=a10constants.A10_HARDWARE_THUNDER_CONF_SECTION,
                         devices=devices_str)
        self.assertIn('project-1', CONF.hardware_thunder.devices)
        self.assertIn('project-2', CONF.hardware_thunder.devices)
        self.assertEqual('rack_thunder_1', CONF.hardware_thunder.devices['project-1'].device_name)
        self.assertEqual('rack_thunder_2', CONF.hardware_thunder.devices['project-2'].device_name)

    def test_rack_device_valid_no_devices(self):
        self.conf.register_opts(config_options.A10_HARDWARE_THUNDER_OPTS,
                                group=a10constants.A10_HARDWARE_THUNDER_CONF_SECTION)
        devices_str = json.dumps([])
        self.conf.config(group=a10constants.A10_HARDWARE_THUNDER_CONF_SECTION,
                         devices=devices_str)
        self.assertEqual(CONF.hardware_thunder.devices, {})

    def test_rack_device_valid_invalid_array(self):
        devices_str = '[' + json.dumps(RACK_DEVICE_1)
        lob_object = config_types.ListOfObjects(bounds=True)
        self.assertRaises(ValueError, lob_object, devices_str)

    def test_rack_device_valid_invalid_dict(self):
        devices_str = '[{' + json.dumps(RACK_DEVICE_1) + ']'
        lob_object = config_types.ListOfObjects(bounds=True)
        self.assertRaises(SyntaxError, lob_object, devices_str)
