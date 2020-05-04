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
try:
    from unittest import mock
except ImportError:
    import mock

from acos_client.v30 import interface

from a10_octavia.common import data_models as a10_data_models
from a10_octavia.controller.worker.tasks import vthunder_tasks as task
from a10_octavia.tests.common import a10constants
from a10_octavia.tests.unit import base

VTHUNDER = a10_data_models.VThunder()
VLAN_ID = 11
DELETE_VLAN = True
TAG_INTERFACE = 1
ETH_DATA = {"action": "enable"}
VE_INTERFACE = {'ifnum': VLAN_ID}


class TestVThunderTasks(base.BaseTaskTestCase):

    def setUp(self):
        super(TestVThunderTasks, self).setUp()
        imp.reload(task)
        self.client_mock = mock.Mock()

    def test_create_vlan_task(self):
        create_vlan = task.CreateVLAN()
        create_vlan.axapi_client = self.client_mock
        self.client_mock.interface.ethernet.get.return_value = ETH_DATA
        self.client_mock.vlan.exists.return_value = False
        create_vlan.execute(VLAN_ID, TAG_INTERFACE, VTHUNDER)
        self.client_mock.vlan.create.assert_called_with(VLAN_ID,
                                                        tagged_eths=[TAG_INTERFACE],
                                                        veth=True)

    def test_revert_create_vlan_task(self):
        create_vlan = task.CreateVLAN()
        create_vlan.axapi_client = self.client_mock
        create_vlan.revert(VLAN_ID, TAG_INTERFACE, VTHUNDER)
        self.client_mock.vlan.delete.assert_called_with(VLAN_ID)

    def test_delete_vlan_task(self):
        delete_vlan = task.DeleteVLAN()
        delete_vlan.axapi_client = self.client_mock
        delete_vlan.execute(DELETE_VLAN, VLAN_ID, VTHUNDER)
        self.client_mock.vlan.delete.assert_called_with(VLAN_ID)

    def test_configure_virt_eth_iface_task(self):
        configure_ve = task.ConfigureVirtEthIface()
        configure_ve.axapi_client = self.client_mock
        configure_ve.execute(VE_INTERFACE, VTHUNDER)
        self.client_mock.interface.ve.update.assert_called_with(
            VE_INTERFACE['ifnum'], dhcp=True, enable=True)

    def test_revert_configure_virt_eth_iface_task(self):
        configure_ve = task.ConfigureVirtEthIface()
        configure_ve.axapi_client = self.client_mock
        configure_ve.revert(VE_INTERFACE, VTHUNDER)
        self.client_mock.interface.ve.delete.assert_called_with(VE_INTERFACE['ifnum'])
