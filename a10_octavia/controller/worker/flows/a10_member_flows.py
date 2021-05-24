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
        delete_member_flow.add(database_tasks.DeleteMemberInDB(
            requires=constants.MEMBER))
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
            requires=[constants.MEMBER, a10constants.VTHUNDER, constants.POOL,
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
        delete_member_flow.add(self.get_delete_member_vrid_subflow())
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

    def get_rack_vthunder_delete_member_flow(self):
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
        delete_member_flow.add(server_tasks.MemberFindNatPool(
            requires=[constants.MEMBER, a10constants.VTHUNDER, constants.POOL,
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
            requires=constants.MEMBER, provides=a10constants.POOL_COUNT_IP,
            rebind={constants.MEMBER: member_id}))

        # NAT pools database and pools clean up for flavor
        delete_member_thunder_subflow.add(a10_database_tasks.GetFlavorData(
            name='get_flavor_data_' + member_id,
            rebind={a10constants.LB_RESOURCE: constants.LOADBALANCER},
            provides=constants.FLAVOR))
        delete_member_thunder_subflow.add(server_tasks.MemberFindNatPool(
            name='member_find_nat_pool_' + member_id,
            requires=[constants.MEMBER, a10constants.VTHUNDER, constants.POOL,
                      constants.FLAVOR], provides=a10constants.NAT_FLAVOR,
            rebind={constants.MEMBER: member_id, constants.POOL: pool}))
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
                requires=[constants.SUBNET, a10constants.PARTITION_PROJECT_LIST],
                provides=a10constants.LB_COUNT_SUBNET))
        delete_member_vrid_subflow.add(
            a10_database_tasks.CountMembersInProjectBySubnet(
                requires=[constants.SUBNET, a10constants.PARTITION_PROJECT_LIST],
                provides=a10constants.MEMBER_COUNT))
        delete_member_vrid_subflow.add(
            a10_database_tasks.GetVRIDForLoadbalancerResource(
                requires=a10constants.PARTITION_PROJECT_LIST,
                provides=a10constants.VRID_LIST))
        delete_member_vrid_subflow.add(
            a10_network_tasks.DeleteVRIDPort(
                requires=[
                    a10constants.VTHUNDER,
                    a10constants.VRID_LIST,
                    constants.SUBNET,
                    a10constants.LB_COUNT_SUBNET,
                    a10constants.MEMBER_COUNT],
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
                requires=[a10constants.MEMBER_LIST, a10constants.PARTITION_PROJECT_LIST],
                rebind={a10constants.MEMBER_LIST: pool_members},
                provides=a10constants.SUBNET_LIST))
        delete_member_vrid_subflow.add(
            a10_database_tasks.GetVRIDForLoadbalancerResource(
                name='get_vrid_for_loadbalancer_resource' + pool,
                requires=a10constants.PARTITION_PROJECT_LIST,
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
                requires=a10constants.PARTITION_PROJECT_LIST,
                provides=a10constants.VRID_LIST))
        handle_vrid_for_member_subflow.add(
            a10_network_tasks.HandleVRIDFloatingIP(
                requires=[
                    a10constants.VTHUNDER,
                    a10constants.VRID_LIST,
                    constants.SUBNET],
                rebind={
                    a10constants.LB_RESOURCE: constants.MEMBER},
                provides=a10constants.VRID_LIST))
        handle_vrid_for_member_subflow.add(
            a10_database_tasks.UpdateVRIDForLoadbalancerResource(
                requires=a10constants.VRID_LIST,
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
        update_member_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        if topology == constants.TOPOLOGY_ACTIVE_STANDBY:
            update_member_flow.add(vthunder_tasks.GetMasterVThunder(
                name=a10constants.GET_MASTER_VTHUNDER,
                requires=a10constants.VTHUNDER,
                provides=a10constants.VTHUNDER))
        update_member_flow.add(self.handle_vrid_for_member_subflow())
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

    def get_rack_vthunder_update_member_flow(self):
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
        update_member_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        update_member_flow.add(vthunder_tasks.SetupDeviceNetworkMap(
            requires=a10constants.VTHUNDER,
            provides=a10constants.VTHUNDER))
        # Handle VRID settings
        update_member_flow.add(self.handle_vrid_for_member_subflow())
        update_member_flow.add(a10_database_tasks.GetFlavorData(
            rebind={a10constants.LB_RESOURCE: constants.LOADBALANCER},
            provides=constants.FLAVOR))
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

    def get_rack_vthunder_create_member_flow(self):
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
        create_member_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        create_member_flow.add(vthunder_tasks.SetupDeviceNetworkMap(
            requires=a10constants.VTHUNDER,
            provides=a10constants.VTHUNDER))
        create_member_flow.add(self.handle_vrid_for_member_subflow())
        if CONF.a10_global.network_type == 'vlan':
            create_member_flow.add(vthunder_tasks.TagInterfaceForMember(
                requires=[constants.MEMBER,
                          a10constants.VTHUNDER]))
        create_member_flow.add(a10_database_tasks.CountMembersWithIP(
            requires=constants.MEMBER, provides=a10constants.MEMBER_COUNT_IP))
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

    def get_create_member_snat_pool_subflow(self):
        create_member_snat_subflow = linear_flow.Flow(
            a10constants.CREATE_MEMBER_SNAT_POOL_SUBFLOW)
        create_member_snat_subflow.add(server_tasks.MemberFindNatPool(
            requires=[constants.MEMBER, a10constants.VTHUNDER, constants.POOL,
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
