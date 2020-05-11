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
try:
    from unittest import mock
except ImportError:
    import mock

from octavia.common import data_models as o_data_models
from octavia.network import data_models as o_net_data_models
from octavia.tests.common import constants as t_constants

from a10_octavia.common import data_models
from a10_octavia.controller.worker.tasks import a10_network_tasks
from a10_octavia.tests.common import a10constants
from a10_octavia.tests.unit import base

MEMBER = o_data_models.Member()
VTHUNDER = data_models.VThunder()
SUBNET = o_net_data_models.Subnet()
PORT = o_net_data_models.Port()


class TestNetworkTasks(base.BaseTaskTestCase):

    def setUp(self):
        super(TestNetworkTasks, self).setUp()
        imp.reload(a10_network_tasks)
        patcher = mock.patch(
            'a10_octavia.controller.worker.tasks.a10_network_tasks.BaseNetworkTask.network_driver')
        self.network_driver_mock = patcher.start()
        self.client_mock = mock.Mock()

    def test_handle_vrrp_floatingip_delta_no_vrrp_floating_ip(self):
        vthunder = copy.deepcopy(VTHUNDER)

        vthunder.vrrp_floating_ip = None
        network_task = a10_network_tasks.HandleVRRPFloatingIPDelta()
        result = network_task.execute(vthunder, MEMBER)
        self.assertEqual(result, None)

    @mock.patch('a10_octavia.common.utils.check_ip_in_subnet_range', return_value=True)
    def test_handle_vrrp_floatingip_delta_no_vrid(self, mock_utils):
        vthunder = copy.deepcopy(VTHUNDER)
        member = copy.deepcopy(MEMBER)
        subnet = copy.deepcopy(SUBNET)
        port = copy.deepcopy(PORT)
        member.subnet_id = a10constants.MOCK_SUBNET_ID
        vrid = None

        vthunder.vrrp_floating_ip = a10constants.MOCK_VRID_FLOATING_IP_1
        subnet.cidr = a10constants.MOCK_SUBNET_CIDR

        mock_network_task = a10_network_tasks.HandleVRRPFloatingIPDelta()
        mock_network_task.axapi_client = self.client_mock
        self.client_mock.vrrpa.vrid.get.return_value = vrid
        self.network_driver_mock.get_subnet.return_value = subnet
        self.network_driver_mock.create_port.return_value = port

        result = mock_network_task.execute(vthunder, member)
        self.network_driver_mock.create_port.assert_called_with(
            member.subnet_id, fixed_ip=a10constants.MOCK_VRID_FLOATING_IP_1)
        self.assertEqual(result, port)

    @mock.patch('a10_octavia.common.utils.check_ip_in_subnet_range', return_value=True)
    def test_handle_vrrp_floatingip_delta_with_vrid_diffrent_fip(self, mock_utils):
        vthunder = copy.deepcopy(VTHUNDER)
        member = copy.deepcopy(MEMBER)
        subnet = copy.deepcopy(SUBNET)
        port = copy.deepcopy(PORT)

        vthunder.vrrp_port_id = a10constants.MOCK_VRRP_PORT_ID
        member.subnet_id = a10constants.MOCK_SUBNET_ID
        vrid = {
            'floating-ip': {'ip-address-cfg': [
                {'ip-address': a10constants.MOCK_VRID_FLOATING_IP_2}]}}

        vthunder.vrrp_floating_ip = a10constants.MOCK_VRID_FLOATING_IP_1
        subnet.cidr = a10constants.MOCK_SUBNET_CIDR

        mock_network_task = a10_network_tasks.HandleVRRPFloatingIPDelta()
        mock_network_task.axapi_client = self.client_mock
        self.client_mock.vrrpa.vrid.get.return_value = vrid
        self.network_driver_mock.get_subnet.return_value = subnet
        self.network_driver_mock.create_port.return_value = port
        self.network_driver_mock.delete_port = mock.Mock()
        result = mock_network_task.execute(vthunder, member)
        self.network_driver_mock.delete_port.assert_called_with(a10constants.MOCK_VRRP_PORT_ID)
        self.network_driver_mock.create_port.assert_called_with(
            member.subnet_id, fixed_ip=a10constants.MOCK_VRID_FLOATING_IP_1)
        self.assertEqual(result, port)

    @mock.patch('a10_octavia.common.utils.check_ip_in_subnet_range', return_value=True)
    def test_handle_vrrp_floatingip_delta_with_vrid_same_fip(self, mock_utils):
        vthunder = copy.deepcopy(VTHUNDER)
        member = copy.deepcopy(MEMBER)
        subnet = copy.deepcopy(SUBNET)
        port = copy.deepcopy(PORT)

        vthunder.vrrp_port_id = a10constants.MOCK_VRRP_PORT_ID
        member.subnet_id = a10constants.MOCK_SUBNET_ID
        vrid = {
            'floating-ip': {'ip-address-cfg': [
                {'ip-address': a10constants.MOCK_VRID_FLOATING_IP_1}]}}

        vthunder.vrrp_floating_ip = a10constants.MOCK_VRID_FLOATING_IP_1
        subnet.cidr = a10constants.MOCK_SUBNET_CIDR

        mock_network_task = a10_network_tasks.HandleVRRPFloatingIPDelta()
        mock_network_task.axapi_client = self.client_mock
        self.client_mock.vrrpa.vrid.get.return_value = vrid
        result = mock_network_task.execute(vthunder, member)
        self.network_driver_mock.delete_port.assert_not_called()
        self.network_driver_mock.create_port.assert_not_called()
        self.assertEqual(result, None)

    @mock.patch('a10_octavia.common.utils.check_ip_in_subnet_range', return_value=False)
    def test_handle_vrrp_floatingip_delta_with_invalid_floating_ip(self, mock_utils):
        vthunder = copy.deepcopy(VTHUNDER)
        member = copy.deepcopy(MEMBER)
        subnet = copy.deepcopy(SUBNET)
        port = copy.deepcopy(PORT)

        vthunder.vrrp_port_id = a10constants.MOCK_VRRP_PORT_ID
        member.subnet_id = a10constants.MOCK_SUBNET_ID
        vrid = {
            'floating-ip': {'ip-address-cfg': [
                {'ip-address': a10constants.MOCK_VRID_FLOATING_IP_2}]}}

        vthunder.vrrp_floating_ip = a10constants.MOCK_VRID_FLOATING_IP_1
        subnet.cidr = a10constants.MOCK_SUBNET_CIDR

        mock_network_task = a10_network_tasks.HandleVRRPFloatingIPDelta()
        mock_network_task.axapi_client = self.client_mock
        self.client_mock.vrrpa.vrid.get.return_value = vrid
        self.network_driver_mock.get_subnet.return_value = subnet
        self.network_driver_mock.create_port.return_value = port
        self.network_driver_mock.delete_port = mock.Mock()
        self.assertRaises(Exception, lambda: mock_network_task.execute(vthunder, member))
        self.network_driver_mock.delete_port.assert_not_called()
        self.network_driver_mock.create_port.assert_not_called()

    def test_handle_vrrp_floatingip_delta_with_vrid_dhcp_fip(self):
        vthunder = copy.deepcopy(VTHUNDER)
        member = copy.deepcopy(MEMBER)
        subnet = copy.deepcopy(SUBNET)
        port = copy.deepcopy(PORT)

        vthunder.vrrp_port_id = a10constants.MOCK_VRRP_PORT_ID
        member.subnet_id = a10constants.MOCK_SUBNET_ID
        vrid = {
            'floating-ip': {'ip-address-cfg': [
                {'ip-address': a10constants.MOCK_VRID_FLOATING_IP_2}]}}

        vthunder.vrrp_floating_ip = 'dhcp'
        subnet.cidr = a10constants.MOCK_SUBNET_CIDR

        mock_network_task = a10_network_tasks.HandleVRRPFloatingIPDelta()
        mock_network_task.axapi_client = self.client_mock
        self.client_mock.vrrpa.vrid.get.return_value = vrid
        self.network_driver_mock.get_subnet.return_value = subnet
        self.network_driver_mock.create_port.return_value = port
        self.network_driver_mock.delete_port = mock.Mock()
        result = mock_network_task.execute(vthunder, member)
        self.network_driver_mock.delete_port.assert_not_called()
        self.network_driver_mock.create_port.assert_called_with(
            member.subnet_id, fixed_ip=None)
        self.assertEqual(result, port)

    def test_handle_vrrp_floatingip_delta_revert(self):
        vthunder = copy.deepcopy(VTHUNDER)
        vthunder.vrrp_floating_ip = a10constants.MOCK_VRID_FLOATING_IP_1
        vthunder.vrrp_port_id = a10constants.MOCK_VRRP_PORT_ID

        mock_network_task = a10_network_tasks.HandleVRRPFloatingIPDelta()
        mock_network_task.axapi_client = self.client_mock
        mock_network_task.revert('SUCCESS', vthunder, MEMBER)
        self.network_driver_mock.delete_port.assert_called_with(a10constants.MOCK_VRRP_PORT_ID)

    def test_handle_vrrp_floatingip_delta_revert_no_floating_ip(self):
        vthunder = copy.deepcopy(VTHUNDER)
        vthunder.vrrp_floating_ip = None
        vthunder.vrrp_port_id = a10constants.MOCK_VRRP_PORT_ID

        mock_network_task = a10_network_tasks.HandleVRRPFloatingIPDelta()
        mock_network_task.axapi_client = self.client_mock
        mock_network_task.revert('SUCCESS', vthunder, MEMBER)
        self.network_driver_mock.delete_port.assert_not_called()

    def test_handle_vrrp_floatingip_delta_revert_no_vrrp_port(self):
        vthunder = copy.deepcopy(VTHUNDER)
        vthunder.vrrp_floating_ip = a10constants.MOCK_VRID_FLOATING_IP_1
        vthunder.vrrp_port_id = None

        mock_network_task = a10_network_tasks.HandleVRRPFloatingIPDelta()
        mock_network_task.axapi_client = self.client_mock
        mock_network_task.revert('SUCCESS', vthunder, MEMBER)
        self.network_driver_mock.delete_port.assert_not_called()
