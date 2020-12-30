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


from taskflow.patterns import linear_flow

from octavia.common import constants
from octavia.controller.worker.tasks import database_tasks
from octavia.controller.worker.tasks import lifecycle_tasks
from octavia.controller.worker.tasks import model_tasks

from a10_octavia.common import a10constants
from a10_octavia.controller.worker.tasks import a10_database_tasks
from a10_octavia.controller.worker.tasks import health_monitor_tasks
from a10_octavia.controller.worker.tasks import vthunder_tasks


class HealthMonitorFlows(object):

    def get_create_health_monitor_flow(self):
        """Create a flow to create a health monitor

        :returns: The flow for creating a health monitor
        """
        create_hm_flow = linear_flow.Flow(constants.CREATE_HEALTH_MONITOR_FLOW)
        create_hm_flow.add(lifecycle_tasks.HealthMonitorToErrorOnRevertTask(
            requires=[constants.HEALTH_MON,
                      constants.LISTENERS,
                      constants.LOADBALANCER]))
        create_hm_flow.add(database_tasks.MarkHealthMonitorPendingCreateInDB(
            requires=constants.HEALTH_MON))
        create_hm_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        create_hm_flow.add(a10_database_tasks.GetFlavorData(
            rebind={a10constants.LB_RESOURCE: constants.LOADBALANCER},
            provides=constants.FLAVOR))
        create_hm_flow.add(health_monitor_tasks.CreateAndAssociateHealthMonitor(
            requires=[constants.LISTENERS, constants.HEALTH_MON, a10constants.VTHUNDER,
                      constants.FLAVOR]))
        create_hm_flow.add(database_tasks.MarkHealthMonitorActiveInDB(
            requires=constants.HEALTH_MON))
        create_hm_flow.add(database_tasks.MarkPoolActiveInDB(
            requires=constants.POOL))
        create_hm_flow.add(database_tasks.MarkLBAndListenersActiveInDB(
            requires=[constants.LOADBALANCER, constants.LISTENERS]))
        create_hm_flow.add(vthunder_tasks.WriteMemory(
            name=a10constants.WRITE_MEM_FOR_LOCAL_PARTITION,
            requires=(a10constants.VTHUNDER)))
        create_hm_flow.add(vthunder_tasks.WriteMemory(
            name=a10constants.WRITE_MEM_FOR_SHARED_PARTITION,
            requires=(a10constants.VTHUNDER, a10constants.WRITE_MEM_SHARED_PART)))
        create_hm_flow.add(a10_database_tasks.SetThunderUpdatedAt(
            requires=(a10constants.VTHUNDER)))
        return create_hm_flow

    def get_delete_health_monitor_flow(self):
        """Create a flow to delete a health monitor

        :returns: The flow for deleting a health monitor
        """
        delete_hm_flow = linear_flow.Flow(constants.DELETE_HEALTH_MONITOR_FLOW)
        delete_hm_flow.add(lifecycle_tasks.HealthMonitorToErrorOnRevertTask(
            requires=[constants.HEALTH_MON,
                      constants.LISTENERS,
                      constants.LOADBALANCER]))
        delete_hm_flow.add(database_tasks.MarkHealthMonitorPendingDeleteInDB(
            requires=constants.HEALTH_MON))
        delete_hm_flow.add(model_tasks.
                           DeleteModelObject(rebind={constants.OBJECT:
                                                     constants.HEALTH_MON}))
        delete_hm_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        delete_hm_flow.add(self.get_delete_health_monitor_vthunder_subflow())
        delete_hm_flow.add(database_tasks.DeleteHealthMonitorInDB(
            requires=constants.HEALTH_MON))
        delete_hm_flow.add(database_tasks.DecrementHealthMonitorQuota(
            requires=constants.HEALTH_MON))
        delete_hm_flow.add(
            database_tasks.UpdatePoolMembersOperatingStatusInDB(
                requires=constants.POOL,
                inject={constants.OPERATING_STATUS: constants.NO_MONITOR}))
        delete_hm_flow.add(database_tasks.MarkPoolActiveInDB(
            requires=constants.POOL))
        delete_hm_flow.add(database_tasks.MarkLBAndListenersActiveInDB(
            requires=[constants.LOADBALANCER, constants.LISTENERS]))
        delete_hm_flow.add(vthunder_tasks.WriteMemory(
            name=a10constants.WRITE_MEM_FOR_LOCAL_PARTITION,
            requires=(a10constants.VTHUNDER)))
        delete_hm_flow.add(vthunder_tasks.WriteMemory(
            name=a10constants.WRITE_MEM_FOR_SHARED_PARTITION,
            requires=(a10constants.VTHUNDER, a10constants.WRITE_MEM_SHARED_PART)))
        delete_hm_flow.add(a10_database_tasks.SetThunderUpdatedAt(
            requires=(a10constants.VTHUNDER)))
        return delete_hm_flow

    def get_delete_health_monitor_vthunder_subflow(self):
        delete_hm_vthunder_subflow = linear_flow.Flow(
            a10constants.DELETE_HEALTH_MONITOR_VTHUNDER_SUBFLOW)
        delete_hm_vthunder_subflow.add(health_monitor_tasks.DeleteHealthMonitor(
            requires=[constants.HEALTH_MON, a10constants.VTHUNDER]))
        return delete_hm_vthunder_subflow

    def get_update_health_monitor_flow(self):
        """Create a flow to update a health monitor

        :returns: The flow for updating a health monitor
        """
        update_hm_flow = linear_flow.Flow(constants.UPDATE_HEALTH_MONITOR_FLOW)
        update_hm_flow.add(lifecycle_tasks.HealthMonitorToErrorOnRevertTask(
            requires=[constants.HEALTH_MON,
                      constants.LISTENERS,
                      constants.LOADBALANCER]))
        update_hm_flow.add(database_tasks.MarkHealthMonitorPendingUpdateInDB(
            requires=constants.HEALTH_MON))
        update_hm_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        update_hm_flow.add(a10_database_tasks.GetFlavorData(
            rebind={a10constants.LB_RESOURCE: constants.LOADBALANCER},
            provides=constants.FLAVOR))
        update_hm_flow.add(health_monitor_tasks.UpdateHealthMonitor(
            requires=[constants.LISTENERS, constants.HEALTH_MON,
                      a10constants.VTHUNDER, constants.UPDATE_DICT,
                      constants.FLAVOR]))
        update_hm_flow.add(database_tasks.UpdateHealthMonInDB(
            requires=[constants.HEALTH_MON, constants.UPDATE_DICT]))
        update_hm_flow.add(database_tasks.MarkHealthMonitorActiveInDB(
            requires=constants.HEALTH_MON))
        update_hm_flow.add(database_tasks.MarkPoolActiveInDB(
            requires=constants.POOL))
        update_hm_flow.add(database_tasks.MarkLBAndListenersActiveInDB(
            requires=[constants.LOADBALANCER, constants.LISTENERS]))
        update_hm_flow.add(vthunder_tasks.WriteMemory(
            name=a10constants.WRITE_MEM_FOR_LOCAL_PARTITION,
            requires=(a10constants.VTHUNDER)))
        update_hm_flow.add(vthunder_tasks.WriteMemory(
            name=a10constants.WRITE_MEM_FOR_SHARED_PARTITION,
            requires=(a10constants.VTHUNDER, a10constants.WRITE_MEM_SHARED_PART)))
        update_hm_flow.add(a10_database_tasks.SetThunderUpdatedAt(
            requires=(a10constants.VTHUNDER)))
        return update_hm_flow
