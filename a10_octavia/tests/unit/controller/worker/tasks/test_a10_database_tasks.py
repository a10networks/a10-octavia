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
from oslo_utils import uuidutils

from octavia.common import data_models as o_data_models
from octavia.network import data_models as n_data_models
from octavia.tests.common import constants as t_constants

from a10_octavia.common import config_options
from a10_octavia.common import data_models
from a10_octavia.common import exceptions
from a10_octavia.common import utils
from a10_octavia.controller.worker.tasks import a10_database_tasks as task
from a10_octavia.tests.common import a10constants
from a10_octavia.tests.unit import base

VTHUNDER = data_models.VThunder()
HW_THUNDER = data_models.HardwareThunder(
    project_id=a10constants.MOCK_PROJECT_ID,
    device_name="rack_thunder_1",
    undercloud=True,
    username="abc",
    password="abc",
    ip_address="10.10.10.10",
    partition_name="shared")
LB = o_data_models.LoadBalancer(id=a10constants.MOCK_LOAD_BALANCER_ID)
FIXED_IP = n_data_models.FixedIP(ip_address='10.10.10.10')
PORT = n_data_models.Port(id=uuidutils.generate_uuid(), fixed_ips=[FIXED_IP])
VRID = data_models.VRID(id=1, vrid=0,
                        project_id=a10constants.MOCK_PROJECT_ID,
                        vrid_port_id=uuidutils.generate_uuid(),
                        vrid_floating_ip='10.0.12.32')
MEMBER_1 = o_data_models.Member(id=uuidutils.generate_uuid(),
                                project_id=a10constants.MOCK_PROJECT_ID,
                                subnet_id=a10constants.MOCK_SUBNET_ID)
MEMBER_2 = o_data_models.Member(id=uuidutils.generate_uuid(),
                                project_id=a10constants.MOCK_PROJECT_ID,
                                subnet_id=a10constants.MOCK_SUBNET_ID_2)

POOL = o_data_models.Pool(id=a10constants.MOCK_POOL_ID)
SUBNET = n_data_models.Subnet(id=uuidutils.generate_uuid())


