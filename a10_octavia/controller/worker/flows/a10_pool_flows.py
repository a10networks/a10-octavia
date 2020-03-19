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
from a10_octavia.controller.worker.tasks import a10_database_tasks
from a10_octavia.controller.worker.tasks import persist_tasks
from a10_octavia.controller.worker.tasks import service_group_tasks
from a10_octavia.controller.worker.tasks import virtual_port_tasks


class PoolFlows(object):

    def get_create_pool_flow(self):
        """Create a flow to create a pool

        :returns: The flow for creating a pool
        """
        create_pool_flow = linear_flow.Flow(constants.CREATE_POOL_FLOW)
        create_pool_flow.add(lifecycle_tasks.PoolToErrorOnRevertTask(
            requires=[constants.POOL,
                      constants.LISTENERS,
                      constants.LOADBALANCER]))
        create_pool_flow.add(database_tasks.MarkPoolPendingCreateInDB(
            requires=constants.POOL))
        create_pool_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        create_pool = service_group_tasks.PoolCreate(
            requires=[constants.POOL, a10constants.VTHUNDER],
            provides=constants.POOL)
        create_pool_flow.add(*self._get_sess_pers_subflow(create_pool))
        create_pool_flow.add(virtual_port_tasks.ListenersUpdate(
            requires=[constants.LOADBALANCER, constants.LISTENERS, a10constants.VTHUNDER]))
        create_pool_flow.add(database_tasks.MarkPoolActiveInDB(
            requires=constants.POOL))
        create_pool_flow.add(database_tasks.MarkLBAndListenersActiveInDB(
            requires=[constants.LOADBALANCER, constants.LISTENERS]))

        return create_pool_flow

    def get_delete_pool_flow(self):
        """Create a flow to delete a pool

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
        delete_pool_flow.add(virtual_port_tasks.ListenersUpdate(
            requires=[constants.LOADBALANCER, constants.LISTENERS, a10constants.VTHUNDER]))
        delete_pool_flow.add(persist_tasks.DeleteSessionPersistence(
            requires=[a10constants.VTHUNDER, constants.POOL]))
        delete_pool_flow.add(service_group_tasks.PoolDelete(
            requires=[constants.POOL, a10constants.VTHUNDER]))
        delete_pool_flow.add(database_tasks.DeletePoolInDB(
            requires=constants.POOL))
        delete_pool_flow.add(database_tasks.DecrementPoolQuota(
            requires=[constants.POOL, constants.POOL_CHILD_COUNT]))
        delete_pool_flow.add(database_tasks.MarkLBAndListenersActiveInDB(
            requires=[constants.LOADBALANCER, constants.LISTENERS]))

        return delete_pool_flow

    def get_delete_pool_flow_internal(self, name):
        """Create a flow to delete a pool, etc.

        :returns: The flow for deleting a pool
        """
        delete_pool_flow = linear_flow.Flow(constants.DELETE_POOL_FLOW)
        # health monitor should cascade
        # members should cascade
        delete_pool_flow.add(database_tasks.MarkPoolPendingDeleteInDB(
            name='mark_pool_pending_delete_in_db_' + name,
            requires=constants.POOL,
            rebind={constants.POOL: name}))
        delete_pool_flow.add(database_tasks.CountPoolChildrenForQuota(
            name='count_pool_children_for_quota_' + name,
            requires=constants.POOL,
            provides=constants.POOL_CHILD_COUNT,
            rebind={constants.POOL: name}))
        delete_pool_flow.add(model_tasks.DeleteModelObject(
            name='delete_model_object_' + name,
            rebind={constants.OBJECT: name}))
        delete_pool_flow.add(database_tasks.DeletePoolInDB(
            name='delete_pool_in_db_' + name,
            requires=constants.POOL,
            rebind={constants.POOL: name}))
        delete_pool_flow.add(database_tasks.DecrementPoolQuota(
            name='decrement_pool_quota_' + name,
            requires=[constants.POOL, constants.POOL_CHILD_COUNT],
            rebind={constants.POOL: name}))

        return delete_pool_flow

    def get_update_pool_flow(self):
        """Create a flow to update a pool

        :returns: The flow for updating a pool
        """
        update_pool_flow = linear_flow.Flow(constants.UPDATE_POOL_FLOW)
        update_pool_flow.add(lifecycle_tasks.PoolToErrorOnRevertTask(
            requires=[constants.POOL,
                      constants.LISTENERS,
                      constants.LOADBALANCER]))
        update_pool_flow.add(database_tasks.MarkPoolPendingUpdateInDB(
            requires=constants.POOL))
        update_pool_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        update_pool = service_group_tasks.PoolUpdate(
            requires=[constants.POOL, a10constants.VTHUNDER, constants.UPDATE_DICT],
            provides=constants.POOL)
        update_pool_flow.add(*self._get_sess_pers_subflow(update_pool))
        update_pool_flow.add(virtual_port_tasks.ListenersUpdate(
            requires=[constants.LOADBALANCER, constants.LISTENERS, a10constants.VTHUNDER]))
        update_pool_flow.add(database_tasks.UpdatePoolInDB(
            requires=[constants.POOL, constants.UPDATE_DICT]))
        update_pool_flow.add(database_tasks.MarkPoolActiveInDB(
            requires=constants.POOL))
        update_pool_flow.add(database_tasks.MarkLBAndListenersActiveInDB(
            requires=[constants.LOADBALANCER, constants.LISTENERS]))

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
