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
        create_member_flow.add(database_tasks.MarkMemberPendingCreateInDB(
            requires=constants.MEMBER))
        create_member_flow.add(a10_network_tasks.CalculateDelta(
            requires=constants.LOADBALANCER,
            provides=constants.DELTAS))
        create_member_flow.add(a10_network_tasks.HandleNetworkDeltas(
            requires=constants.DELTAS, provides=constants.ADDED_PORTS))
        create_member_flow.add(database_tasks.GetAmphoraeFromLoadbalancer(
            requires=constants.LOADBALANCER,
            provides=constants.AMPHORA))
        create_member_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        # managing interface additions here
        create_member_flow.add(vthunder_tasks.AmphoraePostMemberNetworkPlug(
            requires=(constants.LOADBALANCER, constants.ADDED_PORTS, a10constants.VTHUNDER)))
        create_member_flow.add(vthunder_tasks.VThunderComputeConnectivityWait(
            requires=(a10constants.VTHUNDER, constants.AMPHORA)))
        create_member_flow.add(vthunder_tasks.EnableInterfaceForMembers(
            requires=[constants.ADDED_PORTS, constants.LOADBALANCER, a10constants.VTHUNDER]))
        # configure member flow for HA
        if topology == constants.TOPOLOGY_ACTIVE_STANDBY:
            create_member_flow.add(a10_database_tasks.GetBackupVThunderByLoadBalancer(
                name="get_backup_vThunder",
                requires=constants.LOADBALANCER,
                provides=a10constants.BACKUP_VTHUNDER))
            create_member_flow.add(
                vthunder_tasks.AmphoraePostMemberNetworkPlug(
                    name="backup_amphora_network_plug",
                    requires=[constants.ADDED_PORTS, constants.LOADBALANCER],
                    rebind={a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER}))
            create_member_flow.add(vthunder_tasks.VThunderComputeConnectivityWait(
                name="backup_compute_conn_wait",
                requires=constants.AMPHORA,
                rebind={a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER}))
            create_member_flow.add(
                vthunder_tasks.EnableInterfaceForMembers(
                    name="backup_enable_interface",
                    requires=[constants.ADDED_PORTS, constants.LOADBALANCER],
                    rebind={a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER}))

        create_member_flow.add(server_tasks.MemberCreate(
            requires=(constants.MEMBER, a10constants.VTHUNDER, constants.POOL)))
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
        return create_member_flow

    def get_delete_member_flow(self):
        """Flow to delete a member on VThunder

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
        delete_member_flow.add(server_tasks.MemberDelete(
            requires=(constants.MEMBER, a10constants.VTHUNDER, constants.POOL)))
        delete_member_flow.add(database_tasks.DeleteMemberInDB(
            requires=constants.MEMBER))
        delete_member_flow.add(database_tasks.DecrementMemberQuota(
            requires=constants.MEMBER))
        delete_member_flow.add(database_tasks.MarkPoolActiveInDB(
            requires=constants.POOL))
        delete_member_flow.add(database_tasks.
                               MarkLBAndListenersActiveInDB(
                                   requires=[constants.LOADBALANCER,
                                             constants.LISTENERS]))
        delete_member_flow.add(vthunder_tasks.WriteMemory(
            requires=a10constants.VTHUNDER))
        return delete_member_flow

    def get_rack_vthunder_delete_member_flow(self):
        """Flow to delete a member in Thunder devices

        :returns: The flow for deleting a member
        """
        delete_member_flow = linear_flow.Flow(constants.DELETE_MEMBER_FLOW)
        delete_member_flow.add(a10_database_tasks.
                               CountMembersInProject(
                                   requires=constants.MEMBER,
                                   provides=a10constants.MEMBER_COUNT))
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
        delete_member_flow.add(server_tasks.MemberDelete(
            requires=(constants.MEMBER, a10constants.VTHUNDER, constants.POOL)))
        if CONF.a10_global.network_type == 'vlan':
            delete_member_flow.add(vthunder_tasks.DeleteInterfaceTagIfNotInUseForMember(
                requires=[constants.MEMBER, a10constants.VTHUNDER]))
        # Handle VRID setting
        delete_member_flow.add(self.get_delete_member_vrid_subflow())
        delete_member_flow.add(database_tasks.DeleteMemberInDB(
            requires=constants.MEMBER))
        delete_member_flow.add(database_tasks.DecrementMemberQuota(
            requires=constants.MEMBER))
        delete_member_flow.add(database_tasks.MarkPoolActiveInDB(
            requires=constants.POOL))
        delete_member_flow.add(database_tasks.
                               MarkLBAndListenersActiveInDB(
                                   requires=[constants.LOADBALANCER,
                                             constants.LISTENERS]))
        delete_member_flow.add(vthunder_tasks.WriteMemory(
            requires=a10constants.VTHUNDER))
        return delete_member_flow

    def get_delete_member_vthunder_internal_subflow(self, member_id):
        delete_member_thunder_subflow = linear_flow.Flow(
            a10constants.DELETE_MEMBER_VTHUNDER_INTERNAL_SUBFLOW)
        delete_member_thunder_subflow.add(vthunder_tasks.SetupDeviceNetworkMap(
            name='setup_device_network_map_' + member_id,
            requires=a10constants.VTHUNDER,
            provides=a10constants.VTHUNDER))
        delete_member_thunder_subflow.add(server_tasks.MemberDelete(
            name='delete_thunder_member_' + member_id,
            requires=(constants.MEMBER, a10constants.VTHUNDER, constants.POOL),
            rebind={constants.MEMBER: member_id}))
        if CONF.a10_global.network_type == 'vlan':
            delete_member_thunder_subflow.add(vthunder_tasks.DeleteInterfaceTagIfNotInUseForMember(
                name='delete_unused_interface_tag_in_member_' + member_id,
                requires=[constants.MEMBER, a10constants.VTHUNDER],
                rebind={constants.MEMBER: member_id}))

        return delete_member_thunder_subflow

    def get_delete_member_vrid_subflow(self):
        delete_member_vrid_subflow = linear_flow.Flow(
            a10constants.DELETE_MEMBER_VRID_SUBFLOW)
        delete_member_vrid_subflow.add(a10_database_tasks.GetVRIDForProjectMember(
            requires=constants.MEMBER,
            provides=a10constants.VRID))
        delete_member_vrid_subflow.add(a10_network_tasks.DeleteMemberVRIDPort(
            requires=[a10constants.VTHUNDER, a10constants.VRID, a10constants.MEMBER_COUNT],
            provides=a10constants.DELETE_VRID))
        delete_member_vrid_subflow.add(a10_database_tasks.DeleteVRIDEntry(
            requires=[a10constants.VRID, a10constants.DELETE_VRID]))
        return delete_member_vrid_subflow

    def get_delete_member_vrid_internal_subflow(self, member_id):
        delete_member_vrid_subflow = linear_flow.Flow(
            a10constants.DELETE_MEMBER_VRID_INTERNAL_SUBFLOW)
        delete_member_vrid_subflow.add(a10_database_tasks.GetVRIDForProjectMember(
            name='get_vrid_for_project_member_' + member_id,
            requires=constants.MEMBER,
            provides=a10constants.VRID,
            rebind={constants.MEMBER: member_id}))
        delete_member_vrid_subflow.add(a10_network_tasks.DeleteMemberVRIDPort(
            name='delete_member_vrid_port_' + member_id,
            requires=[a10constants.VTHUNDER,
                      a10constants.VRID, a10constants.MEMBER_COUNT],
            provides=a10constants.DELETE_VRID))
        delete_member_vrid_subflow.add(a10_database_tasks.DeleteVRIDEntry(
            name='delete_vrid_entry_' + member_id,
            requires=[a10constants.VRID, a10constants.DELETE_VRID]))
        return delete_member_vrid_subflow

    def handle_vrid_for_member_subflow(self):
        handle_vrid_for_member_subflow = linear_flow.Flow(a10constants.HANDLE_VRID_MEMBER_SUBFLOW)
        handle_vrid_for_member_subflow.add(a10_database_tasks.GetVRIDForProjectMember(
            requires=constants.MEMBER,
            provides=a10constants.VRID))
        handle_vrid_for_member_subflow.add(a10_network_tasks.HandleVRIDFloatingIP(
            requires=[constants.MEMBER, a10constants.VTHUNDER, a10constants.VRID],
            provides=a10constants.PORT))
        handle_vrid_for_member_subflow.add(a10_database_tasks.UpdateVRIDForProjectMember(
            requires=[constants.MEMBER, a10constants.VRID, a10constants.PORT]))
        return handle_vrid_for_member_subflow

    def get_update_member_flow(self):
        """Flow to update a member

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
        update_member_flow.add(server_tasks.MemberUpdate(
            requires=(constants.MEMBER, a10constants.VTHUNDER)))
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
        update_member_flow.add(server_tasks.MemberUpdate(
            requires=(constants.MEMBER, a10constants.VTHUNDER)))
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
        create_member_flow.add(server_tasks.MemberCreate(
            requires=(constants.MEMBER, a10constants.VTHUNDER, constants.POOL)))
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
        return create_member_flow
