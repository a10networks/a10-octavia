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
from octavia.common import exceptions as o_exceptions
from octavia.network import data_models as n_data_models
from octavia.tests.common import constants as t_constants

from a10_octavia.common import config_options
from a10_octavia.common import data_models
from a10_octavia.common import exceptions
from a10_octavia.common import utils
from a10_octavia.controller.worker.tasks import a10_database_tasks as task
from a10_octavia.tests.common import a10constants
from a10_octavia.tests.unit import base

VTHUNDER = data_models.VThunder(amphora_id=a10constants.MOCK_AMPHORA_ID,
                                compute_id=a10constants.MOCK_COMPUTE_ID)
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
LB2 = o_data_models.LoadBalancer(id=a10constants.MOCK_LOAD_BALANCER_ID)
FIXED_IP = n_data_models.FixedIP(ip_address='10.10.10.10')
PORT = n_data_models.Port(id=uuidutils.generate_uuid(), fixed_ips=[FIXED_IP])
VRID = data_models.VRID(id=1, vrid=0,
                        owner=a10constants.MOCK_PROJECT_ID,
                        vrid_port_id=uuidutils.generate_uuid(),
                        vrid_floating_ip='10.0.12.32')
VRRP_SET = data_models.VrrpSet(set_id=a10constants.MOCK_SET_ID)
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

AMPHORA = o_data_models.Amphora(id=a10constants.MOCK_AMPHORA_ID,
                                role=a10constants.MOCK_TOPOLOGY_ROLE_MASTER)