class TestA10DatabaseTasks(base.BaseTaskTestCase):

    def setUp(self):
        super(TestA10DatabaseTasks, self).setUp()
        imp.reload(task)
        self.vrid_repo = mock.Mock()
        self.conf = self.useFixture(oslo_fixture.Config(cfg.CONF))
        self.conf.register_opts(config_options.A10_GLOBAL_OPTS,
                                group=a10constants.A10_GLOBAL_CONF_SECTION)
        self.conf.register_opts(
            config_options.A10_HARDWARE_THUNDER_OPTS,
            group=a10constants.HARDWARE_THUNDER_CONF_SECTION)
        self.db_session = mock.patch(
            'a10_octavia.controller.worker.tasks.a10_database_tasks.db_apis.get_session')
        self.db_session.start()

    def tearDown(self):
        super(TestA10DatabaseTasks, self).tearDown()
        self.db_session.stop()

    def _generate_hardware_device_conf(self, thunder):
        hardware_device_conf = [{"project_id": a10constants.MOCK_PROJECT_ID,
                                 "username": thunder.username,
                                 "password": thunder.password,
                                 "device_name": thunder.device_name,
                                 "vrid_floating_ip": thunder.vrid_floating_ip,
                                 "ip_address": thunder.ip_address}]
        return hardware_device_conf

    def test_get_vthunder_by_loadbalancer(self):
        self.conf.config(
            group=a10constants.A10_GLOBAL_CONF_SECTION,
            use_parent_partition=True)
        mock_get_vthunder = task.GetVThunderByLoadBalancer()
        mock_get_vthunder.vthunder_repo = mock.MagicMock()
        mock_get_vthunder.vthunder_repo.get_vthunder_from_lb.return_value = None
        vthunder = mock_get_vthunder.execute(LB)
        self.assertEqual(vthunder, None)

    @mock.patch('a10_octavia.common.utils.get_parent_project',
                return_value=a10constants.MOCK_PARENT_PROJECT_ID)
    def test_create_rack_vthunder_entry_parent_partition_exists(
            self, mock_parent_project_id):
        self.conf.config(
            group=a10constants.A10_GLOBAL_CONF_SECTION,
            use_parent_partition=True)
        mock_lb = copy.deepcopy(LB)
        mock_lb.project_id = a10constants.MOCK_CHILD_PROJECT_ID
        mock_vthunder_config = copy.deepcopy(HW_THUNDER)
        mock_vthunder_config.hierarchical_multitenancy = "enable"
        mock_create_vthunder = task.CreateRackVthunderEntry()
        mock_create_vthunder.vthunder_repo = mock.MagicMock()
        mock_vthunder = copy.deepcopy(VTHUNDER)
        mock_vthunder.partition_name = a10constants.MOCK_PARENT_PROJECT_ID[:14]
        mock_create_vthunder.vthunder_repo.create.return_value = mock_vthunder
        vthunder = mock_create_vthunder.execute(mock_lb, mock_vthunder_config)
        self.assertEqual(vthunder.partition_name,
                         a10constants.MOCK_PARENT_PROJECT_ID[:14])

    @mock.patch('a10_octavia.common.utils.get_parent_project',
                return_value=None)
    def test_create_rack_vthunder_entry_parent_partition_not_exists(
            self, mock_parent_project_id):
        self.conf.config(
            group=a10constants.A10_GLOBAL_CONF_SECTION,
            use_parent_partition=True)
        mock_lb = copy.deepcopy(LB)
        mock_lb.project_id = a10constants.MOCK_CHILD_PROJECT_ID
        mock_vthunder_config = copy.deepcopy(HW_THUNDER)
        mock_vthunder_config.hierarchical_multitenancy = "enable"
        mock_create_vthunder = task.CheckExistingProjectToThunderMappedEntries()
        mock_create_vthunder.vthunder_repo = mock.MagicMock()
        mock_vthunder = copy.deepcopy(VTHUNDER)
        mock_vthunder.partition_name = a10constants.MOCK_CHILD_PART
        self.assertRaises(exceptions.ParentProjectNotFound,
                          mock_create_vthunder.execute, mock_lb,
                          mock_vthunder_config)

    def test_create_rack_vthunder_entry_parent_partition_no_hmt(self):
        self.conf.config(group=a10constants.A10_GLOBAL_CONF_SECTION,
                         use_parent_partition=True)
        mock_lb = copy.deepcopy(LB)
        mock_lb.project_id = a10constants.MOCK_CHILD_PROJECT_ID
        mock_vthunder_config = copy.deepcopy(HW_THUNDER)
        mock_vthunder_config.hierarchical_multitenancy = "disable"
        mock_create_vthunder = task.CreateRackVthunderEntry()
        mock_create_vthunder.vthunder_repo = mock.MagicMock()
        mock_vthunder = copy.deepcopy(VTHUNDER)
        mock_vthunder.partition_name = a10constants.MOCK_CHILD_PART

        mock_create_vthunder.vthunder_repo.create.return_value = mock_vthunder
        vthunder = mock_create_vthunder.execute(mock_lb, mock_vthunder_config)
        self.assertEqual(vthunder.partition_name, a10constants.MOCK_CHILD_PART)

    def test_create_rack_vthunder_entry_parent_partition_hmt_no_use_parent_partition(
            self):
        self.conf.config(
            group=a10constants.A10_GLOBAL_CONF_SECTION,
            use_parent_partition=False)
        mock_lb = copy.deepcopy(LB)
        mock_lb.project_id = a10constants.MOCK_CHILD_PROJECT_ID
        mock_vthunder_config = copy.deepcopy(HW_THUNDER)
        mock_vthunder_config.hierarchical_multitenancy = "enable"
        mock_create_vthunder = task.CreateRackVthunderEntry()
        mock_create_vthunder.vthunder_repo = mock.MagicMock()
        mock_vthunder = copy.deepcopy(VTHUNDER)
        mock_vthunder.partition_name = a10constants.MOCK_CHILD_PART
        mock_create_vthunder.vthunder_repo.create.return_value = mock_vthunder
        vthunder = mock_create_vthunder.execute(mock_lb, mock_vthunder_config)
        self.assertEqual(vthunder.partition_name, a10constants.MOCK_CHILD_PART)

    def test_create_rack_vthunder_entry_child_partition_exists(self):
        self.conf.config(
            group=a10constants.A10_GLOBAL_CONF_SECTION,
            use_parent_partition=False)
        mock_lb = copy.deepcopy(LB)
        mock_lb.project_id = a10constants.MOCK_CHILD_PROJECT_ID
        mock_vthunder_config = copy.deepcopy(HW_THUNDER)
        mock_vthunder_config.hierarchical_multitenancy = "enable"
        mock_create_vthunder = task.CreateRackVthunderEntry()
        mock_create_vthunder.vthunder_repo = mock.MagicMock()
        mock_vthunder = copy.deepcopy(VTHUNDER)
        mock_vthunder.partition_name = a10constants.MOCK_CHILD_PROJECT_ID[:14]
        mock_create_vthunder.vthunder_repo.create.return_value = mock_vthunder
        vthunder = mock_create_vthunder.execute(mock_lb, mock_vthunder_config)
        self.assertEqual(vthunder.partition_name,
                         a10constants.MOCK_CHILD_PROJECT_ID[:14])

    def test_get_vrid_for_project_member_hmt_use_partition(self):
        thunder = copy.deepcopy(HW_THUNDER)
        thunder.hierarchical_multitenancy = 'enable'
        thunder.vrid_floating_ip = VRID.vrid_floating_ip
        hardware_device_conf = self._generate_hardware_device_conf(thunder)
        self.conf.config(group=a10constants.HARDWARE_THUNDER_CONF_SECTION,
                         devices=[hardware_device_conf])
        self.conf.config(
            group=a10constants.A10_GLOBAL_CONF_SECTION,
            use_parent_partition=True)
        self.conf.conf.hardware_thunder.devices = {
            a10constants.MOCK_PROJECT_ID: thunder}

        mock_vrid_entry = task.GetVRIDForLoadbalancerResource()
        mock_vrid_entry.CONF = self.conf

        mock_vrid_entry.vrid_repo = mock.Mock()
        mock_vrid_entry.vthunder_repo = mock.Mock()
        mock_vrid_entry.vrid_repo.get_vrid_from_project_ids.return_value = VRID
        vrid = mock_vrid_entry.execute([a10constants.MOCK_PROJECT_ID])
        self.assertEqual(VRID, vrid)

    def test_get_vrid_for_project(self):
        thunder = copy.deepcopy(HW_THUNDER)
        thunder.hierarchical_multitenancy = 'disable'
        thunder.vrid_floating_ip = VRID.vrid_floating_ip
        hardware_device_conf = self._generate_hardware_device_conf(thunder)
        self.conf.config(group=a10constants.HARDWARE_THUNDER_CONF_SECTION,
                         devices=[hardware_device_conf])
        self.conf.config(
            group=a10constants.A10_GLOBAL_CONF_SECTION,
            use_parent_partition=False)
        self.conf.conf.hardware_thunder.devices = {
            a10constants.MOCK_PROJECT_ID: thunder}

        mock_vrid_entry = task.GetVRIDForLoadbalancerResource()
        mock_vrid_entry.CONF = self.conf

        mock_vrid_entry.vrid_repo = mock.Mock()
        mock_vrid_entry.vthunder_repo = mock.Mock()
        mock_vrid_entry.vrid_repo.get_vrid_from_project_ids.return_value = VRID
        vrid = mock_vrid_entry.execute(MEMBER_1)
        mock_vrid_entry.vthunder_repo.get_partition_for_project.assert_not_called()
        self.assertEqual(VRID, vrid)

    def test_update_vrid_for_project_member_delete_vrid(self):
        thunder = copy.deepcopy(HW_THUNDER)
        thunder.vrid_floating_ip = VRID.vrid_floating_ip
        hardware_device_conf = self._generate_hardware_device_conf(thunder)
        self.conf.config(group=a10constants.HARDWARE_THUNDER_CONF_SECTION,
                         devices=[hardware_device_conf])
        self.conf.conf.hardware_thunder.devices = {
            a10constants.MOCK_PROJECT_ID: thunder}
        utils.get_vrid_floating_ip_for_project.CONF = self.conf

        mock_vrid_entry = task.UpdateVRIDForLoadbalancerResource()
        mock_vrid_entry.vrid_repo = mock.Mock()
        mock_vrid_entry.execute(MEMBER_1, [])
        mock_vrid_entry.vrid_repo.delete.assert_called_once_with(
            mock.ANY,
            project_id=a10constants.MOCK_PROJECT_ID
        )

    def test_update_vrid_for_project_member_with_port_and_with_vrid(self):
        mock_vrid_entry = task.UpdateVRIDForLoadbalancerResource()
        mock_vrid_entry.vrid_repo = mock.Mock()
        mock_vrid_entry.vrid_repo.exists.return_value = True
        mock_vrid_entry.execute(MEMBER_1, [VRID])
        mock_vrid_entry.vrid_repo.update.assert_called_once_with(
            mock.ANY,
            VRID.id,
            vrid=VRID.vrid,
            vrid_floating_ip=VRID.vrid_floating_ip,
            vrid_port_id=VRID.vrid_port_id,
            subnet_id=VRID.subnet_id)
        mock_vrid_entry.vrid_repo.create.assert_not_called()

    def test_update_vrid_for_project_member_with_port_and_no_vrid(self):
        mock_vrid_entry = task.UpdateVRIDForLoadbalancerResource()
        mock_vrid_entry.vrid_repo = mock.Mock()
        mock_vrid_entry.vrid_repo.exists.return_value = False
        mock_vrid_entry.execute(MEMBER_1, [VRID])
        mock_vrid_entry.vrid_repo.create.assert_called_once_with(
            mock.ANY,
            project_id=MEMBER_1.project_id,
            vrid=VRID.vrid,
            vrid_floating_ip=VRID.vrid_floating_ip,
            vrid_port_id=VRID.vrid_port_id,
            subnet_id=VRID.subnet_id)
        mock_vrid_entry.vrid_repo.update.assert_not_called()

    def test_delete_vrid_entry_with_vrid(self):
        mock_vrid_entry = task.DeleteVRIDEntry()
        mock_vrid_entry.vrid_repo = mock.Mock()
        mock_vrid_entry.execute(VRID, True)
        mock_vrid_entry.vrid_repo.delete.assert_called_once_with(
            mock.ANY, id=VRID.id)

    def test_delete_vrid_entry_negative(self):
        mock_vrid_entry = task.DeleteVRIDEntry()
        mock_vrid_entry.vrid_repo = mock.Mock()
        mock_vrid_entry.execute(VRID, False)
        mock_vrid_entry.vrid_repo.delete.assert_not_called()
        mock_vrid_entry.vrid_repo.reset_mock()
        mock_vrid_entry.execute(None, True)
        mock_vrid_entry.vrid_repo.delete.assert_not_called()
        mock_vrid_entry.vrid_repo.reset_mock()
        mock_vrid_entry.execute(None, False)
        mock_vrid_entry.vrid_repo.delete.assert_not_called()

    def test_delete_vrid_entry_with_multi_vrids(self):
        VRID_1 = data_models.VRID(id=2)
        mock_vrid_entry = task.DeleteMultiVRIDEntry()
        mock_vrid_entry.vrid_repo = mock.Mock()
        mock_vrid_entry.execute([VRID, VRID_1])
        mock_vrid_entry.vrid_repo.delete_batch.assert_called_once_with(
            mock.ANY, ids=[VRID.id, VRID_1.id])

    def test_count_members_in_project_ip(self):
        mock_count_member = task.CountMembersWithIP()
        mock_count_member.member_repo.get_member_count_by_ip_address = mock.Mock()
        mock_count_member.member_repo.get_member_count_by_ip_address.return_value = 1
        member_count = mock_count_member.execute(MEMBER_1)
        self.assertEqual(1, member_count)

    def test_count_members_in_project_ip_port_protocol(self):
        member_1 = o_data_models.Member(
            id=uuidutils.generate_uuid(),
            protocol_port=t_constants.MOCK_PORT_ID,
            project_id=t_constants.MOCK_PROJECT_ID,
            ip_address=t_constants.MOCK_IP_ADDRESS)
        mock_count_member = task.CountMembersWithIPPortProtocol()
        mock_count_member.member_repo.get_member_count_by_ip_address_port_protocol = mock.Mock()
        mock_count_member.member_repo.get_member_count_by_ip_address_port_protocol.return_value = 2
        member_count = mock_count_member.execute(member_1, POOL)
        self.assertEqual(2, member_count)

    def test_pool_count_accn_ip(self):
        member_1 = o_data_models.Member(id=uuidutils.generate_uuid(),
                                        project_id=t_constants.MOCK_PROJECT_ID,
                                        ip_address=t_constants.MOCK_IP_ADDRESS,
                                        pool_id=a10constants.MOCK_POOL_ID)
        mock_count_pool = task.PoolCountforIP()
        mock_count_pool.member_repo.get_pool_count_by_ip = mock.Mock()
        mock_count_pool.member_repo.get_pool_count_by_ip.return_value = 2
        pool_count = mock_count_pool.execute(member_1)
        self.assertEqual(2, pool_count)

    def test_get_subnet_for_deletion_with_pool_no_lb(self):
        mock_subnets = task.GetSubnetForDeletionInPool()
        mock_subnets.member_repo.get_pool_count_subnet = mock.Mock()
        mock_subnets.member_repo.get_pool_count_subnet.return_value = 1
        mock_subnets.loadbalancer_repo.get_lb_count_by_subnet = mock.Mock()
        mock_subnets.loadbalancer_repo.get_lb_count_by_subnet.return_value = 0
        subnet_list = mock_subnets.execute(
            [MEMBER_1, MEMBER_2], [a10constants.MOCK_PROJECT_ID])
        self.assertEqual(['mock-subnet-1', 'mock-subnet-2'], subnet_list)

    def test_get_subnet_for_deletion_with_multiple_pool_lb(self):
        mock_subnets = task.GetSubnetForDeletionInPool()
        mock_subnets.member_repo.get_pool_count_subnet = mock.Mock()
        mock_subnets.member_repo.get_pool_count_subnet.return_value = 2
        mock_subnets.loadbalancer_repo.get_lb_count_by_subnet = mock.Mock()
        mock_subnets.loadbalancer_repo.get_lb_count_by_subnet.return_value = 2
        subnet_list = mock_subnets.execute(
            [MEMBER_1, MEMBER_2], [a10constants.MOCK_PROJECT_ID])
        self.assertEqual([], subnet_list)

    def test_get_child_projects_for_partition(self):
        vthunder = copy.deepcopy(VTHUNDER)
        vthunder.partition_name = "mock-partition-name"
        mock_get_projects = task.GetChildProjectsOfParentPartition()
        mock_get_projects.vthunder_repo.get_project_list_using_partition = mock.Mock()
        mock_get_projects.execute(MEMBER_1, vthunder)
        mock_get_projects.vthunder_repo.get_project_list_using_partition.\
            assert_called_once_with(mock.ANY, partition_name='mock-partition-name')
