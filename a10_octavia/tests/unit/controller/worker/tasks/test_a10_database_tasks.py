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
LB = o_data_models.LoadBalancer(id=a10constants.MOCK_LOAD_BALANCER_ID,
                                flavor_id=a10constants.MOCK_FLAVOR_ID)
FIXED_IP = n_data_models.FixedIP(ip_address='10.10.10.10')
PORT = n_data_models.Port(id=uuidutils.generate_uuid(), fixed_ips=[FIXED_IP])
VRID = data_models.VRID(id=1, vrid=0,
                        project_id=a10constants.MOCK_PROJECT_ID,
                        vrid_port_id=uuidutils.generate_uuid(),
                        vrid_floating_ip='10.0.12.32')
LISTENER = o_data_models.Listener(id=a10constants.MOCK_LISTENER_ID, load_balancer=LB)
POOL = o_data_models.Pool(id=a10constants.MOCK_POOL_ID, load_balancer=LB)
HM = o_data_models.HealthMonitor(id=a10constants, pool=POOL)
MEMBER_1 = o_data_models.Member(id=uuidutils.generate_uuid(),
                                project_id=a10constants.MOCK_PROJECT_ID,
                                subnet_id=a10constants.MOCK_SUBNET_ID,
                                pool=POOL)
MEMBER_2 = o_data_models.Member(id=uuidutils.generate_uuid(),
                                project_id=a10constants.MOCK_PROJECT_ID,
                                subnet_id=a10constants.MOCK_SUBNET_ID_2,
                                pool=POOL)
FLAVOR_PROFILE = o_data_models.FlavorProfile(id=a10constants.MOCK_FLAVOR_PROF_ID,
                                             flavor_data={})
FLAVOR = o_data_models.Flavor(id=a10constants.MOCK_FLAVOR_ID,
                              flavor_profile_id=a10constants.MOCK_FLAVOR_PROF_ID)
SUBNET = n_data_models.Subnet(id=uuidutils.generate_uuid())
NAT_POOL = data_models.NATPool(id=uuidutils.generate_uuid(),
                               port_id=a10constants.MOCK_PORT_ID)


