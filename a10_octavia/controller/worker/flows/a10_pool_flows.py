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


from taskflow.patterns import graph_flow
from taskflow.patterns import linear_flow

from octavia.common import constants
from octavia.controller.worker.tasks import database_tasks
from octavia.controller.worker.tasks import lifecycle_tasks
from octavia.controller.worker.tasks import model_tasks

from a10_octavia.common import a10constants
from a10_octavia.controller.worker.flows import a10_health_monitor_flows
from a10_octavia.controller.worker.flows import a10_member_flows
from a10_octavia.controller.worker.tasks import a10_database_tasks
from a10_octavia.controller.worker.tasks import a10_network_tasks
from a10_octavia.controller.worker.tasks import persist_tasks
from a10_octavia.controller.worker.tasks import service_group_tasks
from a10_octavia.controller.worker.tasks import virtual_port_tasks
from a10_octavia.controller.worker.tasks import vthunder_tasks

from oslo_config import cfg
CONF = cfg.CONF


class PoolFlows(object):

    def __init__(self):
        self.hm_flow = a10_health_monitor_flows.HealthMonitorFlows()
        self.member_flow = a10_member_flows.MemberFlows()

    def get_create_pool_flow(self, topology):
        """Create a flow to create a pool

        :returns: The flow for creating a pool
        """

        create_pool_flow = linear_flow.Flow(constants.CREATE_POOL_FLOW)
        create_pool_flow.add(lifecycle_tasks.PoolToErrorOnRevertTask(
            requires=[constants.POOL,
                      constants.LISTENERS,
                      constants.LOADBALANCER]))
        create_pool_flow.add(vthunder_tasks.VthunderInstanceBusy(
            requires=a10constants.COMPUTE_BUSY))

        create_pool_flow.add(database_tasks.MarkPoolPendingCreateInDB(
            requires=constants.POOL))
        create_pool_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        if topology == constants.TOPOLOGY_ACTIVE_STANDBY:
            create_pool_flow.add(vthunder_tasks.GetMasterVThunder(
                name=a10constants.GET_MASTER_VTHUNDER,
                requires=a10constants.VTHUNDER,
                provides=a10constants.VTHUNDER))
        create_pool_flow.add(a10_database_tasks.GetFlavorData(
            rebind={a10constants.LB_RESOURCE: constants.POOL},
            provides=constants.FLAVOR))
        create_pool = service_group_tasks.PoolCreate(
            requires=[constants.POOL, a10constants.VTHUNDER, constants.FLAVOR],
            provides=constants.POOL)
        create_pool_flow.add(*self._get_sess_pers_subflow(create_pool))
        create_pool_flow.add(virtual_port_tasks.ListenerUpdateForPool(
            requires=[constants.LOADBALANCER, constants.LISTENER, a10constants.VTHUNDER]))
        create_pool_flow.add(database_tasks.MarkPoolActiveInDB(
            requires=constants.POOL))
        create_pool_flow.add(database_tasks.MarkLBAndListenersActiveInDB(
            requires=[constants.LOADBALANCER, constants.LISTENERS]))
        create_pool_flow.add(vthunder_tasks.WriteMemory(
            requires=a10constants.VTHUNDER))
        create_pool_flow.add(a10_database_tasks.SetThunderUpdatedAt(
            requires=a10constants.VTHUNDER))

        return create_pool_flow

    def get_delete_pool_flow(self, members, health_mon, store, topology):
        """Create a flow to delete a pool

        :returns: The flow for deleting a pool
        """
        delete_pool_flow = linear_flow.Flow(constants.DELETE_POOL_FLOW)
        delete_pool_flow.add(lifecycle_tasks.PoolToErrorOnRevertTask(
            requires=[constants.POOL,
                      constants.LISTENERS,
                      constants.LOADBALANCER]))
        delete_pool_flow.add(vthunder_tasks.VthunderInstanceBusy(
            requires=a10constants.COMPUTE_BUSY))

        delete_pool_flow.add(database_tasks.MarkPoolPendingDeleteInDB(
            requires=constants.POOL))
        delete_pool_flow.add(database_tasks.CountPoolChildrenForQuota(
            requires=constants.POOL, provides=constants.POOL_CHILD_COUNT))
        delete_pool_flow.add(model_tasks.DeleteModelObject(
            rebind={constants.OBJECT: constants.POOL}))
        # Get VThunder details from database
        delete_pool_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        if topology == constants.TOPOLOGY_ACTIVE_STANDBY:
            delete_pool_flow.add(vthunder_tasks.GetMasterVThunder(
                name=a10constants.GET_MASTER_VTHUNDER,
                requires=a10constants.VTHUNDER,
                provides=a10constants.VTHUNDER))
        delete_pool_flow.add(virtual_port_tasks.ListenerUpdateForPool(
            requires=[constants.LOADBALANCER, constants.LISTENER, a10constants.VTHUNDER]))
        delete_pool_flow.add(persist_tasks.DeleteSessionPersistence(
            requires=[a10constants.VTHUNDER, constants.POOL]))
        # Delete pool children
        delete_pool_flow.add(self._get_delete_member_vthunder_subflow(members, store))
        delete_pool_flow.add(self._get_delete_health_monitor_vthunder_subflow(health_mon))
        delete_pool_flow.add(service_group_tasks.PoolDelete(
            requires=[constants.POOL, a10constants.VTHUNDER]))
        delete_pool_flow.add(database_tasks.DeletePoolInDB(
            requires=constants.POOL))
        # Interface delete.
        delete_pool_flow.add(a10_database_tasks.GetLoadBalancerListByProjectID(
            requires=a10constants.VTHUNDER,
            provides=a10constants.LOADBALANCERS_LIST))
        delete_pool_flow.add(a10_network_tasks.CalculateDelta(
            requires=(constants.LOADBALANCER, a10constants.LOADBALANCERS_LIST),
            provides=constants.DELTAS))
        delete_pool_flow.add(a10_network_tasks.HandleNetworkDeltas(
            requires=constants.DELTAS, provides=constants.ADDED_PORTS))
        delete_pool_flow.add(
            vthunder_tasks.AmphoraePostNetworkUnplug(
                requires=(
                    constants.LOADBALANCER,
                    constants.ADDED_PORTS,
                    a10constants.VTHUNDER)))
        delete_pool_flow.add(database_tasks.GetAmphoraeFromLoadbalancer(
            requires=constants.LOADBALANCER,
            provides=constants.AMPHORA))
        delete_pool_flow.add(vthunder_tasks.VThunderComputeConnectivityWait(
            requires=(a10constants.VTHUNDER, constants.AMPHORA)))
        delete_pool_flow.add(database_tasks.DecrementPoolQuota(
            requires=[constants.POOL, constants.POOL_CHILD_COUNT]))
        delete_pool_flow.add(database_tasks.MarkLBAndListenersActiveInDB(
            requires=[constants.LOADBALANCER, constants.LISTENERS]))
        delete_pool_flow.add(vthunder_tasks.WriteMemory(
            requires=a10constants.VTHUNDER))
        delete_pool_flow.add(a10_database_tasks.SetThunderUpdatedAt(
            requires=a10constants.VTHUNDER))

        return delete_pool_flow

    def _get_delete_health_monitor_vthunder_subflow(self, health_mon, cascade=False):
        delete_hm_vthunder_subflow = linear_flow.Flow(
            a10constants.DELETE_HEALTH_MONITOR_SUBFLOW_WITH_POOL_DELETE_FLOW)
        if health_mon:
            if cascade:
                delete_hm_vthunder_subflow.add(
                    self.hm_flow.get_delete_health_monitor_vthunder_subflow(health_mon))
            else:
                delete_hm_vthunder_subflow.add(
                    self.hm_flow.get_delete_health_monitor_vthunder_subflow())
        return delete_hm_vthunder_subflow

    def _get_delete_member_vthunder_subflow(self, members, store, pool=constants.POOL):
        delete_member_vthunder_subflow = linear_flow.Flow(
            a10constants.DELETE_MEMBERS_SUBFLOW_WITH_POOL_DELETE_FLOW)
        member_store = {}
        for member in members:
            member_store[member.id] = member
            delete_member_vthunder_subflow.add(
                self.member_flow.get_delete_member_vthunder_internal_subflow(member.id, pool))
        if members and CONF.a10_global.handle_vrid:
            delete_member_vthunder_subflow.add(
                self.member_flow.get_delete_member_vrid_internal_subflow(pool, members))
        store.update(member_store)
        return delete_member_vthunder_subflow

    def get_update_pool_flow(self, topology):
        """Create a flow to update a pool

        :returns: The flow for updating a pool
        """
        update_pool_flow = linear_flow.Flow(constants.UPDATE_POOL_FLOW)
        update_pool_flow.add(lifecycle_tasks.PoolToErrorOnRevertTask(
            requires=[constants.POOL,
                      constants.LISTENERS,
                      constants.LOADBALANCER]))
        update_pool_flow.add(vthunder_tasks.VthunderInstanceBusy(
            requires=a10constants.COMPUTE_BUSY))

        update_pool_flow.add(database_tasks.MarkPoolPendingUpdateInDB(
            requires=constants.POOL))
        update_pool_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        if topology == constants.TOPOLOGY_ACTIVE_STANDBY:
            update_pool_flow.add(vthunder_tasks.GetMasterVThunder(
                name=a10constants.GET_MASTER_VTHUNDER,
                requires=a10constants.VTHUNDER,
                provides=a10constants.VTHUNDER))
        update_pool_flow.add(a10_database_tasks.GetFlavorData(
            rebind={a10constants.LB_RESOURCE: constants.POOL},
            provides=constants.FLAVOR))
        update_pool = service_group_tasks.PoolUpdate(
            requires=[constants.POOL, a10constants.VTHUNDER,
                      constants.UPDATE_DICT, constants.FLAVOR],
            provides=constants.POOL)
        update_pool_flow.add(*self._get_sess_pers_subflow(update_pool))
        update_pool_flow.add(virtual_port_tasks.ListenerUpdateForPool(
            requires=[constants.LOADBALANCER, constants.LISTENER, a10constants.VTHUNDER]))
        update_pool_flow.add(database_tasks.UpdatePoolInDB(
            requires=[constants.POOL, constants.UPDATE_DICT]))
        update_pool_flow.add(database_tasks.MarkPoolActiveInDB(
            requires=constants.POOL))
        update_pool_flow.add(database_tasks.MarkLBAndListenersActiveInDB(
            requires=[constants.LOADBALANCER, constants.LISTENERS]))
        update_pool_flow.add(vthunder_tasks.WriteMemory(
            requires=a10constants.VTHUNDER))
        update_pool_flow.add(a10_database_tasks.SetThunderUpdatedAt(
            requires=a10constants.VTHUNDER))

        return update_pool_flow

    def _get_sess_pers_subflow(self, pool_task):
        get_pool_create_with_sess_pers = graph_flow.Flow(a10constants.HANDLE_SESS_PERS)
        sess_pers = persist_tasks.HandleSessionPersistenceDelta(
            requires=[a10constants.VTHUNDER, constants.POOL])
        get_pool_create_with_sess_pers.add(pool_task, sess_pers)
        get_pool_create_with_sess_pers.link(pool_task, sess_pers,
                                            decider=self._is_sess_pers_decider)
        return get_pool_create_with_sess_pers

    def _is_sess_pers_decider(self, history):
        """Decides if the pool has session persistence
        :returns: True if if pool has session persistence
        """
        return history[history.keys()[0]].session_persistence is not None

    def get_cascade_delete_pool_internal_flow(
            self, pool_name, members, pool_listener_name, health_mon):
        """Create a flow to delete a pool, etc.
        :returns: The flow for deleting a pool
        """
        store = {}
        delete_pool_flow = linear_flow.Flow(constants.DELETE_POOL_FLOW)
        # health monitor should cascade
        # members should cascade
        delete_pool_flow.add(database_tasks.MarkPoolPendingDeleteInDB(
            name='mark_pool_pending_delete_in_db_' + pool_name,
            requires=constants.POOL,
            rebind={constants.POOL: pool_name}))
        delete_pool_flow.add(database_tasks.CountPoolChildrenForQuota(
            name='count_pool_children_for_quota_' + pool_name,
            requires=constants.POOL,
            provides=constants.POOL_CHILD_COUNT,
            rebind={constants.POOL: pool_name}))
        delete_pool_flow.add(virtual_port_tasks.ListenerUpdateForPool(
            name='listener_update_for_pool_' + pool_name,
            requires=[constants.LOADBALANCER, constants.LISTENER, a10constants.VTHUNDER],
            rebind={constants.LISTENER: pool_listener_name}))
        delete_pool_flow.add(persist_tasks.DeleteSessionPersistence(
            name='delete_session_persistence_' + pool_name,
            requires=[a10constants.VTHUNDER, constants.POOL],
            rebind={constants.POOL: pool_name}))
        delete_pool_flow.add(model_tasks.DeleteModelObject(
            name='delete_model_object_' + pool_name,
            rebind={constants.OBJECT: pool_name}))
        delete_pool_flow.add(a10_network_tasks.GetPoolsOnThunder(
            name='get_pools_on_thunder_' + pool_name,
            requires=[a10constants.VTHUNDER, a10constants.USE_DEVICE_FLAVOR],
            provides=a10constants.POOLS))
        # Delete pool children
        delete_pool_flow.add(self._get_delete_member_vthunder_subflow(members, store, pool_name))
        delete_pool_flow.add(self._get_delete_health_monitor_vthunder_subflow(health_mon, True))
        delete_pool_flow.add(service_group_tasks.PoolDelete(
            name='pool_delete_' + pool_name,
            requires=[constants.POOL, a10constants.VTHUNDER],
            rebind={constants.POOL: pool_name}))
        delete_pool_flow.add(database_tasks.DeletePoolInDB(
            name='delete_pool_in_db_' + pool_name,
            requires=constants.POOL,
            rebind={constants.POOL: pool_name}))
        delete_pool_flow.add(database_tasks.DecrementPoolQuota(
            name='decrement_pool_quota_' + pool_name,
            requires=[constants.POOL, constants.POOL_CHILD_COUNT],
            rebind={constants.POOL: pool_name}))

        return (delete_pool_flow, store)

    def get_delete_pool_rack_flow(self, members, health_mon, store):
        """Create a flow to delete a pool rack

        :returns: The flow for deleting a pool
        """
        delete_pool_flow = linear_flow.Flow(constants.DELETE_POOL_FLOW)
        delete_pool_flow.add(lifecycle_tasks.PoolToErrorOnRevertTask(
            requires=[constants.POOL,
                      constants.LISTENERS,
                      constants.LOADBALANCER]))
        delete_pool_flow.add(database_tasks.MarkPoolPendingDeleteInDB(
            requires=constants.POOL))
        delete_pool_flow.add(database_tasks.CountPoolChildrenForQuota(
            requires=constants.POOL, provides=constants.POOL_CHILD_COUNT))
        delete_pool_flow.add(model_tasks.DeleteModelObject(
            rebind={constants.OBJECT: constants.POOL}))
        # Get VThunder details from database
        delete_pool_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        delete_pool_flow.add(virtual_port_tasks.ListenerUpdateForPool(
            requires=[constants.LOADBALANCER, constants.LISTENER, a10constants.VTHUNDER]))
        delete_pool_flow.add(persist_tasks.DeleteSessionPersistence(
            requires=[a10constants.VTHUNDER, constants.POOL]))
        delete_pool_flow.add(vthunder_tasks.SetupDeviceNetworkMap(
            requires=a10constants.VTHUNDER,
            provides=a10constants.VTHUNDER))

        # Device Flavor
        delete_pool_flow.add(a10_database_tasks.GetFlavorData(
            rebind={a10constants.LB_RESOURCE: constants.LOADBALANCER},
            provides=constants.FLAVOR))
        delete_pool_flow.add(vthunder_tasks.GetVthunderConfByFlavor(
            requires=(constants.LOADBALANCER, a10constants.VTHUNDER_CONFIG,
                      a10constants.DEVICE_CONFIG_DICT),
            rebind={constants.FLAVOR_DATA: constants.FLAVOR},
            provides=(a10constants.VTHUNDER_CONFIG, a10constants.USE_DEVICE_FLAVOR)))
        delete_pool_flow.add(a10_network_tasks.GetPoolsOnThunder(
            requires=[a10constants.VTHUNDER, a10constants.USE_DEVICE_FLAVOR],
            provides=a10constants.POOLS))

        # Delete pool children
        delete_pool_flow.add(self._get_delete_member_vthunder_subflow(members, store))
        delete_pool_flow.add(self._get_delete_health_monitor_vthunder_subflow(health_mon))
        delete_pool_flow.add(service_group_tasks.PoolDelete(
            requires=[constants.POOL, a10constants.VTHUNDER]))
        delete_pool_flow.add(database_tasks.DeletePoolInDB(
            requires=constants.POOL))
        delete_pool_flow.add(database_tasks.DecrementPoolQuota(
            requires=[constants.POOL, constants.POOL_CHILD_COUNT]))
        delete_pool_flow.add(database_tasks.MarkLBAndListenersActiveInDB(
            requires=[constants.LOADBALANCER, constants.LISTENERS]))
        delete_pool_flow.add(vthunder_tasks.WriteMemory(
            requires=a10constants.VTHUNDER))
        delete_pool_flow.add(a10_database_tasks.SetThunderUpdatedAt(
            requires=a10constants.VTHUNDER))

        return delete_pool_flow
