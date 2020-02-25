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

import acos_client
import mock
from unittest.mock import patch

import octavia.tests.unit.base as base
from octavia.common import data_models as o_data_models
from octavia.tests.common import constants as t_constants

from a10_octavia.common.data_models import VThunder
from a10_octavia.controller.worker.tasks import vthunder_tasks
from a10_octavia.network.data_models import Subport
from a10_octavia.tests.common import a10constants as a10_test_constants

AMPHORA = o_data_models.Amphora(id=t_constants.MOCK_AMP_ID1)
LB = o_data_models.LoadBalancer(amphorae=[AMPHORA])
SUBPORT = Subport(segmentation_id=a10_test_constants.SEGMENTATION_ID)
VTHUNDER = VThunder()


class TestVThunderTasks(base.TestCase):

    def setUp(self):
        patcher = patch(
            'a10_octavia.controller.worker.tasks.common.BaseVThunderTask.client_factory')
        self.client_factory_mock = patcher.start()
        self.client_factory_mock.return_value = mock.Mock()
        super(TestVThunderTasks, self).setUp()

    @mock.patch.object(acos_client.v30.interface.VirtualEthernet, 'delete')
    def test_delete_virt_eth_ifaces_with_single_iface(self, acos_client_mock):
        ve_interfaces = {t_constants.MOCK_AMP_ID1: {
            a10_test_constants.VLAN_ID: a10_test_constants.SUBNET_IP}}
        eth = vthunder_tasks.DeleteVirtEthIfaces()
        eth.execute(ve_interfaces, LB, VTHUNDER)
        acos_client_mock.assert_called_with(a10_test_constants.VLAN_ID)

    @mock.patch.object(acos_client.v30.interface.VirtualEthernet, 'delete')
    def test_delete_virt_eth_ifaces_with_no_iface(self, acos_client_mock):
        ve_interfaces_none = None
        eth = vthunder_tasks.DeleteVirtEthIfaces()
        eth.execute(ve_interfaces_none, LB, VTHUNDER)
        acos_client_mock.assert_not_called()

    @mock.patch('acos_client.v30.vlan.Vlan')
    def test_untag_ethernet_ifaces_with_single_virt_iface(self, acos_client_mock):
        mock_obj = acos_client_mock.return_value
        deleted_ports = {t_constants.MOCK_AMP_ID1: [SUBPORT]}
        eth = vthunder_tasks.UnTagEthernetIfaces()
        eth.execute(deleted_ports, LB, VTHUNDER)
        mock_obj.delete.assert_called_with(a10_test_constants.SEGMENTATION_ID)

    @mock.patch('acos_client.v30.vlan.Vlan')
    def test_untag_ethernet_ifaces_with_no_virt_iface(self, acos_client_mock):
        mock_obj = acos_client_mock.return_value
        empty_deleted_ports = {t_constants.MOCK_AMP_ID1: []}
        eth = vthunder_tasks.UnTagEthernetIfaces()
        eth.execute(empty_deleted_ports, LB, VTHUNDER)
        mock_obj.delete.assert_not_called()
