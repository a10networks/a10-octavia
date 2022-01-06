#    Copyright 2019, A10 Networks
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


from oslo_config import cfg
from taskflow.patterns import linear_flow

from octavia.common import constants
from octavia.controller.worker.tasks import database_tasks
from octavia.controller.worker.tasks import lifecycle_tasks
from octavia.controller.worker.tasks import model_tasks

from a10_octavia.common import a10constants
from a10_octavia.controller.worker.tasks import a10_database_tasks
from a10_octavia.controller.worker.tasks import a10_network_tasks
from a10_octavia.controller.worker.tasks import server_tasks
from a10_octavia.controller.worker.tasks import vthunder_tasks

CONF = cfg.CONF


class MemberFlows(object):

    def get_create_member_flow(self, topology):
        """Create a flow to create a member

        :returns: The flow for creating a member
        """
        create_member_flow = linear_flow.Flow(constants.CREATE_MEMBER_FLOW)
        create_member_flow.add(lifecycle_tasks.MemberToErrorOnRevertTask(
            requires=[constants.MEMBER,
                      constants.LISTENERS,
                      constants.LOADBALANCER,
                      constants.POOL]))
        create_member_flow.add(vthunder_tasks.VthunderInstanceBusy(
            requires=a10constants.COMPUTE_BUSY))

        create_member_flow.add(database_tasks.MarkMemberPendingCreateInDB(
            requires=constants.MEMBER))
        if CONF.a10_global.validate_subnet:
            create_member_flow.add(a10_network_tasks.ValidateSubnet(
                name='validate-subnet',
                requires=constants.MEMBER))
        create_member_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        create_member_flow.add(a10_database_tasks.GetLoadBalancerListByProjectID(
            requires=a10constants.VTHUNDER,
            provides=a10constants.LOADBALANCERS_LIST))
        create_member_flow.add(database_tasks.GetAmphoraeFromLoadbalancer(
            requires=constants.LOADBALANCER,
            provides=constants.AMPHORA))
        create_member_flow.add(a10_network_tasks.CalculateDelta(
            requires=(constants.LOADBALANCER, a10constants.LOADBALANCERS_LIST),
            provides=constants.DELTAS))
        create_member_flow.add(a10_network_tasks.HandleNetworkDeltas(
            requires=constants.DELTAS, provides=constants.ADDED_PORTS))
        # managing interface additions here
        if topology == constants.TOPOLOGY_SINGLE:
            create_member_flow.add(
                vthunder_tasks.AmphoraePostMemberNetworkPlug(
                    requires=(
                        constants.LOADBALANCER,
                        constants.ADDED_PORTS,
                        a10constants.VTHUNDER)))
            create_member_flow.add(vthunder_tasks.VThunderComputeConnectivityWait(
                name=a10constants.VTHUNDER_CONNECTIVITY_WAIT,
                requires=(a10constants.VTHUNDER, constants.AMPHORA)))
            create_member_flow.add(
                vthunder_tasks.EnableInterfaceForMembers(
                    requires=[
                        constants.ADDED_PORTS,
                        constants.LOADBALANCER,
                        a10constants.VTHUNDER]))
        # configure member flow for HA
        if topology == constants.TOPOLOGY_ACTIVE_STANDBY:
            create_member_flow.add(
                a10_database_tasks.GetBackupVThunderByLoadBalancer(
                    name="get_backup_vThunder",
                    requires=(constants.LOADBALANCER, a10constants.VTHUNDER),
                    provides=a10constants.BACKUP_VTHUNDER))
            create_member_flow.add(vthunder_tasks.VThunderComputeConnectivityWait(
                name="backup_compute_conn_wait_before_probe_device",
                requires=constants.AMPHORA,
                rebind={a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER}))
            create_member_flow.add(vthunder_tasks.VCSSyncWait(
                name="vcs_sync_wait_before_probe_device",
                requires=a10constants.VTHUNDER))
            create_member_flow.add(
                vthunder_tasks.AmphoraePostMemberNetworkPlug(
                    requires=(
                        constants.LOADBALANCER,
                        constants.ADDED_PORTS,
                        a10constants.VTHUNDER)))
            create_member_flow.add(
                vthunder_tasks.AmphoraePostMemberNetworkPlug(
                    name="backup_amphora_network_plug", requires=[
                        constants.ADDED_PORTS, constants.LOADBALANCER], rebind={
                        a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER}))
            create_member_flow.add(vthunder_tasks.VThunderComputeConnectivityWait(
                name=a10constants.MASTER_CONNECTIVITY_WAIT,
                requires=(a10constants.VTHUNDER, constants.AMPHORA)))
            create_member_flow.add(vthunder_tasks.VThunderComputeConnectivityWait(
                name=a10constants.BACKUP_CONNECTIVITY_WAIT,
                requires=constants.AMPHORA,
                rebind={a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER}))
            create_member_flow.add(vthunder_tasks.VCSSyncWait(
                name="backup-plug-wait-vcs-ready",
                requires=a10constants.VTHUNDER))
            create_member_flow.add(vthunder_tasks.GetMasterVThunder(
                name=a10constants.GET_MASTER_VTHUNDER,
                requires=a10constants.VTHUNDER,
                provides=a10constants.VTHUNDER))
            create_member_flow.add(a10_database_tasks.GetBackupVThunderByLoadBalancer(
                name="get_backup_vThunder_after_get_master",
                requires=(constants.LOADBALANCER, a10constants.VTHUNDER),
                provides=a10constants.BACKUP_VTHUNDER))
            create_member_flow.add(
                vthunder_tasks.EnableInterfaceForMembers(
                    name=a10constants.ENABLE_MASTER_VTHUNDER_INTERFACE,
                    requires=[
                        constants.ADDED_PORTS,
                        constants.LOADBALANCER,
                        a10constants.VTHUNDER]))
            create_member_flow.add(vthunder_tasks.AmphoraePostMemberNetworkPlug(
                name="amphorae-post-member-network-plug-for-master",
                requires=(constants.LOADBALANCER, constants.ADDED_PORTS,
                          a10constants.VTHUNDER)))
            create_member_flow.add(
                vthunder_tasks.VThunderComputeConnectivityWait(
                    name=a10constants.CONNECTIVITY_WAIT_FOR_MASTER_VTHUNDER,
                    requires=(a10constants.VTHUNDER, constants.AMPHORA)))
            create_member_flow.add(
                vthunder_tasks.VThunderComputeConnectivityWait(
                    name=a10constants.CONNECTIVITY_WAIT_FOR_BACKUP_VTHUNDER,
                    rebind={
                        a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER},
                    requires=constants.AMPHORA))
            create_member_flow.add(vthunder_tasks.VCSSyncWait(
                name="member_enable_interface_vcs_sync_wait",
                requires=a10constants.VTHUNDER))
            create_member_flow.add(vthunder_tasks.GetMasterVThunder(
                name=a10constants.GET_VTHUNDER_MASTER,
                requires=a10constants.VTHUNDER,
                provides=a10constants.VTHUNDER))
            create_member_flow.add(
                vthunder_tasks.EnableInterfaceForMembers(
                    requires=[
                        constants.ADDED_PORTS,
                        constants.LOADBALANCER,
                        a10constants.VTHUNDER]))
        if CONF.a10_global.handle_vrid:
            create_member_flow.add(self.handle_vrid_for_member_subflow())
        create_member_flow.add(a10_database_tasks.CountMembersWithIP(
            requires=constants.MEMBER, provides=a10constants.MEMBER_COUNT_IP
        ))
        create_member_flow.add(vthunder_tasks.AllowLoadbalancerForwardWithAnySource(
            name=a10constants.ALLOW_NO_SNAT,
            requires=(constants.MEMBER, constants.AMPHORA)))
        create_member_flow.add(a10_database_tasks.GetFlavorData(
            rebind={a10constants.LB_RESOURCE: constants.LOADBALANCER},
            provides=constants.FLAVOR))
        create_member_flow.add(self.get_create_member_snat_pool_subflow())
        create_member_flow.add(server_tasks.MemberCreate(
            requires=(constants.MEMBER, a10constants.VTHUNDER, constants.POOL,
                      a10constants.MEMBER_COUNT_IP, constants.FLAVOR)))
        create_member_flow.add(database_tasks.MarkMemberActiveInDB(
            requires=constants.MEMBER))
        create_member_flow.add(database_tasks.MarkPoolActiveInDB(
            requires=constants.POOL))
        create_member_flow.add(database_tasks.
                               MarkLBAndListenersActiveInDB(
                                   requires=(constants.LOADBALANCER,
                                             constants.LISTENERS)))
        create_member_flow.add(vthunder_tasks.WriteMemory(
            requires=a10constants.VTHUNDER))
        create_member_flow.add(a10_database_tasks.SetThunderUpdatedAt(
            requires=a10constants.VTHUNDER))
        return create_member_flow

    def get_delete_member_flow(self, topology):
        """Flow to delete a member on VThunder

        :returns: The flow for deleting a member
        """
        delete_member_flow = linear_flow.Flow(constants.DELETE_MEMBER_FLOW)
        delete_member_flow.add(lifecycle_tasks.MemberToErrorOnRevertTask(
            requires=[constants.MEMBER,
                      constants.LISTENERS,
                      constants.LOADBALANCER,
                      constants.POOL]))
        delete_member_flow.add(vthunder_tasks.VthunderInstanceBusy(
            requires=a10constants.COMPUTE_BUSY))

        delete_member_flow.add(database_tasks.MarkMemberPendingDeleteInDB(
            requires=constants.MEMBER))
        delete_member_flow.add(model_tasks.
                               DeleteModelObject(rebind={constants.OBJECT:
                                                         constants.MEMBER}))
        delete_member_flow.add(database_tasks.GetAmphoraeFromLoadbalancer(
            requires=constants.LOADBALANCER,
            provides=constants.AMPHORA))
        delete_member_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        delete_member_flow.add(a10_database_tasks.CountMembersWithIP(
            requires=constants.MEMBER, provides=a10constants.MEMBER_COUNT_IP))
        delete_member_flow.add(
            a10_database_tasks.CountMembersWithIPPortProtocol(
                requires=(
                    constants.MEMBER,
                    constants.POOL),
                provides=a10constants.MEMBER_COUNT_IP_PORT_PROTOCOL))
        delete_member_flow.add(a10_database_tasks.GetFlavorData(
            rebind={a10constants.LB_RESOURCE: constants.LOADBALANCER},
            provides=constants.FLAVOR))
        delete_member_flow.add(a10_database_tasks.GetLoadBalancerListByProjectID(
            requires=a10constants.VTHUNDER,
            provides=a10constants.LOADBALANCERS_LIST))
        delete_member_flow.add(a10_network_tasks.CalculateDelta(
            requires=(constants.LOADBALANCER, a10constants.LOADBALANCERS_LIST),
            provides=constants.DELTAS))
        delete_member_flow.add(a10_network_tasks.HandleNetworkDeltas(
            requires=constants.DELTAS, provides=constants.ADDED_PORTS))
        delete_member_flow.add(
            vthunder_tasks.AmphoraePostNetworkUnplug(
                requires=(
                    constants.LOADBALANCER,
                    constants.ADDED_PORTS,
                    a10constants.VTHUNDER)))
        delete_member_flow.add(vthunder_tasks.VThunderComputeConnectivityWait(
            name=a10constants.VTHUNDER_CONNECTIVITY_WAIT,
            requires=(a10constants.VTHUNDER, constants.AMPHORA)))
        if topology == constants.TOPOLOGY_ACTIVE_STANDBY:
            delete_member_flow.add(
                a10_database_tasks.GetBackupVThunderByLoadBalancer(
                    name=a10constants.GET_BACKUP_VTHUNDER_BY_LB,
                    requires=(constants.LOADBALANCER, a10constants.VTHUNDER),
                    provides=a10constants.BACKUP_VTHUNDER))
            delete_member_flow.add(
                vthunder_tasks.VThunderComputeConnectivityWait(
                    name=a10constants.BACKUP_CONNECTIVITY_WAIT + "-before-unplug",
                    requires=constants.AMPHORA,
                    rebind={a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER}))
            delete_member_flow.add(
                vthunder_tasks.AmphoraePostNetworkUnplug(
                    name=a10constants.AMPHORA_POST_NETWORK_UNPLUG_FOR_BACKUP_VTHUNDER,
                    requires=(constants.LOADBALANCER, constants.ADDED_PORTS),
                    rebind={a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER}))
            delete_member_flow.add(
                vthunder_tasks.VThunderComputeConnectivityWait(
                    name=a10constants.BACKUP_CONNECTIVITY_WAIT,
                    requires=constants.AMPHORA,
                    rebind={a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER}))
            delete_member_flow.add(vthunder_tasks.VCSSyncWait(
                name='member-unplug-' + a10constants.VCS_SYNC_WAIT,
                requires=a10constants.VTHUNDER))
            delete_member_flow.add(vthunder_tasks.GetMasterVThunder(
                name=a10constants.GET_VTHUNDER_MASTER,
                requires=a10constants.VTHUNDER,
                provides=a10constants.VTHUNDER))
        delete_member_flow.add(server_tasks.MemberFindNatPool(
            requires=[a10constants.VTHUNDER, constants.POOL,
                      constants.FLAVOR], provides=a10constants.NAT_FLAVOR))
        delete_member_flow.add(a10_database_tasks.GetNatPoolEntry(
            requires=[constants.MEMBER, a10constants.NAT_FLAVOR],
            provides=a10constants.NAT_POOL))
        delete_member_flow.add(a10_network_tasks.ReleaseSubnetAddressForMember(
            requires=[constants.MEMBER, a10constants.NAT_FLAVOR, a10constants.NAT_POOL]))
        delete_member_flow.add(a10_database_tasks.DeleteNatPoolEntry(
            requires=a10constants.NAT_POOL))
        delete_member_flow.add(
            server_tasks.MemberDelete(
                requires=(
                    constants.MEMBER,
                    a10constants.VTHUNDER,
                    constants.POOL,
                    a10constants.MEMBER_COUNT_IP,
                    a10constants.MEMBER_COUNT_IP_PORT_PROTOCOL)))
        if CONF.a10_global.handle_vrid:
            delete_member_flow.add(self.get_delete_member_vrid_subflow())
        delete_member_flow.add(database_tasks.DeleteMemberInDB(
            requires=constants.MEMBER))
        delete_member_flow.add(database_tasks.DecrementMemberQuota(
            requires=constants.MEMBER))
        delete_member_flow.add(database_tasks.MarkPoolActiveInDB(
            requires=constants.POOL))
        delete_member_flow.add(database_tasks.MarkLBAndListenersActiveInDB(
            requires=[constants.LOADBALANCER, constants.LISTENERS]))
        delete_member_flow.add(vthunder_tasks.WriteMemory(
            requires=a10constants.VTHUNDER))
        delete_member_flow.add(a10_database_tasks.SetThunderUpdatedAt(
            requires=a10constants.VTHUNDER))
        return delete_member_flow

    def get_rack_vthunder_delete_member_flow(self, vthunder_conf, device_dict):
        """Flow to delete a member in Thunder devices

        :returns: The flow for deleting a member
        """
        delete_member_flow = linear_flow.Flow(constants.DELETE_MEMBER_FLOW)
        delete_member_flow.add(lifecycle_tasks.MemberToErrorOnRevertTask(
            requires=[constants.MEMBER,
                      constants.LISTENERS,
                      constants.LOADBALANCER,
                      constants.POOL]))
        delete_member_flow.add(database_tasks.MarkMemberPendingDeleteInDB(
            requires=constants.MEMBER))
        delete_member_flow.add(model_tasks.
                               DeleteModelObject(rebind={constants.OBJECT:
                                                         constants.MEMBER}))
        delete_member_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        delete_member_flow.add(vthunder_tasks.SetupDeviceNetworkMap(
            requires=a10constants.VTHUNDER,
            provides=a10constants.VTHUNDER))
        delete_member_flow.add(a10_database_tasks.CountMembersWithIP(
            requires=constants.MEMBER, provides=a10constants.MEMBER_COUNT_IP))
        delete_member_flow.add(
            a10_database_tasks.CountMembersWithIPPortProtocol(
                requires=(
                    constants.MEMBER,
                    constants.POOL),
                provides=a10constants.MEMBER_COUNT_IP_PORT_PROTOCOL))
        delete_member_flow.add(a10_database_tasks.GetFlavorData(
            rebind={a10constants.LB_RESOURCE: constants.LOADBALANCER},
            provides=constants.FLAVOR))
        delete_member_flow.add(vthunder_tasks.GetVthunderConfByFlavor(
            inject={a10constants.VTHUNDER_CONFIG: vthunder_conf,
                    a10constants.DEVICE_CONFIG_DICT: device_dict},
            requires=(constants.LOADBALANCER, a10constants.VTHUNDER_CONFIG,
                      a10constants.DEVICE_CONFIG_DICT),
            rebind={constants.FLAVOR_DATA: constants.FLAVOR},
            provides=(a10constants.VTHUNDER_CONFIG, a10constants.USE_DEVICE_FLAVOR)))
        delete_member_flow.add(a10_network_tasks.GetLBResourceSubnet(
            name=a10constants.GET_LB_RESOURCE_SUBNET,
            rebind={a10constants.LB_RESOURCE: constants.MEMBER},
            provides=constants.SUBNET))
        delete_member_flow.add(
            a10_network_tasks.GetMembersOnThunder(
                requires=[a10constants.VTHUNDER, a10constants.USE_DEVICE_FLAVOR],
                provides=a10constants.MEMBERS))
        delete_member_flow.add(
            a10_database_tasks.CountMembersOnThunderBySubnet(
                requires=[
                    constants.SUBNET,
                    a10constants.USE_DEVICE_FLAVOR,
                    a10constants.MEMBERS],
                provides=a10constants.MEMBER_COUNT_THUNDER))
        delete_member_flow.add(server_tasks.MemberFindNatPool(
            requires=[a10constants.VTHUNDER, constants.POOL,
                      constants.FLAVOR], provides=a10constants.NAT_FLAVOR))
        delete_member_flow.add(a10_database_tasks.GetNatPoolEntry(
            requires=[constants.MEMBER, a10constants.NAT_FLAVOR],
            provides=a10constants.NAT_POOL))
        delete_member_flow.add(a10_network_tasks.ReleaseSubnetAddressForMember(
            requires=[constants.MEMBER, a10constants.NAT_FLAVOR, a10constants.NAT_POOL]))
        delete_member_flow.add(a10_database_tasks.DeleteNatPoolEntry(
            requires=a10constants.NAT_POOL))
        delete_member_flow.add(
            server_tasks.MemberDelete(
                requires=(
                    constants.MEMBER,
                    a10constants.VTHUNDER,
                    constants.POOL,
                    a10constants.MEMBER_COUNT_IP,
                    a10constants.MEMBER_COUNT_IP_PORT_PROTOCOL)))
        if CONF.a10_global.network_type == 'vlan':
            delete_member_flow.add(
                vthunder_tasks.DeleteInterfaceTagIfNotInUseForMember(
                    requires=[
                        constants.MEMBER,
                        a10constants.VTHUNDER]))
        # Handle VRID setting
        if CONF.a10_global.handle_vrid:
            delete_member_flow.add(self.get_delete_member_vrid_subflow())
        delete_member_flow.add(database_tasks.DeleteMemberInDB(
            requires=constants.MEMBER))
        delete_member_flow.add(database_tasks.DecrementMemberQuota(
            requires=constants.MEMBER))
        delete_member_flow.add(database_tasks.MarkPoolActiveInDB(
            requires=constants.POOL))
        delete_member_flow.add(database_tasks.MarkLBAndListenersActiveInDB(
            requires=[constants.LOADBALANCER,
                      constants.LISTENERS]))
        delete_member_flow.add(vthunder_tasks.WriteMemory(
            requires=a10constants.VTHUNDER))
        delete_member_flow.add(a10_database_tasks.SetThunderUpdatedAt(
            requires=a10constants.VTHUNDER))
        return delete_member_flow

    def get_delete_member_vthunder_internal_subflow(self, member_id, pool):
        delete_member_thunder_subflow = linear_flow.Flow(
            a10constants.DELETE_MEMBER_VTHUNDER_INTERNAL_SUBFLOW)
        delete_member_thunder_subflow.add(
            a10_database_tasks.CountMembersWithIPPortProtocol(
                name='count_members_ip_port_' + member_id,
                requires=(
                    constants.MEMBER,
                    constants.POOL),
                provides=a10constants.MEMBER_COUNT_IP_PORT_PROTOCOL,
                rebind={
                    constants.MEMBER: member_id,
                    constants.POOL: pool}))
        delete_member_thunder_subflow.add(a10_database_tasks.PoolCountforIP(
            name='pool_count_for_ip_' + member_id,
            requires=[constants.MEMBER, a10constants.USE_DEVICE_FLAVOR, a10constants.POOLS],
            provides=a10constants.POOL_COUNT_IP,
            rebind={constants.MEMBER: member_id}))

        # NAT pools database and pools clean up for flavor
        delete_member_thunder_subflow.add(a10_database_tasks.GetFlavorData(
            name='get_flavor_data_' + member_id,
            rebind={a10constants.LB_RESOURCE: constants.LOADBALANCER},
            provides=constants.FLAVOR))
        delete_member_thunder_subflow.add(server_tasks.MemberFindNatPool(
            name='member_find_nat_pool_' + member_id,
            requires=[a10constants.VTHUNDER, constants.POOL,
                      constants.FLAVOR], provides=a10constants.NAT_FLAVOR,
            rebind={constants.POOL: pool}))
        delete_member_thunder_subflow.add(a10_database_tasks.GetNatPoolEntry(
            name='get_nat_pool_db_entry_' + member_id,
            requires=[constants.MEMBER, a10constants.NAT_FLAVOR],
            provides=a10constants.NAT_POOL, rebind={constants.MEMBER: member_id}))
        delete_member_thunder_subflow.add(a10_network_tasks.ReleaseSubnetAddressForMember(
            name='release_subnet_address_for_member_' + member_id,
            requires=[constants.MEMBER, a10constants.NAT_FLAVOR, a10constants.NAT_POOL],
            rebind={constants.MEMBER: member_id}))
        delete_member_thunder_subflow.add(a10_database_tasks.DeleteNatPoolEntry(
            name='delete_nat_pool_entry_' + member_id,
            requires=a10constants.NAT_POOL))

        delete_member_thunder_subflow.add(
            server_tasks.MemberDeletePool(
                name='delete_thunder_member_pool_' +
                member_id,
                requires=(
                    constants.MEMBER,
                    a10constants.VTHUNDER,
                    constants.POOL,
                    a10constants.POOL_COUNT_IP,
                    a10constants.MEMBER_COUNT_IP_PORT_PROTOCOL),
                rebind={
                    constants.MEMBER: member_id, constants.POOL: pool}))
        if CONF.a10_global.network_type == 'vlan':
            delete_member_thunder_subflow.add(
                vthunder_tasks.DeleteInterfaceTagIfNotInUseForMember(
                    name='delete_unused_interface_tag_in_member_' +
                    member_id,
                    requires=[
                        constants.MEMBER,
                        a10constants.VTHUNDER],
                    rebind={
                        constants.MEMBER: member_id}))

        return delete_member_thunder_subflow

    def get_delete_member_vrid_subflow(self):
        delete_member_vrid_subflow = linear_flow.Flow(
            a10constants.DELETE_MEMBER_VRID_SUBFLOW)
        delete_member_vrid_subflow.add(a10_network_tasks.GetLBResourceSubnet(
            rebind={a10constants.LB_RESOURCE: constants.MEMBER},
            provides=constants.SUBNET))
        delete_member_vrid_subflow.add(
            a10_database_tasks.GetChildProjectsOfParentPartition(
                rebind={a10constants.LB_RESOURCE: constants.MEMBER},
                provides=a10constants.PARTITION_PROJECT_LIST
            ))
        delete_member_vrid_subflow.add(
            a10_database_tasks.CountLoadbalancersInProjectBySubnet(
                requires=[
                    constants.SUBNET,
                    a10constants.PARTITION_PROJECT_LIST,
                    a10constants.USE_DEVICE_FLAVOR],
                provides=a10constants.LB_COUNT_SUBNET))
        delete_member_vrid_subflow.add(
            a10_database_tasks.CountLoadbalancersOnThunderBySubnet(
                requires=[a10constants.VTHUNDER, constants.SUBNET, a10constants.USE_DEVICE_FLAVOR],
                provides=a10constants.LB_COUNT_THUNDER))
        delete_member_vrid_subflow.add(
            a10_database_tasks.CountMembersInProjectBySubnet(
                requires=[constants.SUBNET, a10constants.PARTITION_PROJECT_LIST],
                provides=a10constants.MEMBER_COUNT))
        delete_member_vrid_subflow.add(
            a10_database_tasks.GetVRIDForLoadbalancerResource(
                requires=[
                    a10constants.PARTITION_PROJECT_LIST,
                    a10constants.VTHUNDER],
                provides=a10constants.VRID_LIST))
        delete_member_vrid_subflow.add(
            a10_network_tasks.DeleteVRIDPort(
                requires=[
                    a10constants.VTHUNDER,
                    a10constants.VRID_LIST,
                    constants.SUBNET,
                    a10constants.USE_DEVICE_FLAVOR,
                    a10constants.LB_COUNT_SUBNET,
                    a10constants.MEMBER_COUNT,
                    a10constants.LB_COUNT_THUNDER,
                    a10constants.MEMBER_COUNT_THUNDER],
                rebind={a10constants.LB_RESOURCE: constants.MEMBER},
                provides=(
                    a10constants.VRID,
                    a10constants.DELETE_VRID)))
        delete_member_vrid_subflow.add(a10_database_tasks.DeleteVRIDEntry(
            requires=[a10constants.VRID, a10constants.DELETE_VRID]))
        return delete_member_vrid_subflow

    def get_delete_member_vrid_internal_subflow(self, pool, pool_members):
        delete_member_vrid_subflow = linear_flow.Flow(
            a10constants.DELETE_MEMBER_VRID_INTERNAL_SUBFLOW)
        delete_member_vrid_subflow.add(
            a10_database_tasks.GetChildProjectsOfParentPartition(
                name='get_child_project_of_parent_partition' + pool,
                rebind={a10constants.LB_RESOURCE: pool},
                provides=a10constants.PARTITION_PROJECT_LIST
            ))
        delete_member_vrid_subflow.add(
            a10_database_tasks.GetSubnetForDeletionInPool(
                name='get_subnet_for_deletion_in_pool' + pool,
                inject={a10constants.MEMBER_LIST: pool_members},
                requires=[
                    a10constants.PARTITION_PROJECT_LIST,
                    a10constants.USE_DEVICE_FLAVOR,
                    a10constants.POOLS],
                provides=a10constants.SUBNET_LIST))
        delete_member_vrid_subflow.add(
            a10_database_tasks.GetVRIDForLoadbalancerResource(
                name='get_vrid_for_loadbalancer_resource' + pool,
                requires=[
                    a10constants.PARTITION_PROJECT_LIST,
                    a10constants.VTHUNDER],
                provides=a10constants.VRID_LIST))
        delete_member_vrid_subflow.add(
            a10_network_tasks.DeleteMultipleVRIDPort(
                name='delete_multiple_vrid_port' + pool,
                requires=[
                    a10constants.VTHUNDER,
                    a10constants.VRID_LIST,
                    a10constants.SUBNET_LIST],
                rebind={a10constants.LB_RESOURCE: pool},
                provides=a10constants.VRID_LIST))
        delete_member_vrid_subflow.add(a10_database_tasks.DeleteMultiVRIDEntry(
            name='delete_multi_vrid_entry' + pool,
            requires=a10constants.VRID_LIST))
        return delete_member_vrid_subflow

    def handle_vrid_for_member_subflow(self):
        handle_vrid_for_member_subflow = linear_flow.Flow(
            a10constants.HANDLE_VRID_MEMBER_SUBFLOW)
        handle_vrid_for_member_subflow.add(
            a10_network_tasks.GetLBResourceSubnet(
                rebind={
                    a10constants.LB_RESOURCE: constants.MEMBER},
                provides=constants.SUBNET))
        handle_vrid_for_member_subflow.add(
            a10_database_tasks.GetChildProjectsOfParentPartition(
                rebind={a10constants.LB_RESOURCE: constants.MEMBER},
                provides=a10constants.PARTITION_PROJECT_LIST
            ))
        handle_vrid_for_member_subflow.add(
            a10_database_tasks.GetVRIDForLoadbalancerResource(
                requires=[
                    a10constants.PARTITION_PROJECT_LIST,
                    a10constants.VTHUNDER],
                provides=a10constants.VRID_LIST))
        handle_vrid_for_member_subflow.add(
            a10_network_tasks.HandleVRIDFloatingIP(
                requires=[
                    a10constants.VTHUNDER,
                    a10constants.VRID_LIST,
                    constants.SUBNET,
                    a10constants.VTHUNDER_CONFIG,
                    a10constants.USE_DEVICE_FLAVOR],
                rebind={
                    a10constants.LB_RESOURCE: constants.MEMBER},
                provides=a10constants.VRID_LIST))
        handle_vrid_for_member_subflow.add(
            a10_database_tasks.UpdateVRIDForLoadbalancerResource(
                requires=[
                    a10constants.VRID_LIST,
                    a10constants.VTHUNDER],
                rebind={
                    a10constants.LB_RESOURCE: constants.MEMBER}))

        return handle_vrid_for_member_subflow

    def get_update_member_flow(self, topology):
        """Flow to update a member

        :returns: The flow for updating a member
        """
        update_member_flow = linear_flow.Flow(constants.UPDATE_MEMBER_FLOW)
        update_member_flow.add(lifecycle_tasks.MemberToErrorOnRevertTask(
            requires=[constants.MEMBER,
                      constants.LISTENERS,
                      constants.LOADBALANCER,
                      constants.POOL]))
        update_member_flow.add(vthunder_tasks.VthunderInstanceBusy(
            requires=a10constants.COMPUTE_BUSY))

        update_member_flow.add(database_tasks.MarkMemberPendingUpdateInDB(
            requires=constants.MEMBER))
        if CONF.a10_global.validate_subnet:
            update_member_flow.add(a10_network_tasks.ValidateSubnet(
                name='validate-subnet',
                requires=constants.MEMBER))
        update_member_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        if topology == constants.TOPOLOGY_ACTIVE_STANDBY:
            update_member_flow.add(vthunder_tasks.GetMasterVThunder(
                name=a10constants.GET_MASTER_VTHUNDER,
                requires=a10constants.VTHUNDER,
                provides=a10constants.VTHUNDER))
        if CONF.a10_global.handle_vrid:
            update_member_flow.add(self.handle_vrid_for_member_subflow())
        update_member_flow.add(database_tasks.GetAmphoraeFromLoadbalancer(
            requires=constants.LOADBALANCER,
            provides=constants.AMPHORA))
        update_member_flow.add(a10_database_tasks.GetLoadbalancersInProjectBySubnet(
            requires=[constants.SUBNET, a10constants.PARTITION_PROJECT_LIST],
            provides=a10constants.LOADBALANCERS_LIST))
        update_member_flow.add(a10_database_tasks.CheckForL2DSRFlavor(
            rebind={a10constants.LB_RESOURCE: a10constants.LOADBALANCERS_LIST},
            provides=a10constants.L2DSR_FLAVOR))
        update_member_flow.add(a10_database_tasks.CountLoadbalancersInProjectBySubnet(
            requires=[constants.SUBNET, a10constants.PARTITION_PROJECT_LIST],
            provides=a10constants.LB_COUNT_SUBNET))
        update_member_flow.add(vthunder_tasks.UpdateLoadbalancerForwardWithAnySource(
            requires=(constants.SUBNET, constants.AMPHORA,
                      a10constants.LB_COUNT_SUBNET, a10constants.L2DSR_FLAVOR)))

        update_member_flow.add(a10_database_tasks.GetFlavorData(
            rebind={a10constants.LB_RESOURCE: constants.LOADBALANCER},
            provides=constants.FLAVOR))
        update_member_flow.add(server_tasks.MemberUpdate(
            requires=(constants.MEMBER, a10constants.VTHUNDER,
                      constants.POOL, constants.FLAVOR)))
        update_member_flow.add(database_tasks.UpdateMemberInDB(
            requires=[constants.MEMBER, constants.UPDATE_DICT]))
        update_member_flow.add(database_tasks.MarkMemberActiveInDB(
            requires=constants.MEMBER))
        update_member_flow.add(database_tasks.MarkPoolActiveInDB(
            requires=constants.POOL))
        update_member_flow.add(database_tasks.
                               MarkLBAndListenersActiveInDB(
                                   requires=[constants.LOADBALANCER,
                                             constants.LISTENERS]))
        update_member_flow.add(vthunder_tasks.WriteMemory(
            requires=a10constants.VTHUNDER))
        update_member_flow.add(a10_database_tasks.SetThunderUpdatedAt(
            requires=a10constants.VTHUNDER))
        return update_member_flow

    def get_rack_vthunder_update_member_flow(self, vthunder_conf, device_dict):
        """Flow to update a member in Thunder devices

        :returns: The flow for updating a member
        """
        update_member_flow = linear_flow.Flow(constants.UPDATE_MEMBER_FLOW)
        update_member_flow.add(lifecycle_tasks.MemberToErrorOnRevertTask(
            requires=[constants.MEMBER,
                      constants.LISTENERS,
                      constants.LOADBALANCER,
                      constants.POOL]))
        update_member_flow.add(database_tasks.MarkMemberPendingUpdateInDB(
            requires=constants.MEMBER))
        if CONF.a10_global.validate_subnet:
            update_member_flow.add(a10_network_tasks.ValidateSubnet(
                name='validate-subnet',
                requires=constants.MEMBER))
        update_member_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        update_member_flow.add(vthunder_tasks.SetupDeviceNetworkMap(
            requires=a10constants.VTHUNDER,
            provides=a10constants.VTHUNDER))

        # For device flavor
        update_member_flow.add(a10_database_tasks.GetFlavorData(
            rebind={a10constants.LB_RESOURCE: constants.LOADBALANCER},
            provides=constants.FLAVOR))
        update_member_flow.add(vthunder_tasks.GetVthunderConfByFlavor(
            inject={a10constants.VTHUNDER_CONFIG: vthunder_conf,
                    a10constants.DEVICE_CONFIG_DICT: device_dict},
            requires=(constants.LOADBALANCER, a10constants.VTHUNDER_CONFIG,
                      a10constants.DEVICE_CONFIG_DICT),
            rebind={constants.FLAVOR_DATA: constants.FLAVOR},
            provides=(a10constants.VTHUNDER_CONFIG, a10constants.USE_DEVICE_FLAVOR)))

        # Handle VRID settings
        if CONF.a10_global.handle_vrid:
            update_member_flow.add(self.handle_vrid_for_member_subflow())
        update_member_flow.add(server_tasks.MemberUpdate(
            requires=(constants.MEMBER, a10constants.VTHUNDER,
                      constants.POOL, constants.FLAVOR)))
        update_member_flow.add(database_tasks.UpdateMemberInDB(
            requires=[constants.MEMBER, constants.UPDATE_DICT]))
        if CONF.a10_global.network_type == 'vlan':
            update_member_flow.add(vthunder_tasks.TagInterfaceForMember(
                requires=[constants.MEMBER, a10constants.VTHUNDER]))
        update_member_flow.add(database_tasks.MarkMemberActiveInDB(
            requires=constants.MEMBER))
        update_member_flow.add(database_tasks.MarkPoolActiveInDB(
            requires=constants.POOL))
        update_member_flow.add(database_tasks.
                               MarkLBAndListenersActiveInDB(
                                   requires=[constants.LOADBALANCER,
                                             constants.LISTENERS]))
        update_member_flow.add(vthunder_tasks.WriteMemory(
            requires=a10constants.VTHUNDER))
        update_member_flow.add(a10_database_tasks.SetThunderUpdatedAt(
            requires=a10constants.VTHUNDER))
        return update_member_flow

    def get_rack_vthunder_create_member_flow(self, vthunder_conf, device_dict):
        """Create a flow to create a rack vthunder member

        :returns: The flow for creating a rack vthunder member
        """
        create_member_flow = linear_flow.Flow(constants.CREATE_MEMBER_FLOW)
        create_member_flow.add(lifecycle_tasks.MemberToErrorOnRevertTask(
            requires=[constants.MEMBER,
                      constants.LISTENERS,
                      constants.LOADBALANCER,
                      constants.POOL]))
        create_member_flow.add(database_tasks.MarkMemberPendingCreateInDB(
            requires=constants.MEMBER))
        if CONF.a10_global.validate_subnet:
            create_member_flow.add(a10_network_tasks.ValidateSubnet(
                name='validate-subnet',
                requires=constants.MEMBER))
        create_member_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        create_member_flow.add(vthunder_tasks.SetupDeviceNetworkMap(
            requires=a10constants.VTHUNDER,
            provides=a10constants.VTHUNDER))
        create_member_flow.add(a10_database_tasks.GetFlavorData(
            rebind={a10constants.LB_RESOURCE: constants.LOADBALANCER},
            provides=constants.FLAVOR))
        create_member_flow.add(vthunder_tasks.GetVthunderConfByFlavor(
            inject={a10constants.VTHUNDER_CONFIG: vthunder_conf,
                    a10constants.DEVICE_CONFIG_DICT: device_dict},
            requires=(constants.LOADBALANCER, a10constants.VTHUNDER_CONFIG,
                      a10constants.DEVICE_CONFIG_DICT),
            rebind={constants.FLAVOR_DATA: constants.FLAVOR},
            provides=(a10constants.VTHUNDER_CONFIG, a10constants.USE_DEVICE_FLAVOR)))
        if CONF.a10_global.handle_vrid:
            create_member_flow.add(self.handle_vrid_for_member_subflow())
        if CONF.a10_global.network_type == 'vlan':
            create_member_flow.add(vthunder_tasks.TagInterfaceForMember(
                requires=[constants.MEMBER,
                          a10constants.VTHUNDER]))
        create_member_flow.add(a10_database_tasks.CountMembersWithIP(
            requires=constants.MEMBER, provides=a10constants.MEMBER_COUNT_IP))
        create_member_flow.add(self.get_create_member_snat_pool_subflow())
        create_member_flow.add(server_tasks.MemberCreate(
            requires=(constants.MEMBER, a10constants.VTHUNDER, constants.POOL,
                      a10constants.MEMBER_COUNT_IP, constants.FLAVOR)))
        create_member_flow.add(database_tasks.MarkMemberActiveInDB(
            requires=constants.MEMBER))
        create_member_flow.add(database_tasks.MarkPoolActiveInDB(
            requires=constants.POOL))
        create_member_flow.add(database_tasks.
                               MarkLBAndListenersActiveInDB(
                                   requires=(constants.LOADBALANCER,
                                             constants.LISTENERS)))
        create_member_flow.add(vthunder_tasks.WriteMemory(
            requires=a10constants.VTHUNDER))
        create_member_flow.add(a10_database_tasks.SetThunderUpdatedAt(
            requires=a10constants.VTHUNDER))
        return create_member_flow

    def get_create_member_snat_pool_subflow(self):
        create_member_snat_subflow = linear_flow.Flow(
            a10constants.CREATE_MEMBER_SNAT_POOL_SUBFLOW)
        create_member_snat_subflow.add(server_tasks.MemberFindNatPool(
            requires=[a10constants.VTHUNDER, constants.POOL,
                      constants.FLAVOR], provides=a10constants.NAT_FLAVOR))
        create_member_snat_subflow.add(a10_database_tasks.GetNatPoolEntry(
            requires=[constants.MEMBER, a10constants.NAT_FLAVOR],
            provides=a10constants.NAT_POOL))
        create_member_snat_subflow.add(a10_network_tasks.ReserveSubnetAddressForMember(
            requires=[constants.MEMBER, a10constants.NAT_FLAVOR, a10constants.NAT_POOL],
            provides=a10constants.SUBNET_PORT))
        create_member_snat_subflow.add(a10_database_tasks.UpdateNatPoolDB(
            requires=[constants.MEMBER, a10constants.NAT_FLAVOR,
                      a10constants.NAT_POOL, a10constants.SUBNET_PORT]))
        return create_member_snat_subflow

    def get_rack_vthunder_batch_update_members_flow(self, old_members, new_members,
                                                    updated_members, vthunder_conf, device_dict):
        """Create a flow to batch update members
        :returns: The flow for batch updating members
        """
        batch_update_members_flow = linear_flow.Flow(
            constants.BATCH_UPDATE_MEMBERS_FLOW)
        batch_update_members_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        batch_update_members_flow.add(vthunder_tasks.SetupDeviceNetworkMap(
            requires=a10constants.VTHUNDER,
            provides=a10constants.VTHUNDER))
        batch_update_members_flow.add(a10_database_tasks.GetFlavorData(
            rebind={a10constants.LB_RESOURCE: constants.LOADBALANCER},
            provides=constants.FLAVOR))
        batch_update_members_flow.add(vthunder_tasks.GetVthunderConfByFlavor(
            inject={a10constants.VTHUNDER_CONFIG: vthunder_conf,
                    a10constants.DEVICE_CONFIG_DICT: device_dict},
            requires=(constants.LOADBALANCER, a10constants.VTHUNDER_CONFIG,
                      a10constants.DEVICE_CONFIG_DICT),
            rebind={constants.FLAVOR_DATA: constants.FLAVOR},
            provides=(a10constants.VTHUNDER_CONFIG, a10constants.USE_DEVICE_FLAVOR)))
        batch_update_members_flow.add(a10_network_tasks.GetPoolsOnThunder(
            requires=[a10constants.VTHUNDER, a10constants.USE_DEVICE_FLAVOR],
            provides=a10constants.POOLS))
        batch_update_members_flow.add(server_tasks.MemberFindNatPool(
            requires=[a10constants.VTHUNDER, constants.POOL, constants.FLAVOR],
            provides=a10constants.NAT_FLAVOR))

        # Delete old members
        batch_update_members_flow.add(
            lifecycle_tasks.MembersToErrorOnRevertTask(
                inject={constants.MEMBERS: old_members},
                name='{flow}-deleted'.format(
                    flow=constants.MEMBER_TO_ERROR_ON_REVERT_FLOW)))
        for m in old_members:
            batch_update_members_flow.add(database_tasks.MarkMemberPendingDeleteInDB(
                inject={constants.MEMBER: m},
                name='mark-member-pending-delete-in-db-' + m.id))
            batch_update_members_flow.add(model_tasks.DeleteModelObject(
                inject={constants.OBJECT: m},
                name='{flow}-{id}'.format(
                    id=m.id, flow=constants.DELETE_MODEL_OBJECT_FLOW)))
            batch_update_members_flow.add(a10_database_tasks.CountMembersWithIP(
                name='count-member-with-ip-' + m.id,
                inject={constants.MEMBER: m},
                provides=a10constants.MEMBER_COUNT_IP))
            batch_update_members_flow.add(a10_database_tasks.CountMembersWithIPPortProtocol(
                name='count-member-with-IP-port-protocol-' + m.id,
                inject={constants.MEMBER: m},
                requires=constants.POOL,
                provides=a10constants.MEMBER_COUNT_IP_PORT_PROTOCOL))
            batch_update_members_flow.add(a10_network_tasks.GetLBResourceSubnet(
                name='{flow}-{id}'.format(
                    id=m.id, flow=a10constants.GET_LB_RESOURCE_SUBNET),
                inject={a10constants.LB_RESOURCE: m},
                provides=constants.SUBNET))
            batch_update_members_flow.add(a10_database_tasks.GetNatPoolEntry(
                name='get-nat-pool-entry-' + m.id,
                inject={constants.MEMBER: m},
                requires=[a10constants.NAT_FLAVOR],
                provides=a10constants.NAT_POOL))
            batch_update_members_flow.add(a10_network_tasks.ReleaseSubnetAddressForMember(
                name='release-subnet-address-for-member-' + m.id,
                inject={constants.MEMBER: m},
                requires=[a10constants.NAT_FLAVOR, a10constants.NAT_POOL]))
            batch_update_members_flow.add(a10_database_tasks.DeleteNatPoolEntry(
                name='delete-nat-pool-entry-' + m.id,
                requires=a10constants.NAT_POOL))
            batch_update_members_flow.add(server_tasks.MemberDelete(
                name='member-delete-' + m.id,
                inject={constants.MEMBER: m},
                requires=(constants.MEMBER, a10constants.VTHUNDER, constants.POOL,
                          a10constants.MEMBER_COUNT_IP,
                          a10constants.MEMBER_COUNT_IP_PORT_PROTOCOL)))
            if CONF.a10_global.network_type == 'vlan':
                batch_update_members_flow.add(
                    vthunder_tasks.DeleteInterfaceTagIfNotInUseForMember(
                        name='delete_unused_interface_tag_in_member_' + m.id,
                        inject={constants.MEMBER: m},
                        requires=[
                            constants.MEMBER,
                            a10constants.VTHUNDER]))
            batch_update_members_flow.add(database_tasks.DeleteMemberInDB(
                inject={constants.MEMBER: m},
                name='{flow}-{id}'.format(
                    id=m.id, flow=constants.DELETE_MEMBER_INDB)))
            batch_update_members_flow.add(database_tasks.DecrementMemberQuota(
                inject={constants.MEMBER: m},
                name='{flow}-{id}'.format(
                    id=m.id, flow=constants.DECREMENT_MEMBER_QUOTA_FLOW)))
        if CONF.a10_global.handle_vrid:
            batch_update_members_flow.add(
                self.get_delete_member_vrid_internal_subflow(constants.POOL, old_members))

        # for creation of members
        batch_update_members_flow.add(lifecycle_tasks.MembersToErrorOnRevertTask(
            name='{flow}-created'.format(
                flow=constants.MEMBER_TO_ERROR_ON_REVERT_FLOW),
            inject={constants.MEMBERS: new_members}))
        for m in new_members:
            batch_update_members_flow.add(database_tasks.MarkMemberPendingCreateInDB(
                name='mark-member-pending-create-in-db-' + m.id,
                inject={constants.MEMBER: m}))
            if CONF.a10_global.validate_subnet:
                batch_update_members_flow.add(a10_network_tasks.ValidateSubnet(
                    name='validate-subnet' + m.id,
                    inject={constants.MEMBER: m}))
            batch_update_members_flow.add(a10_database_tasks.CountMembersWithIP(
                name='count-member-with-ip-' + m.id,
                inject={constants.MEMBER: m},
                provides=a10constants.MEMBER_COUNT_IP))
            batch_update_members_flow.add(self.get_batch_update_member_snat_pool_subflow(m))
            batch_update_members_flow.add(server_tasks.MemberCreate(
                name='member-create-' + m.id,
                inject={constants.MEMBER: m},
                requires=(constants.MEMBER, a10constants.VTHUNDER, constants.POOL,
                          a10constants.MEMBER_COUNT_IP, constants.FLAVOR)))
            batch_update_members_flow.add(database_tasks.MarkMemberActiveInDB(
                inject={constants.MEMBER: m},
                name='{flow}-{id}'.format(
                    id=m.id, flow=constants.MARK_MEMBER_ACTIVE_INDB)))

        # for updating of members
        batch_update_members_flow.add(
            lifecycle_tasks.MembersToErrorOnRevertTask(
                name='{flow}-updated'.format(
                    flow=constants.MEMBER_TO_ERROR_ON_REVERT_FLOW),
                # updated_members is a list of (obj, dict), only pass `obj`
                inject={constants.MEMBERS: [m[0] for m in updated_members]}))
        for m, um in updated_members:
            um.pop('id', None)
            batch_update_members_flow.add(database_tasks.MarkMemberPendingUpdateInDB(
                inject={constants.MEMBER: m},
                name='mark-member-pending-update-in-db-' + m.id))
            if CONF.a10_global.validate_subnet:
                batch_update_members_flow.add(a10_network_tasks.ValidateSubnet(
                    name='validate-subnet' + m.id,
                    inject={constants.MEMBER: m}))
            batch_update_members_flow.add(server_tasks.MemberUpdate(
                name='member-update-' + m.id,
                inject={constants.MEMBER: m},
                requires=(constants.MEMBER, a10constants.VTHUNDER,
                          constants.POOL, constants.FLAVOR)))
            batch_update_members_flow.add(database_tasks.UpdateMemberInDB(
                name='update-member-in-db-' + m.id,
                inject={constants.MEMBER: m, constants.UPDATE_DICT: um}))
            batch_update_members_flow.add(database_tasks.MarkMemberActiveInDB(
                inject={constants.MEMBER: m},
                name='{flow}-{id}'.format(
                    id=m.id, flow=constants.MARK_MEMBER_ACTIVE_INDB)))

        existing_members = [m[0] for m in updated_members]
        pool_members = new_members + existing_members
        if pool_members:
            if CONF.a10_global.handle_vrid:
                batch_update_members_flow.add(
                    self.get_handle_member_vrid_internal_subflow(pool_members))
            if CONF.a10_global.network_type == 'vlan':
                batch_update_members_flow.add(vthunder_tasks.TagInterfaceForMember(
                    name='update_tagged_interface_for_members',
                    inject={constants.MEMBER: pool_members},
                    requires=[constants.MEMBER,
                              a10constants.VTHUNDER]))

        batch_update_members_flow.add(database_tasks.MarkPoolActiveInDB(
            requires=constants.POOL))
        batch_update_members_flow.add(database_tasks.MarkLBAndListenersActiveInDB(
            requires=(constants.LOADBALANCER,
                      constants.LISTENERS)))
        batch_update_members_flow.add(vthunder_tasks.WriteMemory(
            requires=a10constants.VTHUNDER))
        batch_update_members_flow.add(a10_database_tasks.SetThunderUpdatedAt(
            requires=a10constants.VTHUNDER))

        return batch_update_members_flow

    def get_batch_update_member_snat_pool_subflow(self, member):
        batch_update_member_snat_subflow = linear_flow.Flow(
            a10constants.CREATE_MEMBER_SNAT_POOL_SUBFLOW)
        batch_update_member_snat_subflow.add(a10_database_tasks.GetNatPoolEntry(
            name='get-nat-pool-entry-' + member.id,
            inject={constants.MEMBER: member},
            requires=a10constants.NAT_FLAVOR,
            provides=a10constants.NAT_POOL))
        batch_update_member_snat_subflow.add(a10_network_tasks.ReserveSubnetAddressForMember(
            name='reserve-subnet-address-for-member' + member.id,
            inject={constants.MEMBER: member},
            requires=[a10constants.NAT_FLAVOR, a10constants.NAT_POOL],
            provides=a10constants.SUBNET_PORT))
        batch_update_member_snat_subflow.add(a10_database_tasks.UpdateNatPoolDB(
            name='update-nat-pool-DB-' + member.id,
            inject={constants.MEMBER: member},
            requires=[a10constants.NAT_FLAVOR,
                      a10constants.NAT_POOL, a10constants.SUBNET_PORT]))
        return batch_update_member_snat_subflow

    def get_batch_update_members_flow(self, old_members, new_members, updated_members, topology):
        """Create a flow to batch update members
        :returns: The flow for batch updating members
        """
        batch_update_members_flow = linear_flow.Flow(
            constants.BATCH_UPDATE_MEMBERS_FLOW)
        batch_update_members_flow.add(vthunder_tasks.VthunderInstanceBusy(
            requires=a10constants.COMPUTE_BUSY))
        batch_update_members_flow.add(database_tasks.GetAmphoraeFromLoadbalancer(
            requires=constants.LOADBALANCER,
            provides=constants.AMPHORA))
        batch_update_members_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        batch_update_members_flow.add(a10_database_tasks.GetFlavorData(
            rebind={a10constants.LB_RESOURCE: constants.LOADBALANCER},
            provides=constants.FLAVOR))
        if topology == constants.TOPOLOGY_ACTIVE_STANDBY:
            batch_update_members_flow.add(vthunder_tasks.GetMasterVThunder(
                name='get-master-vtthunder',
                requires=a10constants.VTHUNDER,
                provides=a10constants.VTHUNDER))
        batch_update_members_flow.add(a10_network_tasks.GetPoolsOnThunder(
            requires=[a10constants.VTHUNDER, a10constants.USE_DEVICE_FLAVOR],
            provides=a10constants.POOLS))
        batch_update_members_flow.add(server_tasks.MemberFindNatPool(
            name='find-nat-pool-for-member',
            requires=[a10constants.VTHUNDER, constants.POOL, constants.FLAVOR],
            provides=a10constants.NAT_FLAVOR))
        batch_update_members_flow.add(
            a10_database_tasks.GetChildProjectsOfParentPartition(
                name='get_child_project_of_parent_partition_',
                rebind={a10constants.LB_RESOURCE: constants.POOL},
                provides=a10constants.PARTITION_PROJECT_LIST))
        batch_update_members_flow.add(lifecycle_tasks.MembersToErrorOnRevertTask(
            inject={constants.MEMBERS: old_members},
            name='{flow}-deleted'.format(
                flow=constants.MEMBER_TO_ERROR_ON_REVERT_FLOW)))
        for m in old_members:
            batch_update_members_flow.add(database_tasks.MarkMemberPendingDeleteInDB(
                name='Mark-pending-delete-in-DB' + m.id,
                inject={constants.MEMBER: m}))
            batch_update_members_flow.add(model_tasks.DeleteModelObject(
                name='delete-model-object' + m.id,
                inject={constants.OBJECT: m}))
            batch_update_members_flow.add(a10_database_tasks.CountMembersWithIP(
                name='Count-members-with-ip' + m.id,
                inject={constants.MEMBER: m},
                provides=a10constants.MEMBER_COUNT_IP))
            batch_update_members_flow.add(a10_database_tasks.CountMembersWithIPPortProtocol(
                name='count-member-with-ip-address' + m.id,
                inject={constants.MEMBER: m},
                requires=constants.POOL,
                provides=a10constants.MEMBER_COUNT_IP_PORT_PROTOCOL))
            batch_update_members_flow.add(a10_database_tasks.GetNatPoolEntry(
                name='get-nat-pool' + m.id,
                inject={constants.MEMBER: m},
                requires=[a10constants.NAT_FLAVOR],
                provides=a10constants.NAT_POOL))
            batch_update_members_flow.add(a10_network_tasks.ReleaseSubnetAddressForMember(
                name='release-subnet-address-for-member' + m.id,
                inject={constants.MEMBER: m},
                requires=[a10constants.NAT_FLAVOR, a10constants.NAT_POOL]))
            batch_update_members_flow.add(a10_database_tasks.DeleteNatPoolEntry(
                name='delete-nat-pool-entry' + m.id,
                requires=a10constants.NAT_POOL))
            batch_update_members_flow.add(server_tasks.MemberDelete(
                name='member-delete' + m.id,
                inject={constants.MEMBER: m},
                requires=(constants.MEMBER, a10constants.VTHUNDER,
                          constants.POOL, a10constants.MEMBER_COUNT_IP,
                          a10constants.MEMBER_COUNT_IP_PORT_PROTOCOL)))
            batch_update_members_flow.add(database_tasks.DeleteMemberInDB(
                name='delete-member-in-db' + m.id,
                inject={constants.MEMBER: m}))
            batch_update_members_flow.add(database_tasks.DecrementMemberQuota(
                name='decrement-member-quota' + m.id,
                inject={constants.MEMBER: m}))
        if CONF.a10_global.handle_vrid:
            batch_update_members_flow.add(
                self.get_delete_member_vrid_internal_subflow(constants.POOL, old_members))

        # for creation of members
        batch_update_members_flow.add(lifecycle_tasks.MembersToErrorOnRevertTask(
            name='{flow}-created'.format(
                flow=constants.MEMBER_TO_ERROR_ON_REVERT_FLOW),
            inject={constants.MEMBERS: new_members}))
        for m in new_members:
            batch_update_members_flow.add(database_tasks.MarkMemberPendingCreateInDB(
                name='mark-member-pending-create-in-DB' + m.id,
                inject={constants.MEMBER: m}))
            if CONF.a10_global.validate_subnet:
                batch_update_members_flow.add(a10_network_tasks.ValidateSubnet(
                    name='validate-subnet' + m.id,
                    inject={constants.MEMBER: m}))
            batch_update_members_flow.add(a10_database_tasks.CountMembersWithIP(
                name='count-members-with-ip' + m.id,
                inject={constants.MEMBER: m},
                provides=a10constants.MEMBER_COUNT_IP))
            batch_update_members_flow.add(vthunder_tasks.AllowLoadbalancerForwardWithAnySource(
                name=a10constants.ALLOW_NO_SNAT + m.id,
                inject={constants.MEMBER: m},
                requires=(constants.AMPHORA)))
            batch_update_members_flow.add(server_tasks.MemberCreate(
                name='member-create' + m.id,
                inject={constants.MEMBER: m},
                requires=(constants.MEMBER, a10constants.VTHUNDER, constants.POOL,
                          a10constants.MEMBER_COUNT_IP, constants.FLAVOR)))
            batch_update_members_flow.add(database_tasks.MarkMemberActiveInDB(
                name='mark-active-in-DB' + m.id,
                inject={constants.MEMBER: m}))

        # for updating of members
        batch_update_members_flow.add(
            lifecycle_tasks.MembersToErrorOnRevertTask(
                name='{flow}-updated'.format(
                    flow=constants.MEMBER_TO_ERROR_ON_REVERT_FLOW),
                # updated_members is a list of (obj, dict), only pass `obj`
                inject={constants.MEMBERS: [m[0] for m in updated_members]}))
        for m, um in updated_members:
            um.pop('id', None)
            batch_update_members_flow.add(database_tasks.MarkMemberPendingUpdateInDB(
                inject={constants.MEMBER: m},
                name='mark-member-pending-update-in-db-' + m.id))
            if CONF.a10_global.validate_subnet:
                batch_update_members_flow.add(a10_network_tasks.ValidateSubnet(
                    name='validate-subnet' + m.id,
                    inject={constants.MEMBER: m}))
            batch_update_members_flow.add(a10_network_tasks.GetLBResourceSubnet(
                name='{flow}-{id}'.format(
                    id=m.id, flow=a10constants.GET_LB_RESOURCE_SUBNET),
                inject={a10constants.LB_RESOURCE: m},
                provides=constants.SUBNET))
            batch_update_members_flow.add(a10_database_tasks.GetLoadbalancersInProjectBySubnet(
                name='get-lb-in-project-by-subnet' + m.id,
                requires=[constants.SUBNET, a10constants.PARTITION_PROJECT_LIST],
                provides=a10constants.LOADBALANCERS_LIST))
            batch_update_members_flow.add(a10_database_tasks.CheckForL2DSRFlavor(
                name='check-for-L2DSR' + m.id,
                rebind={a10constants.LB_RESOURCE: a10constants.LOADBALANCERS_LIST},
                provides=a10constants.L2DSR_FLAVOR))
            batch_update_members_flow.add(a10_database_tasks.CountLoadbalancersInProjectBySubnet(
                name='count-lbs-in-project-by-subnet' + m.id,
                requires=[constants.SUBNET, a10constants.PARTITION_PROJECT_LIST],
                provides=a10constants.LB_COUNT_SUBNET))
            batch_update_members_flow.add(vthunder_tasks.UpdateLoadbalancerForwardWithAnySource(
                name='update-lb-forward-with-any-source' + m.id,
                requires=(constants.SUBNET, constants.AMPHORA,
                          a10constants.LB_COUNT_SUBNET, a10constants.L2DSR_FLAVOR)))
            batch_update_members_flow.add(server_tasks.MemberUpdate(
                name='member-update' + m.id,
                inject={constants.MEMBER: m},
                requires=(constants.MEMBER, a10constants.VTHUNDER,
                          constants.POOL, constants.FLAVOR)))
            batch_update_members_flow.add(database_tasks.UpdateMemberInDB(
                name='update-member-in-db' + m.id,
                inject={constants.MEMBER: m, constants.UPDATE_DICT: um}))
            batch_update_members_flow.add(database_tasks.MarkMemberActiveInDB(
                name='mark-member-active-in-db' + m.id,
                inject={constants.MEMBER: m}))
        batch_update_members_flow.add(a10_database_tasks.GetLoadBalancerListByProjectID(
            requires=a10constants.VTHUNDER,
            provides=a10constants.LOADBALANCERS_LIST))
        batch_update_members_flow.add(a10_network_tasks.CalculateDelta(
            requires=(constants.LOADBALANCER, a10constants.LOADBALANCERS_LIST),
            provides=constants.DELTAS))
        batch_update_members_flow.add(a10_network_tasks.HandleNetworkDeltas(
            requires=constants.DELTAS, provides=constants.ADDED_PORTS))
        # managing interface additions here
        if topology == constants.TOPOLOGY_SINGLE:
            batch_update_members_flow.add(vthunder_tasks.AmphoraePostMemberNetworkPlug(
                requires=(constants.LOADBALANCER, constants.ADDED_PORTS,
                          a10constants.VTHUNDER)))
            batch_update_members_flow.add(vthunder_tasks.VThunderComputeConnectivityWait(
                name=a10constants.VTHUNDER_CONNECTIVITY_WAIT,
                requires=(a10constants.VTHUNDER, constants.AMPHORA)))
            batch_update_members_flow.add(vthunder_tasks.EnableInterfaceForMembers(
                requires=[constants.ADDED_PORTS, constants.LOADBALANCER,
                          a10constants.VTHUNDER]))
        # configure member flow for HA
        if topology == constants.TOPOLOGY_ACTIVE_STANDBY:
            batch_update_members_flow.add(a10_database_tasks.GetBackupVThunderByLoadBalancer(
                name="get_backup_vThunder",
                requires=(constants.LOADBALANCER, a10constants.VTHUNDER),
                provides=a10constants.BACKUP_VTHUNDER))
            batch_update_members_flow.add(vthunder_tasks.VThunderComputeConnectivityWait(
                name="backup_compute_conn_wait_before_probe_device",
                requires=constants.AMPHORA,
                rebind={a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER}))
            batch_update_members_flow.add(vthunder_tasks.VCSSyncWait(
                name="vcs_sync_wait_before_probe_device",
                requires=a10constants.VTHUNDER))
            batch_update_members_flow.add(vthunder_tasks.AmphoraePostMemberNetworkPlug(
                requires=(constants.LOADBALANCER, constants.ADDED_PORTS,
                          a10constants.VTHUNDER)))
            batch_update_members_flow.add(vthunder_tasks.AmphoraePostMemberNetworkPlug(
                name="backup_amphora_network_plug",
                requires=[constants.ADDED_PORTS, constants.LOADBALANCER],
                rebind={a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER}))
            batch_update_members_flow.add(vthunder_tasks.VThunderComputeConnectivityWait(
                name=a10constants.MASTER_CONNECTIVITY_WAIT,
                requires=(a10constants.VTHUNDER, constants.AMPHORA)))
            batch_update_members_flow.add(vthunder_tasks.VThunderComputeConnectivityWait(
                name=a10constants.BACKUP_CONNECTIVITY_WAIT,
                requires=constants.AMPHORA,
                rebind={a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER}))
            batch_update_members_flow.add(vthunder_tasks.VCSSyncWait(
                name="backup-plug-wait-vcs-ready",
                requires=a10constants.VTHUNDER))
            batch_update_members_flow.add(vthunder_tasks.GetMasterVThunder(
                name=a10constants.GET_MASTER_VTHUNDER,
                requires=a10constants.VTHUNDER,
                provides=a10constants.VTHUNDER))
            batch_update_members_flow.add(a10_database_tasks.GetBackupVThunderByLoadBalancer(
                name="get_backup_vThunder_after_get_master",
                requires=(constants.LOADBALANCER, a10constants.VTHUNDER),
                provides=a10constants.BACKUP_VTHUNDER))
            batch_update_members_flow.add(vthunder_tasks.EnableInterfaceForMembers(
                name=a10constants.ENABLE_MASTER_VTHUNDER_INTERFACE,
                requires=[constants.ADDED_PORTS, constants.LOADBALANCER,
                          a10constants.VTHUNDER]))
            batch_update_members_flow.add(vthunder_tasks.AmphoraePostMemberNetworkPlug(
                name="amphorae-post-member-network-plug-for-master",
                requires=(constants.LOADBALANCER, constants.ADDED_PORTS,
                          a10constants.VTHUNDER)))
            batch_update_members_flow.add(
                vthunder_tasks.VThunderComputeConnectivityWait(
                    name=a10constants.CONNECTIVITY_WAIT_FOR_MASTER_VTHUNDER,
                    requires=(a10constants.VTHUNDER, constants.AMPHORA)))
            batch_update_members_flow.add(
                vthunder_tasks.VThunderComputeConnectivityWait(
                    name=a10constants.CONNECTIVITY_WAIT_FOR_BACKUP_VTHUNDER,
                    rebind={a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER},
                    requires=constants.AMPHORA))
            batch_update_members_flow.add(vthunder_tasks.VCSSyncWait(
                name="member_enable_interface_vcs_sync_wait",
                requires=a10constants.VTHUNDER))
            batch_update_members_flow.add(vthunder_tasks.GetMasterVThunder(
                name=a10constants.GET_VTHUNDER_MASTER,
                requires=a10constants.VTHUNDER,
                provides=a10constants.VTHUNDER))
            batch_update_members_flow.add(vthunder_tasks.EnableInterfaceForMembers(
                requires=[constants.ADDED_PORTS, constants.LOADBALANCER,
                          a10constants.VTHUNDER]))
        existing_members = [m[0] for m in updated_members]
        pool_members = new_members + existing_members
        if pool_members:
            if CONF.a10_global.handle_vrid:
                batch_update_members_flow.add(
                    self.get_handle_member_vrid_internal_subflow(pool_members))
        for m in new_members:
            batch_update_members_flow.add(self.get_batch_update_member_snat_pool_subflow(m))

        batch_update_members_flow.add(database_tasks.MarkPoolActiveInDB(
            requires=constants.POOL))
        batch_update_members_flow.add(database_tasks.MarkLBAndListenersActiveInDB(
            requires=[constants.LOADBALANCER, constants.LISTENERS]))
        batch_update_members_flow.add(vthunder_tasks.WriteMemory(
            requires=a10constants.VTHUNDER))
        batch_update_members_flow.add(a10_database_tasks.SetThunderUpdatedAt(
            requires=a10constants.VTHUNDER))
        return batch_update_members_flow

    def get_handle_member_vrid_internal_subflow(self, pool_members):
        handle_vrid_for_member_subflow = linear_flow.Flow(
            a10constants.DELETE_MEMBER_VRID_INTERNAL_SUBFLOW)
        handle_vrid_for_member_subflow.add(
            a10_database_tasks.GetChildProjectsOfParentPartition(
                name='get_child_project_of_parent_partition',
                rebind={a10constants.LB_RESOURCE: constants.POOL},
                provides=a10constants.PARTITION_PROJECT_LIST))
        handle_vrid_for_member_subflow.add(
            a10_network_tasks.GetAllResourceSubnet(
                inject={a10constants.MEMBERS: pool_members},
                provides=constants.SUBNET))
        handle_vrid_for_member_subflow.add(
            a10_database_tasks.GetVRIDForLoadbalancerResource(
                name='get_vrid_for_loadbalancer_resource',
                requires=[
                    a10constants.PARTITION_PROJECT_LIST,
                    a10constants.VTHUNDER],
                provides=a10constants.VRID_LIST))
        handle_vrid_for_member_subflow.add(
            a10_network_tasks.HandleVRIDFloatingIP(
                name='handle-vrid-floating-IP',
                requires=[
                    a10constants.VTHUNDER,
                    a10constants.VRID_LIST,
                    constants.SUBNET,
                    a10constants.VTHUNDER_CONFIG,
                    a10constants.USE_DEVICE_FLAVOR],
                rebind={
                    a10constants.LB_RESOURCE: constants.POOL},
                provides=a10constants.VRID_LIST))
        handle_vrid_for_member_subflow.add(
            a10_database_tasks.UpdateVRIDForLoadbalancerResource(
                name='update-vrid-for-loadbalancer-resource',
                requires=[
                    a10constants.VRID_LIST,
                    a10constants.VTHUNDER],
                rebind={
                    a10constants.LB_RESOURCE: constants.POOL}))
        return handle_vrid_for_member_subflow