class TestA10DatabaseTasks(base.BaseTaskTestCase):

    def setUp(self):
        super(TestA10DatabaseTasks, self).setUp()
        imp.reload(task)
        self.vrid_repo = mock.Mock()
        self.nat_pool_repo = mock.Mock()
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
        vthunder.ip_address = "mock-ip-addr"
        mock_get_projects = task.GetChildProjectsOfParentPartition()
        mock_get_projects.vthunder_repo.get_project_list_using_partition = mock.Mock()
        mock_get_projects.execute(MEMBER_1, vthunder)
        mock_get_projects.vthunder_repo.get_project_list_using_partition.\
            assert_called_once_with(mock.ANY, partition_name='mock-partition-name',
                                    ip_address="mock-ip-addr")

    def test_flavor_search_loadbalancer_find_flavor(self):
        flavor_task = task.GetFlavorData()
        found_id = flavor_task._flavor_search(LB)
        self.assertEqual(found_id, a10constants.MOCK_FLAVOR_ID)

    def test_flavor_search_listener_find_flavor(self):
        flavor_task = task.GetFlavorData()
        found_id = flavor_task._flavor_search(LB)
        self.assertEqual(found_id, a10constants.MOCK_FLAVOR_ID)

    def test_flavor_search_pool_find_flavor(self):
        flavor_task = task.GetFlavorData()
        found_id = flavor_task._flavor_search(POOL)
        self.assertEqual(found_id, a10constants.MOCK_FLAVOR_ID)

    def test_flavor_search_member_find_flavor(self):
        flavor_task = task.GetFlavorData()
        found_id = flavor_task._flavor_search(MEMBER_1)
        self.assertEqual(found_id, a10constants.MOCK_FLAVOR_ID)

    def test_flavor_search_health_monitor_find_flavor(self):
        flavor_task = task.GetFlavorData()
        found_id = flavor_task._flavor_search(HM)
        self.assertEqual(found_id, a10constants.MOCK_FLAVOR_ID)

    def test_GetFlavorData_format_flavor_keys(self):
        expected = {"virtual_server": {"arp_disable": 1}}
        flavor = {"virtual-server": {"arp-disable": 1}}
        flavor_task = task.GetFlavorData()
        formated_flavor = flavor_task._format_keys(flavor)
        self.assertEqual(formated_flavor, expected)

    def test_GetFlavorData_format_flavor_list_keys(self):
        expected = {
            "service_group": {
                "name_expressions": [{
                    "regex": "sg1",
                    "json": {"health_check_disable": 1}
                }]
            }
        }
        name_expr = {
            "name-expressions": [{
                "regex": "sg1",
                "json": {"health-check-disable": 1}
            }]
        }
        flavor = {"service-group": name_expr}
        flavor_task = task.GetFlavorData()
        formated_flavor = flavor_task._format_keys(flavor)
        self.assertEqual(formated_flavor, expected)

    def test_GetFlavorData_format_flavor_multi_val(self):
        expected = {
            "service_group": {
                "name_expressions": [{
                    "regex": "sg1",
                    "json": {"health_check_disable": 1}
                }],
                "strict_select": 0
            }
        }
        name_expr = {
            "name-expressions": [{
                "regex": "sg1",
                "json": {"health-check-disable": 1}
            }]
        }
        flavor = {"service-group": {"strict-select": 0}}
        flavor['service-group'].update(name_expr)
        flavor_task = task.GetFlavorData()
        formated_flavor = flavor_task._format_keys(flavor)
        self.assertEqual(formated_flavor, expected)

    def test_GetFlavorData_execute_no_flavor_id(self):
        flavor_task = task.GetFlavorData()
        flavor_task._flavor_search = mock.Mock(return_value=None)
        ret_val = flavor_task.execute(LB)
        self.assertEqual(ret_val, None)

    def test_GetFlavorData_execute_no_flavor_or_profile(self):
        flavor_task = task.GetFlavorData()
        flavor_task.flavor_repo = mock.Mock()
        flavor_task.flavor_repo.get.return_value = None
        flavor_task._flavor_search = mock.Mock(
            return_value=a10constants.MOCK_FLAVOR_ID)
        ret_val = flavor_task.execute(LB)
        self.assertEqual(ret_val, None)

        flavor_task.flavor_repo.reset_mock()
        flavor_task.flavor_repo = mock.Mock()
        flavor = copy.deepcopy(FLAVOR)
        flavor.flavor_profile_id = None
        flavor_task.flavor_repo.get.return_value = flavor
        ret_val = flavor_task.execute(LB)
        self.assertEqual(ret_val, None)

    def test_GetFlavorData_execute_return_flavor(self):
        flavor_task = task.GetFlavorData()
        flavor_task._flavor_search = mock.Mock(
            return_value=a10constants.MOCK_FLAVOR_ID)
        flavor_task._format_keys = mock.Mock()
        flavor_task._format_keys.return_value = {}
        flavor_task.flavor_repo = mock.Mock()
        flavor_task.flavor_repo.get.return_value = FLAVOR

        flavor_prof = copy.deepcopy(FLAVOR_PROFILE)
        flavor_prof.flavor_data = "{}"
        flavor_task.flavor_profile_repo = mock.Mock()
        flavor_task.flavor_profile_repo.get.return_value = flavor_prof
        ret_val = flavor_task.execute(LB)
        self.assertEqual(ret_val, {})

    def test_GetNatPoolEntry(self):
        db_task = task.GetNatPoolEntry()
        db_task.nat_pool_repo = self.nat_pool_repo
        flavor = {"pool_name": "p1", "start_address": "1.1.1.1", "end_address": "1.1.1.2"}
        db_task.execute(MEMBER_1, flavor)
        self.nat_pool_repo.get(mock.ANY, name="p1", subnet_id=MEMBER_1.subnet_id)

    def test_UpdateNatPoolDB_update(self):
        db_task = task.UpdateNatPoolDB()
        db_task.nat_pool_repo = self.nat_pool_repo
        flavor = {"pool_name": "p1", "start_address": "1.1.1.1", "end_address": "1.1.1.2"}
        NAT_POOL.member_ref_count = 1
        db_task.execute(MEMBER_1, flavor, NAT_POOL, None)
        self.nat_pool_repo.update.assert_called_with(mock.ANY, mock.ANY, member_ref_count=2)

    def test_UpdateNatPoolDB_create(self):
        db_task = task.UpdateNatPoolDB()
        db_task.nat_pool_repo = self.nat_pool_repo
        flavor = {"pool_name": "p1", "start_address": "1.1.1.1", "end_address": "1.1.1.2"}
        port = mock.Mock(id="1")
        db_task.execute(MEMBER_1, flavor, None, port)
        self.nat_pool_repo.create.assert_called_with(
            mock.ANY, id=mock.ANY, name="p1",
            subnet_id=MEMBER_1.subnet_id, start_address="1.1.1.1", end_address="1.1.1.2",
            member_ref_count=1, port_id="1")

    def test_DeleteNatPoolEntry_update(self):
        db_task = task.DeleteNatPoolEntry()
        db_task.nat_pool_repo = self.nat_pool_repo
        NAT_POOL.member_ref_count = 2
        db_task.execute(NAT_POOL)
        self.nat_pool_repo.update.assert_called_with(mock.ANY, mock.ANY, member_ref_count=1)

    def test_DeleteNatPoolEntry_delete(self):
        db_task = task.DeleteNatPoolEntry()
        db_task.nat_pool_repo = self.nat_pool_repo
        NAT_POOL.member_ref_count = 1
        db_task.execute(NAT_POOL)
        self.nat_pool_repo.delete(mock.ANY, id=NAT_POOL.id)

    def test_lb_count_according_to_flavor(self):
        mock_count_lb = task.CountLoadbalancersWithFlavor()
        mock_count_lb.loadbalancer_repo.get_lb_count_by_flavor = mock.Mock()
        mock_count_lb.loadbalancer_repo.get_lb_count_by_flavor.return_value = 2
        lb_count = mock_count_lb.execute(LB)
        self.assertEqual(2, lb_count)

    def test_SetThunderUpdatedAt_execute_update(self):
        db_task = task.SetThunderUpdatedAt()
        vthunder = copy.deepcopy(VTHUNDER)
        db_task.vthunder_repo.update = mock.Mock()
        db_task.execute(vthunder)
        db_task.vthunder_repo.update.assert_called_once_with(mock.ANY,
                                                             vthunder.id,
                                                             updated_at=mock.ANY)

    def test_SetThunderLastWriteMem_execute_update(self):
        db_task = task.SetThunderLastWriteMem()
        vthunder = copy.deepcopy(VTHUNDER)
        db_task.vthunder_repo.update_last_write_mem = mock.Mock()
        db_task.execute(vthunder, True, True)
        db_task.vthunder_repo.update_last_write_mem.assert_called_once_with(
            mock.ANY, vthunder.ip_address, vthunder.partition_name, last_write_mem=mock.ANY)

    def test_GetActiveLoadBalancersByThunder_return_empty(self):
        lb_task = task.GetActiveLoadBalancersByThunder()
        vthunder = copy.deepcopy(VTHUNDER)
        vthunder.loadbalancer_id = a10constants.MOCK_LOAD_BALANCER_ID
        lb_task.loadbalancer_repo.get_active_lbs_by_thunder = mock.Mock()
        lb_task.loadbalancer_repo.get_active_lbs_by_thunder.return_value = []
        lb_list = lb_task.execute(vthunder)
        self.assertEqual(lb_list, [])

    def test_GetActiveLoadBalancersByThunder_return_list(self):
        lb_task = task.GetActiveLoadBalancersByThunder()
        vthunder = copy.deepcopy(VTHUNDER)
        vthunder.loadbalancer_id = a10constants.MOCK_LOAD_BALANCER_ID
        lb_task.loadbalancer_repo.get_active_lbs_by_thunder = mock.Mock()
        lb_task.loadbalancer_repo.get_active_lbs_by_thunder.return_value = [LB]
        lb_list = lb_task.execute(vthunder)
        self.assertEqual(len(lb_list), 1)

    def test_MarkLoadBalancersPendingUpdateInDB_execute(self):
        lb_task = task.MarkLoadBalancersPendingUpdateInDB()
        lb_list = []
        lb_list.append(LB)
        lb_task.loadbalancer_repo.update = mock.Mock()
        lb_task.execute(lb_list)
        lb_task.loadbalancer_repo.update.assert_called_once_with(mock.ANY,
                                                                 LB.id,
                                                                 provisioning_status=mock.ANY)

    def test_MarkLoadBalancersPendingUpdateInDB_execute_for_empty_list(self):
        lb_task = task.MarkLoadBalancersPendingUpdateInDB()
        lb_list = []
        lb_task.loadbalancer_repo.update = mock.Mock()
        lb_task.execute(lb_list)
        lb_task.loadbalancer_repo.update.assert_not_called()

    def test_MarkLoadBalancersActiveInDB_execute(self):
        lb_task = task.MarkLoadBalancersActiveInDB()
        lb_list = []
        lb_list.append(LB)
        lb_task.loadbalancer_repo.update = mock.Mock()
        lb_task.execute(lb_list)
        lb_task.loadbalancer_repo.update.assert_called_once_with(mock.ANY,
                                                                 LB.id,
                                                                 provisioning_status=mock.ANY)

    def test_MarkLoadBalancersActiveInDB_execute_for_empty_list(self):
        lb_task = task.MarkLoadBalancersActiveInDB()
        lb_list = []
        lb_task.loadbalancer_repo.update = mock.Mock()
        lb_task.execute(lb_list)
        lb_task.loadbalancer_repo.update.assert_not_called()
