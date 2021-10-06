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
from oslo_config import cfg
from oslo_config import fixture as oslo_fixture

from octavia.common import data_models as o_data_models
from octavia.network import data_models as o_net_data_models

from a10_octavia.common import config_options
from a10_octavia.common import data_models
from a10_octavia.controller.worker.tasks import a10_network_tasks
from a10_octavia.tests.common import a10constants
from a10_octavia.tests.unit import base

MEMBER = o_data_models.Member(subnet_id=a10constants.MOCK_SUBNET_ID)
POOL = o_data_models.Pool()
VTHUNDER = data_models.VThunder()
SUBNET = o_net_data_models.Subnet()
PORT = o_net_data_models.Port()
VRID = data_models.VRID()
VRID_VALUE = 0
SUBNET_1 = o_net_data_models.Subnet(id=a10constants.MOCK_SUBNET_ID)
VRID_1 = data_models.VRID(id=1, subnet_id=a10constants.MOCK_SUBNET_ID)
NAT_POOL = data_models.NATPool(port_id=a10constants.MOCK_PORT_ID)
NAT_FLAVOR = {"pool_name": "p1", "start_address": "1.1.1.1", "end_address": "1.1.1.2"}
HW_THUNDER = data_models.HardwareThunder(
    project_id=a10constants.MOCK_PROJECT_ID,
    device_name="rack_thunder_1",
    undercloud=True,
    username="abc",
    password="abc",
    ip_address="10.10.10.10",
    partition_name="shared")
HW_THUNDER2 = data_models.HardwareThunder(
    project_id=a10constants.MOCK_PROJECT_ID,
    device_name="rack_thunder_2",
    undercloud=True,
    username="abc",
    password="abc",
    ip_address="10.10.10.11",
    partition_name="shared",
    vrid_floating_ip="192.168.8.126")
EXISTING_FIP_SHARED_PARTITION = {
    u'vrid': {u'blade-parameters': {
        u'priority': 150, u'uuid': u'41e54b26-bc4f-11eb-bd71-525400895118',
        u'a10-url': u'/axapi/v3/vrrp-a/vrid/0/blade-parameters'},
        u'uuid': u'41e5439c-bc4f-11eb-bd71-525400895118', u'floating-ip': {
            u'ip-address-cfg': [{
                u'ip-address': u'192.168.8.140'}, {u'ip-address': u'192.168.9.140'}]},
            u'vrid-val': 0, u'preempt-mode': {u'threshold': 0, u'disable': 0},
            u'a10-url': u'/axapi/v3/vrrp-a/vrid/0'}
}
EXISTING_FIP_L3V_PARTITION = {
    u'vrid': {u'blade-parameters': {
        u'priority': 150, u'uuid': u'41e54b26-bc4f-11eb-bd71-525400895118',
        u'a10-url': u'/axapi/v3/vrrp-a/vrid/0/blade-parameters'},
        u'uuid': u'41e5439c-bc4f-11eb-bd71-525400895118', u'floating-ip': {
            u'ip-address-part-cfg': [{
                u'ip-address-partition': u'192.168.8.140'},
                {u'ip-address-partition': u'192.168.9.140'}]},
            u'vrid-val': 0, u'preempt-mode': {u'threshold': 0, u'disable': 0},
            u'a10-url': u'/axapi/v3/vrrp-a/vrid/0'}
}


class MockIP(object):
    def __init__(self, ip_address):
        self.ip_address = ip_address


