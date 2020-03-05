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


from taskflow.patterns import linear_flow, unordered_flow, graph_flow
from taskflow.patterns.graph_flow import TargetedFlow
from a10_octavia.controller.worker.tasks import vthunder_tasks
from a10_octavia.controller.worker.tasks import handler_server
from a10_octavia.controller.worker.tasks import a10_database_tasks
from a10_octavia.controller.worker.tasks import a10_network_tasks
from a10_octavia.common import a10constants
from octavia.common import constants
try:
    from octavia.controller.worker.v2.tasks import amphora_driver_tasks
    from octavia.controller.worker.v2.tasks import database_tasks
    from octavia.controller.worker.v2.tasks import lifecycle_tasks
    from octavia.controller.worker.v2.tasks import model_tasks
    from octavia.controller.worker.v2.tasks import network_tasks
except (ImportError, AttributeError):
    pass

try:
    # Stein and previous
    from octavia.controller.worker.tasks import amphora_driver_tasks
    from octavia.controller.worker.tasks import database_tasks
    from octavia.controller.worker.tasks import lifecycle_tasks
    from octavia.controller.worker.tasks import model_tasks
    from octavia.controller.worker.tasks import network_tasks
except (ImportError, AttributeError):
    pass


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

        create_member_flow.add(database_tasks.GetAmphoraeFromLoadbalancer(
            requires=constants.LOADBALANCER,
            provides=constants.AMPHORA))

        create_member_flow.add(*self._get_member_networking_subflow(topology))
        create_member_flow.add(handler_server.MemberCreate(
            requires=(constants.MEMBER, a10constants.VTHUNDER, constants.POOL)))
        create_member_flow.add(database_tasks.MarkMemberActiveInDB(
            requires=constants.MEMBER))
        create_member_flow.add(database_tasks.MarkPoolActiveInDB(
            requires=constants.POOL))
        create_member_flow.add(database_tasks.
                               MarkLBAndListenersActiveInDB(
                                   requires=(constants.LOADBALANCER,
                                             constants.LISTENERS)))
        return create_member_flow

    def _get_member_networking_subflow(self, topology):
        create_member_net_flow = graph_flow.Flow(a10constants.CREATE_MEMBER_NET_FLOW)
        parent_port = a10_network_tasks.GetParentPort(
            requires=constants.LOADBALANCER,
            provides=a10constants.PARENT_PORT)

        vlan_subflow = self.get_vlan_network_handler_subflow()
        flat_subflow = self.get_flat_network_handler_subflow()

        create_member_net_flow.add(parent_port, vlan_subflow, flat_subflow)
        create_member_net_flow.link(parent_port, vlan_subflow,
                                decider=self._is_vlan_net_decider)
        create_member_net_flow.link(parent_port, flat_subflow,
                                decider=self._is_not_vlan_net_decider)

        get_vthunder = a10_database_tasks.GetVThunderByLoadBalancer(
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER)
        iface_flat_subflow = self.get_vthunder_interface_flat_subflow(a10constants.VTHUNDER,
            enable_iface=True)
        iface_vlan_subflow = self.get_vthunder_interface_vlan_subflow(a10constants.VTHUNDER)

        create_member_net_flow.add(get_vthunder, iface_flat_subflow, iface_vlan_subflow)
        create_member_net_flow.link(get_vthunder, iface_vlan_subflow,
                                decider=self._is_vlan_net_decider)
        create_member_net_flow.link(get_vthunder, iface_flat_subflow,
                                decider=self._is_not_vlan_net_decider)
        return create_member_net_flow

    def _is_vlan_net_decider(self, history):
        """Decides if the current network topology is type vlan

        :returns: True if the parent port is associated with a trunk 
        """ 
        return history[history.keys()[0]] != None

    def _is_not_vlan_net_decider(self, history):
        """Decides if the current network topology is type flat

        :returns: True if the parent port is not associated with a trunk 
        """
        return history[history.keys()[0]] == None

    def get_delete_member_flow(self):
        """Create a flow to delete a member

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
        delete_member_flow.add(database_tasks.DeleteMemberInDB(
            requires=constants.MEMBER))
        delete_member_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))

        delete_member_flow.add(self._get_delete_member_networking_subflow())

        delete_member_flow.add(handler_server.MemberDelete(
            requires=(constants.MEMBER, a10constants.VTHUNDER, constants.POOL)))
        delete_member_flow.add(database_tasks.DecrementMemberQuota(
            requires=constants.MEMBER))
        delete_member_flow.add(database_tasks.MarkPoolActiveInDB(
            requires=constants.POOL))
        delete_member_flow.add(database_tasks.
                               MarkLBAndListenersActiveInDB(
                                   requires=[constants.LOADBALANCER,
                                             constants.LISTENERS]))

        return delete_member_flow

    def _get_delete_member_networking_subflow(self):
        delete_member_net_flow = graph_flow.Flow(a10constants.DELETE_MEMBER_NET_FLOW)

        parent_port = a10_network_tasks.GetParentPort(
            requires=constants.LOADBALANCER,
            provides=a10constants.PARENT_PORT)

        vlan_subflow = self._get_delete_vlan_network_handler_subflow()
        flat_subflow = self._get_delete_flat_network_handler_subflow()

        delete_member_net_flow.add(parent_port, vlan_subflow, flat_subflow)
        delete_member_net_flow.link(parent_port, vlan_subflow,
                                decider=self._is_vlan_net_decider)
        delete_member_net_flow.link(parent_port, flat_subflow,
                                decider=self._is_not_vlan_net_decider)
        return delete_member_net_flow

    def _get_delete_flat_network_handler_subflow(self):
        flat_network_handler_subflow = linear_flow.Flow(a10constants.FLAT_DELETE_NET_HANDLER_SUBFLOW)
        # TODO: Add flat network member delete logic here
        return flat_network_handler_subflow

    def _get_delete_vlan_network_handler_subflow(self):
        vlan_network_handler_subflow = linear_flow.Flow(a10constants.VLAN_DELETE_NET_HANDLER_SUBFLOW)
        vlan_network_handler_subflow.add(a10_network_tasks.CalculatePortDelta(
            requires=[constants.LOADBALANCER,
                      a10constants.PARENT_PORT],
            provides=a10constants.PORT_DELTAS))
        vlan_network_handler_subflow.add(a10_network_tasks.HandleDeletePortDeltas(
            requires=[a10constants.PARENT_PORT,
                      a10constants.PORT_DELTAS],
            provides=a10constants.DELETED_PORTS))
        vlan_network_handler_subflow.add(a10_network_tasks.FetchVirtEthIPs(
            rebind=[a10constants.DELETED_PORTS],
            provides=a10constants.VE_INTERFACES))
        vlan_network_handler_subflow.add(vthunder_tasks.DeleteVirtEthIfaces(
            requires=[a10constants.VTHUNDER,
                      a10constants.VE_INTERFACES,
                      constants.LOADBALANCER]))
        vlan_network_handler_subflow.add(vthunder_tasks.UnTagEthernetIfaces(
            requires=[a10constants.VTHUNDER,
                      a10constants.DELETED_PORTS,
                      constants.LOADBALANCER]))
        return vlan_network_handler_subflow

    def get_update_member_flow(self):
        """Create a flow to update a member

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
        update_member_flow.add(handler_server.MemberUpdate(
            requires=(constants.MEMBER, a10constants.VTHUNDER)))
        update_member_flow.add(database_tasks.UpdateMemberInDB(
            requires=[constants.MEMBER, constants.UPDATE_DICT]))
        update_member_flow.add(database_tasks.MarkMemberActiveInDB(
            requires=constants.MEMBER))
        update_member_flow.add(database_tasks.MarkPoolActiveInDB(
            requires=constants.POOL))
        update_member_flow.add(database_tasks.MarkLBAndListenersActiveInDB(
                               requires=[constants.LOADBALANCER,
                                         constants.LISTENERS]))

        return update_member_flow

    def get_batch_update_members_flow(self, old_members, new_members,
                                      updated_members):
        """Create a flow to batch update members

        :returns: The flow for batch updating members
        """
        batch_update_members_flow = linear_flow.Flow(
            constants.BATCH_UPDATE_MEMBERS_FLOW)
        unordered_members_flow = unordered_flow.Flow(
            constants.UNORDERED_MEMBER_UPDATES_FLOW)
        unordered_members_active_flow = unordered_flow.Flow(
            constants.UNORDERED_MEMBER_ACTIVE_FLOW)

        # Delete old members
        unordered_members_flow.add(
            lifecycle_tasks.MembersToErrorOnRevertTask(
                inject={constants.MEMBERS: old_members},
                name='{flow}-deleted'.format(
                    flow=constants.MEMBER_TO_ERROR_ON_REVERT_FLOW)))
        for m in old_members:
            unordered_members_flow.add(
                model_tasks.DeleteModelObject(
                    inject={constants.OBJECT: m},
                    name='{flow}-{id}'.format(
                        id=m.id, flow=constants.DELETE_MODEL_OBJECT_FLOW)))
            unordered_members_flow.add(database_tasks.DeleteMemberInDB(
                inject={constants.MEMBER: m},
                name='{flow}-{id}'.format(
                    id=m.id, flow=constants.DELETE_MEMBER_INDB)))
            unordered_members_flow.add(database_tasks.DecrementMemberQuota(
                inject={constants.MEMBER: m},
                name='{flow}-{id}'.format(
                    id=m.id, flow=constants.DECREMENT_MEMBER_QUOTA_FLOW)))

        # Create new members
        unordered_members_flow.add(
            lifecycle_tasks.MembersToErrorOnRevertTask(
                inject={constants.MEMBERS: new_members},
                name='{flow}-created'.format(
                    flow=constants.MEMBER_TO_ERROR_ON_REVERT_FLOW)))
        for m in new_members:
            unordered_members_active_flow.add(
                database_tasks.MarkMemberActiveInDB(
                    inject={constants.MEMBER: m},
                    name='{flow}-{id}'.format(
                        id=m.id, flow=constants.MARK_MEMBER_ACTIVE_INDB)))

        # Update existing members
        unordered_members_flow.add(
            lifecycle_tasks.MembersToErrorOnRevertTask(
                # updated_members is a list of (obj, dict), only pass `obj`
                inject={constants.MEMBERS: [m[0] for m in updated_members]},
                name='{flow}-updated'.format(
                    flow=constants.MEMBER_TO_ERROR_ON_REVERT_FLOW)))
        for m, um in updated_members:
            um.pop('id', None)
            unordered_members_active_flow.add(
                database_tasks.MarkMemberActiveInDB(
                    inject={constants.MEMBER: m},
                    name='{flow}-{id}'.format(
                        id=m.id, flow=constants.MARK_MEMBER_ACTIVE_INDB)))

        batch_update_members_flow.add(unordered_members_flow)

        # Done, do real updates
        batch_update_members_flow.add(network_tasks.CalculateDelta(
            requires=constants.LOADBALANCER,
            provides=a10constants.NIC_DELTAS))
        batch_update_members_flow.add(network_tasks.HandleNetworkDeltas(
            requires=a10constants.NIC_DELTAS, provides=constants.ADDED_PORTS))
        batch_update_members_flow.add(
            amphora_driver_tasks.AmphoraePostNetworkPlug(
                requires=(constants.LOADBALANCER, constants.ADDED_PORTS)))

        # Update the Listener (this makes the changes active on the Amp)
        batch_update_members_flow.add(amphora_driver_tasks.ListenersUpdate(
            requires=(constants.LOADBALANCER, constants.LISTENERS)))

        # Mark all the members ACTIVE here, then pool then LB/Listeners
        batch_update_members_flow.add(unordered_members_active_flow)
        batch_update_members_flow.add(database_tasks.MarkPoolActiveInDB(
            requires=constants.POOL))
        batch_update_members_flow.add(
            database_tasks.MarkLBAndListenersActiveInDB(
                requires=(constants.LOADBALANCER,
                          constants.LISTENERS)))

        return batch_update_members_flow

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
        create_member_flow.add(handler_server.MemberCreate(
            requires=(constants.MEMBER, constants.POOL)))
        create_member_flow.add(database_tasks.MarkMemberActiveInDB(
            requires=constants.MEMBER))
        create_member_flow.add(database_tasks.MarkPoolActiveInDB(
            requires=constants.POOL))
        create_member_flow.add(database_tasks.
                               MarkLBAndListenersActiveInDB(
                                   requires=(constants.LOADBALANCER,
                                             constants.LISTENERS)))
        return create_member_flow

    def get_vthunder_interface_flat_subflow(self, vthunder_constant, enable_iface=False):
        flat_network_subflow = linear_flow.Flow(a10constants.GET_FLAT_NET_SUBFLOW)
        flat_network_subflow.add(vthunder_tasks.AmphoraePostMemberNetworkPlug(
            name="{}_amphora_network_plug".format(vthunder_constant),
            rebind=[a10constants.ADDED_NICS, constants.LOADBALANCER, vthunder_constant]))
        flat_network_subflow.add(vthunder_tasks.VThunderComputeConnectivityWait(
            name="{}_compute_conn_wait".format(vthunder_constant),
            rebind=[vthunder_constant, constants.AMPHORA]))
        flat_network_subflow.add(vthunder_tasks.EnableInterfaceForMembers(
            name="{}_enable_interface".format(vthunder_constant),
            rebind=[a10constants.ADDED_NICS, constants.LOADBALANCER, vthunder_constant]))
        return flat_network_subflow

    def get_vthunder_interface_vlan_subflow(self, vthunder_constant):
        vlan_network_subflow = linear_flow.Flow(a10constants.GET_VLAN_NET_SUBFLOW)
        vlan_network_subflow.add(vthunder_tasks.TagEthernetIfaces(
            requires=[a10constants.VTHUNDER,
                      constants.ADDED_PORTS,
                      constants.LOADBALANCER]))
        vlan_network_subflow.add(a10_network_tasks.FetchVirtEthIPs(
            requires=constants.ADDED_PORTS,
            provides=a10constants.VE_INTERFACES))
        vlan_network_subflow.add(vthunder_tasks.ConfigureVirtEthIfaces(
            requires=[a10constants.VTHUNDER,
                      a10constants.VE_INTERFACES,
                      constants.LOADBALANCER]))
        return vlan_network_subflow

    def get_flat_network_handler_subflow(self):
        flat_network_handler_subflow = linear_flow.Flow(a10constants.FLAT_NET_HANDLER_SUBFLOW)
        flat_network_handler_subflow.add(a10_network_tasks.CalculateNICDelta(
            requires=constants.LOADBALANCER,
            provides=a10constants.NIC_DELTAS))
        flat_network_handler_subflow.add(a10_network_tasks.HandleNICDeltas(
            requires=a10constants.NIC_DELTAS,
            provides=a10constants.ADDED_NICS))
        return flat_network_handler_subflow

    def get_vlan_network_handler_subflow(self):
        vlan_network_handler_subflow = linear_flow.Flow(a10constants.VLAN_NET_HANDLER_SUBFLOW)
        vlan_network_handler_subflow.add(a10_network_tasks.CalculatePortDelta(
            requires=[constants.LOADBALANCER,
                      a10constants.PARENT_PORT],
            provides=a10constants.PORT_DELTAS))
        vlan_network_handler_subflow.add(a10_network_tasks.HandlePortDeltas(
            requires=[a10constants.PARENT_PORT,
                      a10constants.PORT_DELTAS],
            provides=constants.ADDED_PORTS))
        return vlan_network_handler_subflow