AMPHORA_BLADE = o_data_models.Amphora(id=a10constants.MOCK_AMPHORA_ID,
                                      role=a10constants.MOCK_TOPOLOGY_ROLE_BACKUP)


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
        self.conf.register_opts(config_options.A10_GLOBAL_OPTS,
                                group=a10constants.A10_GLOBAL_OPTS)
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

    def test_get_backup_vthunder_by_loadbalancer(self):
        vthunder = copy.deepcopy(VTHUNDER)
        vthunder.role = "BACKUP"
        self.conf.config(
            group=a10constants.A10_GLOBAL_CONF_SECTION,
            use_parent_partition=True)
        mock_get_vthunder = task.GetVThunderByLoadBalancer()
        mock_get_vthunder.vthunder_repo = mock.MagicMock()
        mock_get_vthunder.vthunder_repo.get_vthunder_from_lb.return_value = None
        mock_get_vthunder.vthunder_repo.get_backup_vthunder_from_lb.return_value = vthunder
        backup_vthunder = mock_get_vthunder.execute(LB, False)
        self.assertEqual(backup_vthunder, vthunder)

    def test_get_vrid_for_project_member_hmt_use_partition(self):
        thunder = copy.deepcopy(HW_THUNDER)
        lb = copy.deepcopy(LB)
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
        mock_vrid_entry.vrid_repo.get_vrid_from_owner.return_value = VRID
        vrid = mock_vrid_entry.execute([a10constants.MOCK_PROJECT_ID], thunder, lb)
        self.assertEqual(VRID, vrid)

    def test_get_vrid_for_project(self):
        thunder = copy.deepcopy(HW_THUNDER)
        lb = copy.deepcopy(LB)
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
        mock_vrid_entry.vrid_repo.get_vrid_from_owner.return_value = VRID
        vrid = mock_vrid_entry.execute(MEMBER_1, thunder, lb)
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
        mock_vrid_entry.execute(MEMBER_1, [], thunder)
        mock_vrid_entry.vrid_repo.delete.assert_called_once_with(
            mock.ANY,
            owner=thunder.ip_address + "_" + thunder.partition_name
        )

    def test_update_vrid_for_project_member_with_port_and_with_vrid(self):
        thunder = copy.deepcopy(HW_THUNDER)
        mock_vrid_entry = task.UpdateVRIDForLoadbalancerResource()
        mock_vrid_entry.vrid_repo = mock.Mock()
        mock_vrid_entry.vrid_repo.exists.return_value = True
        mock_vrid_entry.execute(MEMBER_1, [VRID], thunder)
        mock_vrid_entry.vrid_repo.update.assert_called_once_with(
            mock.ANY,
            VRID.id,
            vrid=VRID.vrid,
            vrid_floating_ip=VRID.vrid_floating_ip,
            vrid_port_id=VRID.vrid_port_id,
            subnet_id=VRID.subnet_id)
        mock_vrid_entry.vrid_repo.create.assert_not_called()

    def test_update_vrid_for_project_member_with_port_and_no_vrid(self):
        thunder = copy.deepcopy(HW_THUNDER)
        mock_vrid_entry = task.UpdateVRIDForLoadbalancerResource()
        mock_vrid_entry.vrid_repo = mock.Mock()
        mock_vrid_entry.vrid_repo.exists.return_value = False
        mock_vrid_entry.execute(MEMBER_1, [VRID], thunder)
        mock_vrid_entry.vrid_repo.create.assert_called_once_with(
            mock.ANY,
            owner=thunder.ip_address + "_" + thunder.partition_name,
            id=VRID.id,
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
        use_dev_flavor = False
        member_1 = o_data_models.Member(id=uuidutils.generate_uuid(),
                                        project_id=t_constants.MOCK_PROJECT_ID,
                                        ip_address=t_constants.MOCK_IP_ADDRESS,
                                        pool_id=a10constants.MOCK_POOL_ID)
        mock_count_pool = task.PoolCountforIP()
        mock_count_pool.member_repo.get_pool_count_by_ip = mock.Mock()
        mock_count_pool.member_repo.get_pool_count_by_ip.return_value = 2
        pool_count = mock_count_pool.execute(member_1, use_dev_flavor, mock.ANY)
        self.assertEqual(2, pool_count)

    def test_get_subnet_for_deletion_with_pool_no_lb(self):
        use_dev_flavor = False
        mock_subnets = task.GetSubnetForDeletionInPool()
        mock_subnets.member_repo.get_pool_count_subnet = mock.Mock()
        mock_subnets.member_repo.get_pool_count_subnet.return_value = 1
        mock_subnets.loadbalancer_repo.get_lb_count_by_subnet = mock.Mock()
        mock_subnets.loadbalancer_repo.get_lb_count_by_subnet.return_value = 0
        subnet_list = mock_subnets.execute(
            [MEMBER_1, MEMBER_2], [a10constants.MOCK_PROJECT_ID], use_dev_flavor, mock.ANY)
        self.assertEqual(['mock-subnet-1', 'mock-subnet-2'], subnet_list)

    def test_get_subnet_for_deletion_with_multiple_pool_lb(self):
        use_dev_flavor = False
        mock_subnets = task.GetSubnetForDeletionInPool()
        mock_subnets.member_repo.get_pool_count_subnet = mock.Mock()
        mock_subnets.member_repo.get_pool_count_subnet.return_value = 2
        mock_subnets.loadbalancer_repo.get_lb_count_by_subnet = mock.Mock()
        mock_subnets.loadbalancer_repo.get_lb_count_by_subnet.return_value = 2
        subnet_list = mock_subnets.execute(
            [MEMBER_1, MEMBER_2], [a10constants.MOCK_PROJECT_ID], use_dev_flavor, mock.ANY)
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

    @mock.patch('a10_octavia.controller.worker.tasks.a10_database_tasks.a10_task_utils')
    def test_GetFlavorData_execute_no_flavor_id(self, mock_utils):
        mock_utils.attribute_search.return_value = None
        flavor_task = task.GetFlavorData()
        ret_val = flavor_task.execute(LB)
        self.assertEqual(ret_val, None)

    def test_GetFlavorData_execute_no_flavor_or_profile(self):
        flavor_task = task.GetFlavorData()
        flavor_task.flavor_repo = mock.Mock()
        flavor_task.flavor_repo.get.return_value = None
        flavor_task._flavor_search = mock.Mock(
            return_value=a10constants.MOCK_FLAVOR_ID)
        ret_val = flavor_task.execute
        self.assertRaises(exceptions.FlavorNotFound, ret_val, LB)

        flavor_task.flavor_repo.reset_mock()
        flavor_task.flavor_repo = mock.Mock()
        flavor = copy.deepcopy(FLAVOR)
        flavor.flavor_profile_id = None
        flavor_task.flavor_repo.get.return_value = flavor
        ret_val = flavor_task.execute(LB)
        self.assertEqual(ret_val, None)

    def test_GetFlavorData_execute_with_default_flavor_id(self):
        flavor_task = task.GetFlavorData()
        flavor = copy.deepcopy(FLAVOR)
        flavor_prof = copy.deepcopy(FLAVOR_PROFILE)
        flavor_prof.flavor_data = "{}"
        flavor_task.flavor_repo = mock.Mock()
        flavor_task.flavor_repo.get.return_value = flavor
        self.conf.config(group=a10constants.A10_GLOBAL_OPTS,
                         default_flavor_id=flavor)
        flavor_task.flavor_profile_repo = mock.Mock()
        flavor_task.flavor_profile_repo.get.return_value = flavor_prof
        ret_val = flavor_task.execute(LB2)
        self.assertEqual(ret_val, {})

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
        lb_count = mock_count_lb.execute(LB, VTHUNDER)
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

    def test_AddProjectSetIdDB(self):
        self.conf.config(
            group=a10constants.A10_CONTROLLER_WORKER_CONF_SECTION,
            amp_boot_network_list="mgmt_subnet_1")
        db_task = task.AddProjectSetIdDB()
        db_task.vrrp_set_repo.get = mock.Mock()
        db_task.execute(LB)
        db_task.vrrp_set_repo.get.assert_called_once_with(mock.ANY, mgmt_subnet='mgmt_subnet_1',
                                                          project_id=mock.ANY)

    def test_DeleteProjectSetIdDB(self):
        db_task = task.DeleteProjectSetIdDB()
        db_task.vrrp_set_repo.delete = mock.Mock()
        db_task.execute(LB)
        db_task.vrrp_set_repo.delete.assert_called_once_with(mock.ANY, project_id=mock.ANY)

    def test_CheckExistingVthunderTopology_execute_raised_exception(self):
        lb_task = task.CheckExistingVthunderTopology()
        vthunder = copy.deepcopy(VTHUNDER)
        vthunder.topology = a10constants.MOCK_TOPOLOGY_ACTIVE_STANDBY
        lb_task.vthunder_repo = mock.MagicMock()[1:999]
        lb_task.vthunder_repo.get_vthunder_by_project_id.return_value = vthunder
        self.assertRaises(o_exceptions.InvalidTopology, lb_task.execute, LB, "SINGLE")

    @mock.patch('octavia.statistics.stats_base.update_stats_via_driver')
    def test_update_listeners_stats_with_statistics(self, mock_stats_base):
        LISTENER_STATS = o_data_models.ListenerStatistics(listener_id=uuidutils.generate_uuid())
        mock_get_listener = task.UpdateListenersStats()
        mock_get_listener.listener_repo = mock.MagicMock()
        mock_get_listener.listener_repo.get_all.return_value = [LISTENER], None
        mock_get_listener.listener_stats_repo = mock.MagicMock()
        mock_get_listener.listener_stats_repo.get_all.return_value = [LISTENER_STATS], None
        mock_get_listener.execute([LISTENER_STATS])
        mock_stats_base.assert_called_once_with([LISTENER_STATS])

    def test_GetVThunderAmphora(self):
        db_task = task.GetVThunderAmphora()
        vthunder = copy.deepcopy(VTHUNDER)
        db_task.amphora_repo = mock.MagicMock()
        db_task.amphora_repo.get.return_value = AMPHORA
        amp = db_task.execute(vthunder)
        self.assertEqual(amp.id, a10constants.MOCK_AMPHORA_ID)

    def test_GetProjectVRRPSetId(self):
        db_task = task.GetProjectVRRPSetId()
        self.conf.config(
            group=a10constants.A10_CONTROLLER_WORKER_CONF_SECTION,
            amp_boot_network_list=[1, 2])
        vthunder = copy.deepcopy(VTHUNDER)
        db_task.vrrp_set_repo = mock.MagicMock()
        db_task.vrrp_set_repo.get.return_value = VRRP_SET
        setid = db_task.execute(vthunder)
        self.assertEqual(setid, a10constants.MOCK_SET_ID)

    def test_GetSpareComputeForProject(self):
        db_task = task.GetSpareComputeForProject()
        vthunder = copy.deepcopy(VTHUNDER)
        db_task.vthunder_repo = mock.MagicMock()
        db_task.vthunder_repo.get_spare_vthunder.return_value = vthunder
        db_task.vthunder_repo.set_spare_vthunder_status = mock.Mock()
        cid, vth = db_task.execute()
        self.assertEqual(cid, a10constants.MOCK_COMPUTE_ID)

    def test_TryGetSpareCompute(self):
        db_task = task.TryGetSpareCompute()
        vthunder = copy.deepcopy(VTHUNDER)
        db_task.vthunder_repo = mock.MagicMock()
        db_task.vthunder_repo.get_spare_vthunder.return_value = vthunder
        vth = db_task.execute()
        self.assertEqual(vth, vthunder)

    def test_GetComputeVThundersAndLoadBalancers(self):
        db_task = task.GetComputeVThundersAndLoadBalancers()
        vthunder = copy.deepcopy(VTHUNDER)
        db_task.vthunder_repo = mock.MagicMock()
        db_task.vthunder_repo.get_compute_vthunders.return_value = [vthunder]
        db_task.loadbalancer_repo = mock.MagicMock()
        db_task.loadbalancer_repo.get = mock.MagicMock()
        db_task.loadbalancer_repo.get.return_value = LB
        vlist, llist = db_task.execute(vthunder)
        self.assertEqual(vlist[0], vthunder)
        self.assertEqual(llist[0], LB)

    def test_DeleteStaleSpareVThunder(self):
        db_task = task.DeleteStaleSpareVThunder()
        vthunder = copy.deepcopy(VTHUNDER)
        db_task.amphora_repo = mock.Mock()
        db_task.amphora_repo.delete = mock.Mock()
        db_task.vthunder_repo = mock.Mock()
        db_task.vthunder_repo.delete = mock.Mock()
        db_task.execute(vthunder)
        db_task.amphora_repo.delete.assert_called_once_with(mock.ANY,
                                                            id=a10constants.MOCK_AMPHORA_ID)
        db_task.vthunder_repo.delete.assert_called_once_with(mock.ANY, id=vthunder.id)

    def test_GetVThunderDeviceID(self):
        db_task = task.GetVThunderDeviceID()
        vthunder = copy.deepcopy(VTHUNDER)
        db_task.amphora_repo = mock.MagicMock()
        db_task.amphora_repo.get.return_value = AMPHORA
        setid = db_task.execute(vthunder)
        self.assertEqual(setid, 1)
        db_task.amphora_repo.get.return_value = AMPHORA_BLADE
        setid = db_task.execute(vthunder)
        self.assertEqual(setid, 2)

    def test_FailoverPostDbUpdate(self):
        db_task = task.FailoverPostDbUpdate()
        vthunder = copy.deepcopy(VTHUNDER)
        db_task.amphora_repo = mock.Mock()
        db_task.amphora_repo.get.return_value = AMPHORA
        db_task.amphora_repo.update = mock.Mock()
        db_task.vthunder_repo = mock.Mock()
        db_task.vthunder_repo.get_all_vthunder_by_address.return_value = [vthunder]
        db_task.vthunder_repo.update = mock.Mock()
        db_task.execute(vthunder, vthunder)
        db_task.vthunder_repo.update.assert_called_once_with(mock.ANY,
                                                             id=vthunder.id,
                                                             ip_address=mock.ANY,
                                                             compute_id=mock.ANY)
        db_task.amphora_repo.update.assert_called_once_with(mock.ANY,
                                                            id=a10constants.MOCK_AMPHORA_ID,
                                                            compute_id=mock.ANY,
                                                            lb_network_ip=mock.ANY,
                                                            image_id=mock.ANY,
                                                            compute_flavor=mock.ANY)

    def test_count_lb_thunder_partition_success(self):
        vthunder = copy.deepcopy(VTHUNDER)
        mock_count_lb = task.CountLBThunderPartition()
        mock_count_lb.vthunder_repo.get_lb_count_vthunder_partition = mock.Mock()
        mock_count_lb.vthunder_repo.get_lb_count_vthunder_partition.return_value = 1
        lb_count = mock_count_lb.execute(vthunder)
        self.assertEqual(1, lb_count)

    def test_count_lb_thunder_partition_no_thunder(self):
        mock_count_lb = task.CountLBThunderPartition()
        lb_count = mock_count_lb.execute(None)
        self.assertEqual(0, lb_count)
