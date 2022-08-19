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
from octavia.controller.worker.v1.tasks import database_tasks
from octavia.controller.worker.v1.tasks import lifecycle_tasks
from octavia.controller.worker.v1.tasks import model_tasks

from a10_octavia.common import a10constants
from a10_octavia.controller.worker.tasks import a10_database_tasks
from a10_octavia.controller.worker.tasks import l7rule_tasks
from a10_octavia.controller.worker.tasks import vthunder_tasks


class L7RuleFlows(object):

    def get_create_l7rule_flow(self, topology):
        """Create a flow to create an L7 rule
        :returns: The flow for creating an L7 rule
        """
        create_l7rule_flow = linear_flow.Flow(constants.CREATE_L7RULE_FLOW)
        create_l7rule_flow.add(lifecycle_tasks.L7RuleToErrorOnRevertTask(
            requires=[constants.L7RULE,
                      constants.LISTENERS,
                      constants.LOADBALANCER]))
        create_l7rule_flow.add(vthunder_tasks.VthunderInstanceBusy(
            requires=a10constants.COMPUTE_BUSY))

        create_l7rule_flow.add(database_tasks.MarkL7RulePendingCreateInDB(
            requires=constants.L7RULE))
        create_l7rule_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        if topology == constants.TOPOLOGY_ACTIVE_STANDBY:
            create_l7rule_flow.add(vthunder_tasks.GetMasterVThunder(
                name=a10constants.GET_MASTER_VTHUNDER,
                requires=a10constants.VTHUNDER,
                provides=a10constants.VTHUNDER))
        create_l7rule_flow.add(l7rule_tasks.CreateL7Rule(
            requires=[constants.L7RULE, constants.LISTENERS, a10constants.VTHUNDER]))
        create_l7rule_flow.add(database_tasks.MarkL7RuleActiveInDB(
            requires=constants.L7RULE))
        create_l7rule_flow.add(database_tasks.MarkL7PolicyActiveInDB(
            requires=constants.L7POLICY))
        create_l7rule_flow.add(database_tasks.MarkLBAndListenersActiveInDB(
            requires=[constants.LOADBALANCER, constants.LISTENERS]))
        create_l7rule_flow.add(vthunder_tasks.WriteMemory(
            requires=a10constants.VTHUNDER))
        create_l7rule_flow.add(a10_database_tasks.SetThunderUpdatedAt(
            requires=a10constants.VTHUNDER))
        return create_l7rule_flow

    def get_fully_populated_create_l7rule_flow(self, topology, listeners, l7rule):
        """Create fully populated l7rule"""

        sf_name = constants.CREATE_L7RULE_FLOW + '_' + l7rule.id
        create_l7rule_flow = linear_flow.Flow(sf_name)
        create_l7rule_flow.add(l7rule_tasks.L7RuleToErrorOnRevertTask(
            name=sf_name + a10constants.FULLY_POPULATED_ERROR_ON_REVERT,
            requires=constants.L7RULE,
            inject={constants.L7RULE: l7rule}))

        create_l7rule_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            name=sf_name + '-' + a10constants.GET_VTHUNDER_BY_LB,
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        if topology == constants.TOPOLOGY_ACTIVE_STANDBY:
            create_l7rule_flow.add(vthunder_tasks.GetMasterVThunder(
                name=sf_name + '_' + a10constants.GET_MASTER_VTHUNDER,
                requires=a10constants.VTHUNDER,
                provides=a10constants.VTHUNDER))
        create_l7rule_flow.add(l7rule_tasks.CreateL7Rule(
            name=sf_name + a10constants.FULLY_POPULATED_CREATE_L7RULE,
            requires=[constants.L7RULE, constants.LISTENERS, a10constants.VTHUNDER],
            inject={constants.L7RULE: l7rule, constants.LISTENERS: listeners}))
        create_l7rule_flow.add(database_tasks.MarkL7RuleActiveInDB(
            name=sf_name + a10constants.FULLY_POPULATED_MARK_L7RULE_ACTIVE,
            requires=constants.L7RULE,
            inject={constants.L7RULE: l7rule}))
        return create_l7rule_flow

    def get_delete_l7rule_flow(self, topology):
        """Create a flow to delete an L7 rule
        :returns: The flow for deleting an L7 rule
        """
        delete_l7rule_flow = linear_flow.Flow(constants.DELETE_L7RULE_FLOW)
        delete_l7rule_flow.add(lifecycle_tasks.L7RuleToErrorOnRevertTask(
            requires=[constants.L7RULE,
                      constants.LISTENERS,
                      constants.LOADBALANCER]))
        delete_l7rule_flow.add(vthunder_tasks.VthunderInstanceBusy(
            requires=a10constants.COMPUTE_BUSY))

        delete_l7rule_flow.add(database_tasks.MarkL7RulePendingDeleteInDB(
            requires=constants.L7RULE))
        delete_l7rule_flow.add(model_tasks.DeleteModelObject(
            rebind={constants.OBJECT: constants.L7RULE}))
        delete_l7rule_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            requires=constants.LOADBALANCER, provides=a10constants.VTHUNDER))
        if topology == constants.TOPOLOGY_ACTIVE_STANDBY:
            delete_l7rule_flow.add(vthunder_tasks.GetMasterVThunder(
                name=a10constants.GET_MASTER_VTHUNDER,
                requires=a10constants.VTHUNDER,
                provides=a10constants.VTHUNDER))
        delete_l7rule_flow.add(l7rule_tasks.DeleteL7Rule(
            requires=[constants.L7RULE, constants.LISTENERS, a10constants.VTHUNDER]))
        delete_l7rule_flow.add(database_tasks.DeleteL7RuleInDB(
            requires=constants.L7RULE))
        delete_l7rule_flow.add(database_tasks.MarkL7PolicyActiveInDB(
            requires=constants.L7POLICY))
        delete_l7rule_flow.add(database_tasks.MarkLBAndListenersActiveInDB(
            requires=[constants.LOADBALANCER, constants.LISTENERS]))
        delete_l7rule_flow.add(vthunder_tasks.WriteMemory(
            requires=a10constants.VTHUNDER))
        delete_l7rule_flow.add(a10_database_tasks.SetThunderUpdatedAt(
            requires=a10constants.VTHUNDER))
        return delete_l7rule_flow

    def get_update_l7rule_flow(self, topology):
        """Create a flow to update an L7 rule
        :returns: The flow for updating an L7 rule
        """
        update_l7rule_flow = linear_flow.Flow(constants.UPDATE_L7RULE_FLOW)
        update_l7rule_flow.add(lifecycle_tasks.L7RuleToErrorOnRevertTask(
            requires=[constants.L7RULE,
                      constants.LISTENERS,
                      constants.LOADBALANCER]))
        update_l7rule_flow.add(vthunder_tasks.VthunderInstanceBusy(
            requires=a10constants.COMPUTE_BUSY))

        update_l7rule_flow.add(database_tasks.MarkL7RulePendingUpdateInDB(
            requires=constants.L7RULE))
        update_l7rule_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        if topology == constants.TOPOLOGY_ACTIVE_STANDBY:
            update_l7rule_flow.add(vthunder_tasks.GetMasterVThunder(
                requires=a10constants.VTHUNDER,
                provides=a10constants.VTHUNDER))
        update_l7rule_flow.add(
            l7rule_tasks.UpdateL7Rule(
                requires=[
                    constants.L7RULE,
                    constants.LISTENERS,
                    a10constants.VTHUNDER,
                    constants.UPDATE_DICT]))
        update_l7rule_flow.add(database_tasks.UpdateL7RuleInDB(
            requires=[constants.L7RULE, constants.UPDATE_DICT]))
        update_l7rule_flow.add(database_tasks.MarkL7RuleActiveInDB(
            requires=constants.L7RULE))
        update_l7rule_flow.add(database_tasks.MarkL7PolicyActiveInDB(
            requires=constants.L7POLICY))
        update_l7rule_flow.add(database_tasks.MarkLBAndListenersActiveInDB(
            requires=[constants.LOADBALANCER, constants.LISTENERS]))
        update_l7rule_flow.add(vthunder_tasks.WriteMemory(
            requires=a10constants.VTHUNDER))
        update_l7rule_flow.add(a10_database_tasks.SetThunderUpdatedAt(
            requires=a10constants.VTHUNDER))
        return update_l7rule_flow