class TestNetworkTasks(base.BaseTaskTestCase):

    def setUp(self):
        super(TestNetworkTasks, self).setUp()
        imp.reload(a10_network_tasks)
        patcher = mock.patch(
            'a10_octavia.controller.worker.tasks.a10_network_tasks.BaseNetworkTask.network_driver')
        self.network_driver_mock = patcher.start()
        self.client_mock = mock.Mock()
        self.conf = self.useFixture(oslo_fixture.Config(cfg.CONF))
        self.conf.register_opts(config_options.A10_GLOBAL_OPTS,
                                group=a10constants.A10_GLOBAL_OPTS)

    def tearDown(self):
        super(TestNetworkTasks, self).tearDown()
        self.conf.reset()

    @mock.patch(
        'a10_octavia.common.utils.get_vrid_floating_ip_for_project',
        return_value=None)
    def test_HandleVRIDFloatingIP_noop_vrrpa_config_not_specified(
            self, mock_utils):
        mock_network_task = a10_network_tasks.HandleVRIDFloatingIP()
        mock_network_task.axapi_client = self.client_mock
        subnet = copy.deepcopy(SUBNET_1)
        subnet.cidr = a10constants.MOCK_SUBNET_CIDR
        vthunder_config = copy.deepcopy(HW_THUNDER)
        result = mock_network_task.execute(VTHUNDER, MEMBER, [], subnet, vthunder_config)
        self.assertEqual(result, [])

    @mock.patch('a10_octavia.common.utils.get_vrid_floating_ip_for_project',
                return_value=a10constants.MOCK_VRID_FLOATING_IP_1)
    @mock.patch('a10_octavia.common.utils.get_patched_ip_address',
                return_value=a10constants.MOCK_VRID_FLOATING_IP_1)
    def test_HandleVRIDFloatingIP_create_floating_ip_in_shared_partition_with_static_ip(
            self, mock_patched_ip, mock_floating_ip):
        member = copy.deepcopy(MEMBER)
        member.subnet_id = SUBNET_1.id
        vthunder = copy.deepcopy(VTHUNDER)
        vthunder.ip_address = '10.0.0.1'
        subnet = copy.deepcopy(SUBNET_1)
        subnet.cidr = a10constants.MOCK_SUBNET_CIDR
        vthunder_config = copy.deepcopy(HW_THUNDER)
        port = copy.deepcopy(PORT)
        port.fixed_ips.append(MockIP(a10constants.MOCK_VRID_FLOATING_IP_1))
        self.client_mock.vrrpa.get.return_value = EXISTING_FIP_SHARED_PARTITION
        mock_network_task = a10_network_tasks.HandleVRIDFloatingIP()
        mock_network_task.axapi_client = self.client_mock
        self.network_driver_mock.get_subnet.return_value = subnet
        self.network_driver_mock.allocate_vrid_fip.return_value = port
        self.conf.config(group=a10constants.A10_GLOBAL_OPTS,
                         vrid=VRID_VALUE)
        mock_network_task.execute(vthunder, member, [], subnet, vthunder_config)
        self.network_driver_mock.allocate_vrid_fip.assert_called_with(
            mock.ANY, None, mock.ANY,
            fixed_ip=a10constants.MOCK_VRID_FLOATING_IP_1)
        self.client_mock.vrrpa.update.assert_called_with(
            VRID_VALUE, floating_ips=[a10constants.MOCK_VRID_FLOATING_IP_1],
            is_partition=False)

    @mock.patch('a10_octavia.common.utils.get_patched_ip_address',
                return_value=a10constants.MOCK_VRID_FLOATING_IP_1)
    def test_HandleVRIDFloatingIP_create_floating_ip_with_device_name_flavor(
            self, mock_patched_ip):
        member = copy.deepcopy(MEMBER)
        member.subnet_id = SUBNET_1.id
        vthunder = copy.deepcopy(VTHUNDER)
        vthunder.ip_address = '10.0.0.1'
        subnet = copy.deepcopy(SUBNET_1)
        subnet.cidr = a10constants.MOCK_SUBNET_CIDR
        vthunder_config = copy.deepcopy(HW_THUNDER2)
        port = copy.deepcopy(PORT)
        port.fixed_ips.append(MockIP(a10constants.MOCK_VRID_FLOATING_IP_1))
        mock_network_task = a10_network_tasks.HandleVRIDFloatingIP()
        mock_network_task.axapi_client = self.client_mock
        self.network_driver_mock.get_subnet.return_value = subnet
        self.network_driver_mock.allocate_vrid_fip.return_value = port
        self.client_mock.vrrpa.get.return_value = EXISTING_FIP_SHARED_PARTITION
        self.conf.config(group=a10constants.A10_GLOBAL_OPTS,
                         vrid=VRID_VALUE)
        mock_network_task.execute(vthunder, member, [], subnet,
                                  vthunder_config, use_device_flavor=True)
        mock_network_task.axapi_client.get_vrid_floating_ip_for_project.assert_not_called()
        self.client_mock.vrrpa.update.assert_called_with(
            VRID_VALUE, floating_ips=[a10constants.MOCK_VRID_FLOATING_IP_1],
            is_partition=False)

    @mock.patch('a10_octavia.common.utils.get_vrid_floating_ip_for_project',
                return_value=a10constants.MOCK_VRID_FLOATING_IP_1)
    @mock.patch('a10_octavia.common.utils.get_patched_ip_address',
                return_value=a10constants.MOCK_VRID_FLOATING_IP_1)
    @mock.patch('a10_octavia.controller.worker.tasks.a10_network_tasks.a10_task_utils')
    def test_HandleVRIDFloatingIP_create_floating_ip_in_specified_partition_with_static_ip(
            self, mock_utils, mock_patched_ip, get_floating_ip):
        member = copy.deepcopy(MEMBER)
        member.subnet_id = SUBNET_1.id
        subnet = copy.deepcopy(SUBNET_1)
        subnet.cidr = a10constants.MOCK_SUBNET_CIDR
        vthunder_config = copy.deepcopy(HW_THUNDER)
        port = copy.deepcopy(PORT)
        port.fixed_ips.append(MockIP(a10constants.MOCK_VRID_FLOATING_IP_1))
        vthunder = copy.deepcopy(VTHUNDER)
        vthunder.partition_name = 'partition_1'
        vthunder.ip_address = '10.0.0.1'
        mock_network_task = a10_network_tasks.HandleVRIDFloatingIP()
        mock_network_task.axapi_client = self.client_mock
        self.network_driver_mock.get_subnet.return_value = subnet
        self.network_driver_mock.allocate_vrid_fip.return_value = port
        self.client_mock.vrrpa.get.return_value = EXISTING_FIP_L3V_PARTITION
        self.conf.config(group=a10constants.A10_GLOBAL_OPTS,
                         vrid=VRID_VALUE)
        mock_network_task.execute(vthunder, member, [], subnet, vthunder_config)
        self.network_driver_mock.allocate_vrid_fip.assert_called_with(
            mock.ANY, None, mock.ANY,
            fixed_ip=a10constants.MOCK_VRID_FLOATING_IP_1)
        self.client_mock.vrrpa.update.assert_called_with(
            VRID_VALUE, floating_ips=[
                a10constants.MOCK_VRID_FLOATING_IP_1], is_partition=True)

    @mock.patch(
        'a10_octavia.common.utils.check_ip_in_subnet_range',
        return_value=False)
    @mock.patch(
        'a10_octavia.common.utils.get_vrid_floating_ip_for_project',
        return_value='dhcp')
    def test_HandleVRIDFloatingIP_create_floating_ip_in_shared_partition_with_dhcp(
            self, get_floating_ip, check_subnet):
        member = copy.deepcopy(MEMBER)
        member.subnet_id = SUBNET_1.id
        vthunder = copy.deepcopy(VTHUNDER)
        vthunder.ip_address = '10.0.0.1'
        subnet = copy.deepcopy(SUBNET_1)
        subnet.cidr = a10constants.MOCK_SUBNET_CIDR
        vthunder_config = copy.deepcopy(HW_THUNDER)
        port = copy.deepcopy(PORT)
        port.fixed_ips.append(MockIP(a10constants.MOCK_VRID_FLOATING_IP_1))
        mock_network_task = a10_network_tasks.HandleVRIDFloatingIP()
        mock_network_task.axapi_client = self.client_mock
        self.network_driver_mock.get_subnet.return_value = subnet
        self.network_driver_mock.allocate_vrid_fip.return_value = port
        self.client_mock.vrrpa.get.return_value = EXISTING_FIP_SHARED_PARTITION
        self.conf.config(group=a10constants.A10_GLOBAL_OPTS,
                         vrid=VRID_VALUE)
        mock_network_task.execute(vthunder, member, [VRID_1], subnet, vthunder_config)
        self.network_driver_mock.allocate_vrid_fip.assert_called_with(
            mock.ANY, None, None, fixed_ip=None)
        self.client_mock.vrrpa.update.assert_called_with(
            VRID_VALUE, floating_ips=[a10constants.MOCK_VRID_FLOATING_IP_1],
            is_partition=False)

    @mock.patch(
        'a10_octavia.common.utils.check_ip_in_subnet_range',
        return_value=False)
    @mock.patch(
        'a10_octavia.common.utils.get_vrid_floating_ip_for_project',
        return_value='dhcp')
    def test_HandleVRIDFloatingIP_create_floating_ip_in_specified_partition_with_dhcp(
            self, get_floating_ip, check_subnet):
        member = copy.deepcopy(MEMBER)
        member.subnet_id = SUBNET_1.id
        subnet = copy.deepcopy(SUBNET_1)
        subnet.cidr = a10constants.MOCK_SUBNET_CIDR
        vthunder_config = copy.deepcopy(HW_THUNDER)
        port = copy.deepcopy(PORT)
        port.fixed_ips.append(MockIP(a10constants.MOCK_VRID_FLOATING_IP_1))
        vthunder = copy.deepcopy(VTHUNDER)
        vthunder.partition_name = 'partition_1'
        vthunder.ip_address = '10.0.0.1'
        mock_network_task = a10_network_tasks.HandleVRIDFloatingIP()
        mock_network_task.axapi_client = self.client_mock
        self.network_driver_mock.get_subnet.return_value = subnet
        self.network_driver_mock.allocate_vrid_fip.return_value = port
        self.client_mock.vrrpa.get.return_value = EXISTING_FIP_L3V_PARTITION
        self.conf.config(group=a10constants.A10_GLOBAL_OPTS,
                         vrid=VRID_VALUE)
        mock_network_task.execute(vthunder, member, [VRID_1], subnet, vthunder_config)
        self.network_driver_mock.allocate_vrid_fip.assert_called_with(
            mock.ANY, None, None, fixed_ip=None)
        self.client_mock.vrrpa.update.assert_called_with(
            VRID_VALUE, floating_ips=[
                a10constants.MOCK_VRID_FLOATING_IP_1], is_partition=True)

    @mock.patch(
        'a10_octavia.common.utils.get_vrid_floating_ip_for_project',
        return_value=None)
    def test_HandleVRIDFloatingIP_delete_fip_entries_device_fip_given_but_no_fip_in_conf(
            self, mock_utils):
        vrid = copy.deepcopy(VRID_1)
        vrid.vrid_port_id = a10constants.MOCK_VRRP_PORT_ID
        vrid.vrid = VRID_VALUE
        vthunder_config = copy.deepcopy(HW_THUNDER)
        mock_network_task = a10_network_tasks.HandleVRIDFloatingIP()
        mock_network_task.axapi_client = self.client_mock
        result = mock_network_task.execute(VTHUNDER, MEMBER, [vrid], SUBNET_1, vthunder_config)
        self.network_driver_mock.delete_port.assert_called_with(
            vrid.vrid_port_id)
        self.client_mock.vrrpa.update.assert_called_with(
            vrid.vrid, floating_ips=[], is_partition=False)
        self.assertEqual(result, [])

    @mock.patch('a10_octavia.common.utils.get_vrid_floating_ip_for_project',
                return_value=a10constants.MOCK_VRID_FLOATING_IP_1)
    @mock.patch('a10_octavia.common.utils.get_patched_ip_address',
                return_value=a10constants.MOCK_VRID_FLOATING_IP_1)
    def test_HandleVRIDFloatingIP_noop_device_fip_and_conf_fip_both_given_same_ip(
            self, mock_patched_ip, get_floating_ip):
        vrid = copy.deepcopy(VRID_1)
        vrid.vrid_floating_ip = a10constants.MOCK_VRID_FLOATING_IP_1
        vrid.vrid = VRID_VALUE
        vthunder = copy.deepcopy(VTHUNDER)
        vthunder.ip_address = '10.0.0.1'
        member = copy.deepcopy(MEMBER)
        member.subnet_id = a10constants.MOCK_SUBNET_ID
        subnet = copy.deepcopy(SUBNET_1)
        subnet.cidr = a10constants.MOCK_SUBNET_CIDR
        port = copy.deepcopy(PORT)
        vthunder_config = copy.deepcopy(HW_THUNDER)
        port.fixed_ips.append(MockIP(a10constants.MOCK_VRID_FLOATING_IP_1))
        mock_network_task = a10_network_tasks.HandleVRIDFloatingIP()
        mock_network_task.axapi_client = self.client_mock
        self.network_driver_mock.get_subnet.return_value = subnet
        self.client_mock.vrrpa.get.return_value = EXISTING_FIP_SHARED_PARTITION
        mock_network_task.execute(vthunder, member, [vrid], subnet, vthunder_config)
        self.network_driver_mock.allocate_vrid_fip.assert_not_called()
        self.client_mock.vrrpa.update.assert_not_called()

    @mock.patch('a10_octavia.common.utils.get_vrid_floating_ip_for_project',
                return_value=a10constants.MOCK_VRID_FLOATING_IP_2)
    @mock.patch('a10_octavia.common.utils.get_patched_ip_address',
                return_value=a10constants.MOCK_VRID_FLOATING_IP_2)
    @mock.patch('a10_octavia.controller.worker.tasks.a10_network_tasks.a10_task_utils')
    def test_HandleVRIDFloatingIP_replace_floating_ip_in_shared_partition_with_static_ip(
            self, mock_utils, mock_patched_ip, get_floating_ip):
        vrid = copy.deepcopy(VRID_1)
        vthunder = copy.deepcopy(VTHUNDER)
        vthunder.ip_address = '10.0.0.1'
        vrid.vrid_floating_ip = a10constants.MOCK_VRID_FLOATING_IP_1
        vrid.vrid = VRID_VALUE
        vrid.vrid_port_id = a10constants.MOCK_VRRP_PORT_ID
        member = copy.deepcopy(MEMBER)
        member.subnet_id = a10constants.MOCK_SUBNET_ID
        subnet = copy.deepcopy(SUBNET_1)
        subnet.cidr = a10constants.MOCK_SUBNET_CIDR
        port = copy.deepcopy(PORT)
        vthunder_config = copy.deepcopy(HW_THUNDER)
        port.fixed_ips.append(MockIP(a10constants.MOCK_VRID_FLOATING_IP_2))
        mock_network_task = a10_network_tasks.HandleVRIDFloatingIP()
        mock_network_task.axapi_client = self.client_mock
        self.network_driver_mock.get_subnet.return_value = subnet
        self.network_driver_mock.allocate_vrid_fip.return_value = port
        self.client_mock.vrrpa.get.return_value = EXISTING_FIP_SHARED_PARTITION
        self.conf.config(group=a10constants.A10_GLOBAL_OPTS,
                         vrid=VRID_VALUE)
        mock_network_task.execute(vthunder, member, [vrid], subnet, vthunder_config)
        self.network_driver_mock.allocate_vrid_fip.assert_called_with(
            vrid, subnet.network_id, mock.ANY,
            fixed_ip=a10constants.MOCK_VRID_FLOATING_IP_2)
        self.client_mock.vrrpa.update.assert_called_with(
            VRID_VALUE, floating_ips=[a10constants.MOCK_VRID_FLOATING_IP_2],
            is_partition=False)
        self.network_driver_mock.delete_port.assert_called_with(
            a10constants.MOCK_VRRP_PORT_ID)

    @mock.patch('a10_octavia.common.utils.get_vrid_floating_ip_for_project',
                return_value=a10constants.MOCK_VRID_FLOATING_IP_2)
    @mock.patch('a10_octavia.common.utils.get_patched_ip_address',
                return_value=a10constants.MOCK_VRID_FLOATING_IP_2)
    @mock.patch('a10_octavia.controller.worker.tasks.a10_network_tasks.a10_task_utils')
    def test_HandleVRIDFloatingIP_replace_floating_ip_in_specified_partition_with_static_ip(
            self, mock_utils, mock_patched_ip, get_floating_ip):
        vrid = copy.deepcopy(VRID_1)
        vrid.vrid_floating_ip = a10constants.MOCK_VRID_FLOATING_IP_1
        vrid.vrid = VRID_VALUE
        vrid.vrid_port_id = a10constants.MOCK_VRRP_PORT_ID
        member = copy.deepcopy(MEMBER)
        member.subnet_id = a10constants.MOCK_SUBNET_ID
        subnet = copy.deepcopy(SUBNET_1)
        subnet.cidr = a10constants.MOCK_SUBNET_CIDR
        port = copy.deepcopy(PORT)
        vthunder_config = copy.deepcopy(HW_THUNDER)
        port.fixed_ips.append(MockIP(a10constants.MOCK_VRID_FLOATING_IP_2))
        vthunder = copy.deepcopy(VTHUNDER)
        vthunder.ip_address = '10.0.0.1'
        vthunder.partition_name = 'partition_1'
        mock_network_task = a10_network_tasks.HandleVRIDFloatingIP()
        mock_network_task.axapi_client = self.client_mock
        self.network_driver_mock.get_subnet.return_value = subnet
        self.network_driver_mock.allocate_vrid_fip.return_value = port
        self.client_mock.vrrpa.get.return_value = EXISTING_FIP_L3V_PARTITION
        self.conf.config(group=a10constants.A10_GLOBAL_OPTS,
                         vrid=VRID_VALUE)
        mock_network_task.execute(vthunder, member, [vrid], subnet, vthunder_config)
        self.network_driver_mock.allocate_vrid_fip.assert_called_with(
            vrid, None, mock.ANY,
            fixed_ip=a10constants.MOCK_VRID_FLOATING_IP_2)
        self.client_mock.vrrpa.update.assert_called_with(
            VRID_VALUE, floating_ips=[
                a10constants.MOCK_VRID_FLOATING_IP_2], is_partition=True)
        self.network_driver_mock.delete_port.assert_called_with(
            a10constants.MOCK_VRRP_PORT_ID)

    @mock.patch(
        'a10_octavia.common.utils.get_vrid_floating_ip_for_project',
        return_value='dhcp')
    def test_HandleVRIDFloatingIP_noop_given_same_subnet_with_conf_fip_set_to_dhcp(
            self, get_floating_ip):
        vrid = copy.deepcopy(VRID_1)
        vthunder = copy.deepcopy(VTHUNDER)
        vthunder.ip_address = '10.0.0.1'
        vrid.vrid_floating_ip = a10constants.MOCK_VRID_FLOATING_IP_1
        vrid.vrid = VRID_VALUE
        vrid.vrid_port_id = a10constants.MOCK_VRRP_PORT_ID
        member = copy.deepcopy(MEMBER)
        member.subnet_id = a10constants.MOCK_SUBNET_ID
        subnet = copy.deepcopy(SUBNET_1)
        subnet.cidr = a10constants.MOCK_SUBNET_CIDR
        vthunder_config = copy.deepcopy(HW_THUNDER)
        mock_network_task = a10_network_tasks.HandleVRIDFloatingIP()
        mock_network_task.axapi_client = self.client_mock
        self.network_driver_mock.get_subnet.return_value = subnet
        self.client_mock.vrrpa.get.return_value = EXISTING_FIP_SHARED_PARTITION
        fip_port = mock_network_task.execute(vthunder, member, [vrid], subnet, vthunder_config)
        self.network_driver_mock.allocate_vrid_fip.assert_not_called()
        self.network_driver_mock.delete_port.assert_not_called()
        self.assertEqual(fip_port, [vrid])

    @mock.patch(
        'a10_octavia.common.utils.check_ip_in_subnet_range',
        return_value=False)
    @mock.patch(
        'a10_octavia.common.utils.get_vrid_floating_ip_for_project',
        return_value='dhcp')
    @mock.patch('a10_octavia.controller.worker.tasks.a10_network_tasks.a10_task_utils')
    def test_HandleVRIDFloatingIP_replace_floating_ip_diff_subnet_in_shared_part_conf_fip_set_dhcp(
            self, mock_utils, get_floating_ip, check_subnet):
        vrid = copy.deepcopy(VRID_1)
        vthunder = copy.deepcopy(VTHUNDER)
        vthunder.ip_address = '10.0.0.1'
        vrid.vrid_floating_ip = a10constants.MOCK_VRID_FLOATING_IP_1
        vrid.vrid = VRID_VALUE
        vrid.vrid_port_id = a10constants.MOCK_VRRP_PORT_ID
        member = copy.deepcopy(MEMBER)
        member.subnet_id = a10constants.MOCK_SUBNET_ID
        subnet = copy.deepcopy(SUBNET_1)
        subnet.cidr = a10constants.MOCK_SUBNET_CIDR
        port = copy.deepcopy(PORT)
        vthunder_config = copy.deepcopy(HW_THUNDER)
        port.fixed_ips.append(MockIP(a10constants.MOCK_VRID_FLOATING_IP_1))

        mock_network_task = a10_network_tasks.HandleVRIDFloatingIP()
        mock_network_task.axapi_client = self.client_mock
        self.network_driver_mock.get_subnet.return_value = subnet
        self.network_driver_mock.allocate_vrid_fip.return_value = port
        self.client_mock.vrrpa.get.return_value = EXISTING_FIP_SHARED_PARTITION
        self.conf.config(group=a10constants.A10_GLOBAL_OPTS,
                         vrid=VRID_VALUE)
        mock_network_task.execute(vthunder, member, [vrid], subnet, vthunder_config)
        self.network_driver_mock.allocate_vrid_fip.assert_called_with(
            vrid, subnet.network_id, mock.ANY, fixed_ip=None)
        self.client_mock.vrrpa.update.assert_called_with(
            VRID_VALUE, floating_ips=[a10constants.MOCK_VRID_FLOATING_IP_1],
            is_partition=False)
        self.network_driver_mock.delete_port.assert_called_with(
            a10constants.MOCK_VRRP_PORT_ID)

    @mock.patch('a10_octavia.common.utils.check_ip_in_subnet_range',
                return_value=False)
    @mock.patch('a10_octavia.common.utils.get_vrid_floating_ip_for_project',
                return_value='dhcp')
    @mock.patch('a10_octavia.controller.worker.tasks.a10_network_tasks.a10_task_utils')
    def test_HandleVRIDFloatingIP_replace_floating_ip_diff_subnet_in_set_part_conf_fip_set_dhcp(
            self, mock_utils, get_floating_ip, check_subnet):
        vrid = copy.deepcopy(VRID_1)
        vrid.vrid_floating_ip = a10constants.MOCK_VRID_FLOATING_IP_1
        vrid.vrid = VRID_VALUE
        vrid.vrid_port_id = a10constants.MOCK_VRRP_PORT_ID
        member = copy.deepcopy(MEMBER)
        member.subnet_id = a10constants.MOCK_SUBNET_ID
        subnet = copy.deepcopy(SUBNET_1)
        subnet.cidr = a10constants.MOCK_SUBNET_CIDR
        port = copy.deepcopy(PORT)
        vthunder_config = copy.deepcopy(HW_THUNDER)
        port.fixed_ips.append(MockIP(a10constants.MOCK_VRID_FLOATING_IP_1))
        vthunder = copy.deepcopy(VTHUNDER)
        vthunder.partition_name = 'partition_1'
        vthunder.ip_address = '10.0.0.1'
        mock_network_task = a10_network_tasks.HandleVRIDFloatingIP()
        mock_network_task.axapi_client = self.client_mock
        self.network_driver_mock.get_subnet.return_value = subnet
        self.network_driver_mock.allocate_vrid_fip.return_value = port
        self.client_mock.vrrpa.get.return_value = EXISTING_FIP_L3V_PARTITION
        self.conf.config(group=a10constants.A10_GLOBAL_OPTS,
                         vrid=VRID_VALUE)
        mock_network_task.execute(vthunder, member, [vrid], subnet, vthunder_config)
        self.network_driver_mock.allocate_vrid_fip.assert_called_with(
            vrid, subnet.network_id, mock.ANY, fixed_ip=None)
        self.client_mock.vrrpa.update.assert_called_with(
            VRID_VALUE, floating_ips=[
                a10constants.MOCK_VRID_FLOATING_IP_1], is_partition=True)
        self.network_driver_mock.delete_port.assert_called_with(
            a10constants.MOCK_VRRP_PORT_ID)

    @mock.patch('a10_octavia.common.utils.get_vrid_floating_ip_for_project',
                return_value=a10constants.MOCK_VRID_PARTIAL_FLOATING_IP)
    @mock.patch('a10_octavia.controller.worker.tasks.a10_network_tasks.a10_task_utils')
    def test_HandleVRIDFloatingIP_creating_floating_ip_conf_fip_is_partial(
            self, get_floating_ip, mock_utils):
        member = copy.deepcopy(MEMBER)
        member.subnet_id = a10constants.MOCK_SUBNET_ID
        vthunder = copy.deepcopy(VTHUNDER)
        vthunder.ip_address = '10.0.0.1'
        subnet = copy.deepcopy(SUBNET_1)
        subnet.cidr = a10constants.MOCK_SUBNET_CIDR
        port = copy.deepcopy(PORT)
        vthunder_config = copy.deepcopy(HW_THUNDER)
        port.fixed_ips.append(MockIP(a10constants.MOCK_VRID_FULL_FLOATING_IP))

        mock_network_task = a10_network_tasks.HandleVRIDFloatingIP()
        mock_network_task.axapi_client = self.client_mock
        self.network_driver_mock.get_subnet.return_value = subnet
        self.network_driver_mock.allocate_vrid_fip.return_value = port
        self.client_mock.vrrpa.get.return_value = EXISTING_FIP_SHARED_PARTITION
        self.conf.config(group=a10constants.A10_GLOBAL_OPTS,
                         vrid=VRID_VALUE)
        mock_network_task.execute(vthunder, member, [VRID_1], subnet, vthunder_config)
        self.network_driver_mock.allocate_vrid_fip.assert_called_with(
            mock.ANY, subnet.network_id, mock.ANY,
            fixed_ip=a10constants.MOCK_VRID_FULL_FLOATING_IP)
        self.client_mock.vrrpa.update.assert_called_with(
            VRID_VALUE, floating_ips=[a10constants.MOCK_VRID_FULL_FLOATING_IP],
            is_partition=False)

    @mock.patch('a10_octavia.controller.worker.tasks.a10_network_tasks.a10_task_utils')
    def test_DeleteMemberVRIDPort_delete_vrid_ip_member_count_equals_one(self, mock_utils):
        mock_network_task = a10_network_tasks.DeleteVRIDPort()
        vrid = copy.deepcopy(VRID_1)
        vrid.vrid_port_id = a10constants.MOCK_VRRP_PORT_ID
        vrid.vrid = VRID_VALUE
        mock_network_task.axapi_client = self.client_mock
        self.client_mock.vrrpa.get.return_value = EXISTING_FIP_SHARED_PARTITION
        result = mock_network_task.execute(VTHUNDER, [vrid], SUBNET_1, False,
                                           0, 1, 0, 0, MEMBER)
        self.network_driver_mock.deallocate_vrid_fip.assert_called_with(
            vrid, mock.ANY, mock.ANY)
        self.client_mock.vrrpa.update.assert_called_with(
            vrid.vrid, floating_ips=[])
        self.assertEqual(result, (vrid, True))

    def test_DeleteMemberVRIDPort_member_count_lb_count(self):
        mock_network_task = a10_network_tasks.DeleteVRIDPort()
        mock_network_task.axapi_client = self.client_mock
        result = mock_network_task.execute(VTHUNDER, [VRID_1], SUBNET_1, False,
                                           1, 1, 0, 0, MEMBER)
        self.network_driver_mock.deallocate_vrid_fip.assert_not_called()
        self.client_mock.vrrpa.delete.assert_not_called()
        self.assertEqual(result, (None, False))

    def delete_multi_vrid_port_against_subnet_not_used(self):
        mock_network_task = a10_network_tasks.DeleteVRIDPort()
        vrid = copy.deepcopy(VRID_1)
        vrid.vrid_port_id = a10constants.MOCK_VRRP_PORT_ID
        vrid.vrid = VRID_VALUE
        mock_network_task.axapi_client = self.client_mock
        result = mock_network_task.execute(VTHUNDER, [vrid], [SUBNET_1])
        self.network_driver_mock.delete_port.assert_called_with(
            a10constants.MOCK_VRRP_PORT_ID)
        self.client_mock.vrrpa.update.assert_called_with(
            vrid.vrid, floating_ips=[], is_partiton=False)
        self.assertEqual(result, [])

    def delete_multi_vrid_port_against_all_subnet_used(self):
        mock_network_task = a10_network_tasks.DeleteVRIDPort()
        vrid = copy.deepcopy(VRID_1)
        vrid.vrid_port_id = a10constants.MOCK_VRRP_PORT_ID
        vrid.vrid = VRID_VALUE
        mock_network_task.axapi_client = self.client_mock
        result = mock_network_task.execute(VTHUNDER, [vrid], [])
        self.network_driver_mock.delete_port.assert_not_called()
        self.client_mock.vrrpa.update.assert_not_called()
        self.assertEqual(result, None)

    @mock.patch('a10_octavia.controller.worker.tasks.a10_network_tasks.a10_task_utils')
    def test_reserve_subnet_addr_for_member(self, mock_utils):
        mock_network_task = a10_network_tasks.ReserveSubnetAddressForMember()
        mock_network_task.network_driver = self.client_mock
        mock_network_task.execute(MEMBER, NAT_FLAVOR)
        self.client_mock.reserve_subnet_addresses.assert_called_with(
            MEMBER.subnet_id, ["1.1.1.1", "1.1.1.2"], mock.ANY)

    def test_release_subnet_addr_referenced(self):
        mock_network_task = a10_network_tasks.ReleaseSubnetAddressForMember()
        NAT_POOL.member_ref_count = 2
        ret_val = mock_network_task.execute(MEMBER, NAT_FLAVOR, NAT_POOL)
        self.assertEqual(ret_val, None)

    @mock.patch('a10_octavia.controller.worker.tasks.a10_network_tasks.a10_task_utils')
    def test_release_subnet_addr(self, mock_utils):
        mock_network_task = a10_network_tasks.ReleaseSubnetAddressForMember()
        mock_network_task.network_driver = self.client_mock
        NAT_POOL.member_ref_count = 1
        mock_network_task.execute(MEMBER, NAT_FLAVOR, NAT_POOL)
        self.client_mock.delete_port.assert_called_with(NAT_POOL.port_id)

    @mock.patch('a10_octavia.common.utils.get_vrid_floating_ip_for_project',
                return_value=a10constants.MOCK_VRID_FLOATING_IP_1)
    @mock.patch('a10_octavia.common.utils.get_patched_ip_address',
                return_value=a10constants.MOCK_VRID_FLOATING_IP_1)
    def test_HandleVRIDFloatingIP_create_floating_ip_for_subnet_list(
            self, mock_patched_ip, mock_floating_ip):
        vthunder = copy.deepcopy(VTHUNDER)
        vthunder.ip_address = '10.0.0.1'
        subnet = copy.deepcopy(SUBNET_1)
        subnet.cidr = a10constants.MOCK_SUBNET_CIDR
        vthunder_config = copy.deepcopy(HW_THUNDER)
        port = copy.deepcopy(PORT)
        port.fixed_ips.append(MockIP(a10constants.MOCK_VRID_FLOATING_IP_1))
        self.client_mock.vrrpa.get.return_value = EXISTING_FIP_SHARED_PARTITION
        mock_network_task = a10_network_tasks.HandleVRIDFloatingIP()
        mock_network_task.axapi_client = self.client_mock
        self.network_driver_mock.get_subnet.return_value = subnet
        self.network_driver_mock.allocate_vrid_fip.return_value = port
        self.conf.config(group=a10constants.A10_GLOBAL_OPTS,
                         vrid=VRID_VALUE)
        mock_network_task.execute(vthunder, POOL, [], [subnet], vthunder_config)
        self.network_driver_mock.allocate_vrid_fip.assert_called_with(
            mock.ANY, None, mock.ANY,
            fixed_ip=a10constants.MOCK_VRID_FLOATING_IP_1)
        self.client_mock.vrrpa.update.assert_called_with(
            VRID_VALUE, floating_ips=[a10constants.MOCK_VRID_FLOATING_IP_1],
            is_partition=False)

    def test_get_all_resource_subnet(self):
        mock_network_task = a10_network_tasks.GetAllResourceSubnet()
        self.network_driver_mock.get_subnet.return_value = SUBNET_1
        subnet = mock_network_task.execute([MEMBER])
        self.assertEqual(subnet, [SUBNET_1])
