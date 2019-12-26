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
from taskflow.patterns import graph_flow
from taskflow.patterns import linear_flow
from taskflow.patterns import unordered_flow

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

from a10_octavia.controller.worker.tasks import vthunder_tasks
from a10_octavia.common import a10constants
from a10_octavia.controller.worker.tasks import a10_database_tasks
from a10_octavia.controller.worker.tasks import a10_compute_tasks as compute_tasks

CONF = cfg.CONF

import logging
LOG = logging.getLogger(__name__)


class VThunderFlows(object):

    def __init__(self):
        # for some reason only this has the values from the config file
        # self.REST_AMPHORA_DRIVER = (CONF.controller_worker.amphora_driver ==
        #                            'amphora_haproxy_rest_driver')
        pass

    def get_create_vthunder_flow(self):
        """Creates a flow to create an amphora.

        :returns: The flow for creating the amphora
        """
        create_vthunder_flow = linear_flow.Flow(constants.CREATE_AMPHORA_FLOW)
        create_vthunder_flow.add(a10_database_tasks.CreateVThunderInDB(
            provides=constants.AMPHORA_ID))

        return create_vthunder_flow

    def get_vthunder_for_lb_subflow(
            self, prefix, role=constants.ROLE_STANDALONE):
        """Tries to allocate a spare amphora to a loadbalancer if none

        exists, create a new amphora.
        """

        sf_name = prefix + '-' + constants.GET_AMPHORA_FOR_LB_SUBFLOW

        # We need a graph flow here for a conditional flow
        amp_for_lb_flow = graph_flow.Flow(sf_name)

        amp_for_lb_flow.add(database_tasks.ReloadLoadBalancer(
            name=sf_name + '-' + 'reload_loadbalancer',
            requires=constants.LOADBALANCER_ID,
            provides=constants.LOADBALANCER))

        # Setup the task that maps an amphora to a load balancer
        allocate_and_associate_amp = a10_database_tasks.MapLoadbalancerToAmphora(
            name=sf_name + '-' + constants.MAP_LOADBALANCER_TO_AMPHORA,
            requires=constants.LOADBALANCER,
            provides=constants.AMPHORA_ID)

        # Define a subflow for if we successfully map an amphora
        # map_lb_to_amp = self._get_post_map_lb_subflow(prefix, role)
        # Define a subflow for if we can't map an amphora
        create_amp = self._get_create_amp_for_lb_subflow(prefix, role)

        map_lb_to_vthunder = self._get_vthunder_for_amphora_subflow(
            prefix, role)

        # Add them to the graph flow
        amp_for_lb_flow.add(allocate_and_associate_amp,
                            map_lb_to_vthunder, create_amp)

        # Setup the decider for the path if we can map an amphora
        amp_for_lb_flow.link(allocate_and_associate_amp, map_lb_to_vthunder,
                             decider=self._allocate_amp_to_lb_decider,
                             decider_depth='flow')
        # Setup the decider for the path if we can't map an amphora
        amp_for_lb_flow.link(allocate_and_associate_amp, create_amp,
                             decider=self._create_new_amp_for_lb_decider,
                             decider_depth='flow')

        return amp_for_lb_flow

    def _get_post_map_lb_subflow(self, prefix, role):
        """Set amphora type after mapped to lb."""

        sf_name = prefix + '-' + constants.POST_MAP_AMP_TO_LB_SUBFLOW
        post_map_amp_to_lb = linear_flow.Flow(
            sf_name)

        post_map_amp_to_lb.add(database_tasks.ReloadAmphora(
            name=sf_name + '-' + constants.RELOAD_AMPHORA,
            requires=constants.AMPHORA_ID,
            provides=constants.AMPHORA))

        if role == constants.ROLE_MASTER:
            post_map_amp_to_lb.add(database_tasks.MarkAmphoraMasterInDB(
                name=sf_name + '-' + constants.MARK_AMP_MASTER_INDB,
                requires=constants.AMPHORA))
        elif role == constants.ROLE_BACKUP:
            post_map_amp_to_lb.add(database_tasks.MarkAmphoraBackupInDB(
                name=sf_name + '-' + constants.MARK_AMP_BACKUP_INDB,
                requires=constants.AMPHORA))
        elif role == constants.ROLE_STANDALONE:
            post_map_amp_to_lb.add(database_tasks.MarkAmphoraStandAloneInDB(
                name=sf_name + '-' + constants.MARK_AMP_STANDALONE_INDB,
                requires=constants.AMPHORA))

        return post_map_amp_to_lb

    def _get_post_map_lb_subflow(self, prefix, role):
        """Set amphora type after mapped to lb."""

        sf_name = prefix + '-' + constants.POST_MAP_AMP_TO_LB_SUBFLOW
        post_map_amp_to_lb = linear_flow.Flow(
            sf_name)

        post_map_amp_to_lb.add(database_tasks.ReloadAmphora(
            name=sf_name + '-' + constants.RELOAD_AMPHORA,
            requires=constants.AMPHORA_ID,
            provides=constants.AMPHORA))

        if role == constants.ROLE_MASTER:
            post_map_amp_to_lb.add(database_tasks.MarkAmphoraMasterInDB(
                name=sf_name + '-' + constants.MARK_AMP_MASTER_INDB,
                requires=constants.AMPHORA))
        elif role == constants.ROLE_BACKUP:
            post_map_amp_to_lb.add(database_tasks.MarkAmphoraBackupInDB(
                name=sf_name + '-' + constants.MARK_AMP_BACKUP_INDB,
                requires=constants.AMPHORA))
        elif role == constants.ROLE_STANDALONE:
            post_map_amp_to_lb.add(database_tasks.MarkAmphoraStandAloneInDB(
                name=sf_name + '-' + constants.MARK_AMP_STANDALONE_INDB,
                requires=constants.AMPHORA))

        return post_map_amp_to_lb

    def _get_create_amp_for_lb_subflow(self, prefix, role):
        """Create a new amphora for lb."""

        sf_name = prefix + '-' + constants.CREATE_AMP_FOR_LB_SUBFLOW
        create_amp_for_lb_subflow = linear_flow.Flow(sf_name)
        create_amp_for_lb_subflow.add(database_tasks.CreateAmphoraInDB(
            name=sf_name + '-' + constants.CREATE_AMPHORA_INDB,
            provides=constants.AMPHORA_ID))

        require_server_group_id_condition = (
            role in (constants.ROLE_BACKUP, constants.ROLE_MASTER) and
            CONF.nova.enable_anti_affinity)

        if require_server_group_id_condition:
            create_amp_for_lb_subflow.add(compute_tasks.ComputeCreate(
                name=sf_name + '-' + constants.COMPUTE_CREATE,
                requires=(
                    constants.AMPHORA_ID,
                    constants.BUILD_TYPE_PRIORITY,
                    constants.SERVER_GROUP_ID,
                ),
                provides=constants.COMPUTE_ID))
        else:
            create_amp_for_lb_subflow.add(compute_tasks.ComputeCreate(
                name=sf_name + '-' + constants.COMPUTE_CREATE,
                requires=(
                    constants.AMPHORA_ID,
                    constants.BUILD_TYPE_PRIORITY,
                ),
                provides=constants.COMPUTE_ID))

        create_amp_for_lb_subflow.add(database_tasks.UpdateAmphoraComputeId(
            name=sf_name + '-' + constants.UPDATE_AMPHORA_COMPUTEID,
            requires=(constants.AMPHORA_ID, constants.COMPUTE_ID)))
        create_amp_for_lb_subflow.add(database_tasks.MarkAmphoraBootingInDB(
            name=sf_name + '-' + constants.MARK_AMPHORA_BOOTING_INDB,
            requires=(constants.AMPHORA_ID, constants.COMPUTE_ID)))
        create_amp_for_lb_subflow.add(compute_tasks.ComputeActiveWait(
            name=sf_name + '-' + constants.COMPUTE_WAIT,
            requires=(constants.COMPUTE_ID, constants.AMPHORA_ID),
            provides=constants.COMPUTE_OBJ))
        create_amp_for_lb_subflow.add(database_tasks.UpdateAmphoraInfo(
            name=sf_name + '-' + constants.UPDATE_AMPHORA_INFO,
            requires=(constants.AMPHORA_ID, constants.COMPUTE_OBJ),
            provides=constants.AMPHORA))
        # create vThunder entry in custom DB
        create_amp_for_lb_subflow.add(database_tasks.ReloadLoadBalancer(
            name=sf_name + '-' + 'reload_loadbalancer',
            requires=constants.LOADBALANCER_ID,
            provides=constants.LOADBALANCER))
        create_amp_for_lb_subflow.add(a10_database_tasks.CreteVthunderEntry(
            name=sf_name + '-' + 'create_vThunder_entry_in_database',
            requires=(constants.AMPHORA, constants.LOADBALANCER),
            inject={"role": role}))
        # Get VThunder details from database
        create_amp_for_lb_subflow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            name=sf_name + '-' + 'Get_Loadbalancer_from_db',
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        create_amp_for_lb_subflow.add(
            vthunder_tasks.VThunderComputeConnectivityWait(
                name=sf_name + '-' + constants.AMP_COMPUTE_CONNECTIVITY_WAIT,
                requires=(a10constants.VTHUNDER, constants.AMPHORA)))
        # create_amp_for_lb_subflow.add(amphora_driver_tasks.AmphoraFinalize(
        #    name=sf_name + '-' + constants.AMPHORA_FINALIZE,
        #    requires=constants.AMPHORA))
        create_amp_for_lb_subflow.add(
            database_tasks.MarkAmphoraAllocatedInDB(
                name=sf_name + '-' + constants.MARK_AMPHORA_ALLOCATED_INDB,
                requires=(constants.AMPHORA, constants.LOADBALANCER_ID)))
        create_amp_for_lb_subflow.add(database_tasks.ReloadAmphora(
            name=sf_name + '-' + constants.RELOAD_AMPHORA,
            requires=constants.AMPHORA_ID,
            provides=constants.AMPHORA))
        if role == constants.ROLE_MASTER:
            create_amp_for_lb_subflow.add(database_tasks.MarkAmphoraMasterInDB(
                name=sf_name + '-' + constants.MARK_AMP_MASTER_INDB,
                requires=constants.AMPHORA))
        elif role == constants.ROLE_BACKUP:
            create_amp_for_lb_subflow.add(database_tasks.MarkAmphoraBackupInDB(
                name=sf_name + '-' + constants.MARK_AMP_BACKUP_INDB,
                requires=constants.AMPHORA))
        elif role == constants.ROLE_STANDALONE:
            create_amp_for_lb_subflow.add(
                database_tasks.MarkAmphoraStandAloneInDB(
                    name=sf_name + '-' + constants.MARK_AMP_STANDALONE_INDB,
                    requires=constants.AMPHORA))

        return create_amp_for_lb_subflow

    def _allocate_amp_to_lb_decider(self, history):
        """decides if the lb shall be mapped to a spare amphora

        :return: True if a spare amphora exists in DB
        """

        return list(history.values())[0] is not None

    def _create_new_amp_for_lb_decider(self, history):
        """decides if a new amphora must be created for the lb

        :return: True if there is no spare amphora
        """

        return list(history.values())[0] is None

    def _get_vthunder_for_amphora_subflow(self, prefix, role):
        """Create amphora in existing vThunder."""

        sf_name = prefix + '-' + 'VTHUNDER_TO_AMPHORA_SUBFLOW'
        vthunder_for_amphora_subflow = linear_flow.Flow(sf_name)
        vthunder_for_amphora_subflow.add(database_tasks.CreateAmphoraInDB(
            name=sf_name + '-' + constants.CREATE_AMPHORA_INDB,
            provides=constants.AMPHORA_ID))

        require_server_group_id_condition = (
            role in (constants.ROLE_BACKUP, constants.ROLE_MASTER) and
            CONF.nova.enable_anti_affinity)
        # Relaod LB
        # vthunder_for_amphora_subflow.add(database_tasks.ReloadLoadBalancer(
        #    name=sf_name + '-' + 'reload_loadbalancer',
        #   requires=constants.LOADBALANCER_ID,
        #   provides=constants.LOADBALANCER))
        vthunder_for_amphora_subflow.add(a10_database_tasks.GetComputeForProject(
            name=sf_name + '-' + 'get_compute_id',
            requires=constants.LOADBALANCER,
            provides=constants.COMPUTE_ID))
        vthunder_for_amphora_subflow.add(database_tasks.UpdateAmphoraComputeId(
            name=sf_name + '-' + constants.UPDATE_AMPHORA_COMPUTEID,
            requires=(constants.AMPHORA_ID, constants.COMPUTE_ID)))
        vthunder_for_amphora_subflow.add(compute_tasks.ComputeActiveWait(
            name=sf_name + '-' + constants.COMPUTE_WAIT,
            requires=(constants.COMPUTE_ID, constants.AMPHORA_ID),
            provides=constants.COMPUTE_OBJ))
        vthunder_for_amphora_subflow.add(database_tasks.UpdateAmphoraInfo(
            name=sf_name + '-' + constants.UPDATE_AMPHORA_INFO,
            requires=(constants.AMPHORA_ID, constants.COMPUTE_OBJ),
            provides=constants.AMPHORA))
        # create vThunder entry in custom DB
        vthunder_for_amphora_subflow.add(a10_database_tasks.CreteVthunderEntry(
            name=sf_name + '-' + 'create_vThunder_entry_in_database',
            requires=(constants.AMPHORA, constants.LOADBALANCER),
            inject={"role": role}))
        # Get VThunder details from database
        vthunder_for_amphora_subflow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            name=sf_name + '-' + 'Get_Loadbalancer_from_db',
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        vthunder_for_amphora_subflow.add(
            database_tasks.MarkAmphoraAllocatedInDB(
                name=sf_name + '-' + constants.MARK_AMPHORA_ALLOCATED_INDB,
                requires=(constants.AMPHORA, constants.LOADBALANCER_ID)))
        vthunder_for_amphora_subflow.add(database_tasks.ReloadAmphora(
            name=sf_name + '-' + constants.RELOAD_AMPHORA,
            requires=constants.AMPHORA_ID,
            provides=constants.AMPHORA))
        if role == constants.ROLE_MASTER:
            vthunder_for_amphora_subflow.add(database_tasks.MarkAmphoraMasterInDB(
                name=sf_name + '-' + constants.MARK_AMP_MASTER_INDB,
                requires=constants.AMPHORA))
        elif role == constants.ROLE_BACKUP:
            vthunder_for_amphora_subflow.add(database_tasks.MarkAmphoraBackupInDB(
                name=sf_name + '-' + constants.MARK_AMP_BACKUP_INDB,
                requires=constants.AMPHORA))
        elif role == constants.ROLE_STANDALONE:
            vthunder_for_amphora_subflow.add(
                database_tasks.MarkAmphoraStandAloneInDB(
                    name=sf_name + '-' + constants.MARK_AMP_STANDALONE_INDB,
                    requires=constants.AMPHORA))
        return vthunder_for_amphora_subflow

    def get_vrrp_subflow(self, prefix):
        sf_name = prefix + '-' + constants.GET_VRRP_SUBFLOW
        vrrp_subflow = linear_flow.Flow(sf_name)
        # Get VThunder details from database
        vrrp_subflow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            name=sf_name + '-' + 'Get_Loadbalancer_from_db',
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        vrrp_subflow.add(a10_database_tasks.GetBackupVThunderByLoadBalancer(
            name=sf_name + '-' + 'get_backup_loadbalancer_from_db',
            requires=constants.LOADBALANCER,
            provides=a10constants.BACKUP_VTHUNDER))
        vrrp_subflow.add(vthunder_tasks.ConfigureVRRP(
            name=sf_name + '-' + 'configure_vrrp',
            requires=(a10constants.VTHUNDER, a10constants.BACKUP_VTHUNDER),
            provides=(a10constants.VRRP_STATUS)))
        vrrp_subflow.add(vthunder_tasks.ConfigureVRID(
            name=sf_name + '-' + 'configure_vrid',
            requires=(a10constants.VTHUNDER, a10constants.BACKUP_VTHUNDER, a10constants.VRRP_STATUS)))
        vrrp_subflow.add(vthunder_tasks.ConfigureVRRPSync(
            name=sf_name + '-' + 'configure_vrrp_sync',
            requires=(a10constants.VTHUNDER, a10constants.BACKUP_VTHUNDER, a10constants.VRRP_STATUS)))
        vrrp_subflow.add(vthunder_tasks.VThunderComputeConnectivityWait(
                name=sf_name + '-' + 'wait_for_master_sync',
                requires=(a10constants.VTHUNDER, constants.AMPHORA)))
        vrrp_subflow.add(vthunder_tasks.VThunderComputeConnectivityWait(
                name=sf_name + '-' + 'wait_for_backup_sync',
                rebind=(a10constants.BACKUP_VTHUNDER, constants.AMPHORA)))
        vrrp_subflow.add(vthunder_tasks.ConfigureaVCS(
            name=sf_name + '-' + 'configure_avcs_sync',
            requires=(a10constants.VTHUNDER, a10constants.BACKUP_VTHUNDER, a10constants.VRRP_STATUS)))
        return vrrp_subflow

    def get_rack_vthunder_for_lb_subflow(
            self, vthunder_conf, prefix, role=constants.ROLE_STANDALONE):
        """ reload the loadbalancer and make entry in database"""

        sf_name = prefix + '-' + constants.GET_AMPHORA_FOR_LB_SUBFLOW

        amp_for_lb_flow = linear_flow.Flow(sf_name)

        amp_for_lb_flow.add(database_tasks.ReloadLoadBalancer(
            name=sf_name + '-' + 'reload_loadbalancer',
            requires=constants.LOADBALANCER_ID,
            provides=constants.LOADBALANCER))
        amp_for_lb_flow.add(a10_database_tasks.CreateRackVthunderEntry(
            name=sf_name + '-' + 'create_rack_vThunder_entry_in_database',
            inject={a10constants.VTHUNDER_CONFIG: vthunder_conf},
            requires=(constants.LOADBALANCER, a10constants.VTHUNDER_CONFIG)))
        amp_for_lb_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))

        return amp_for_lb_flow
    
    def delete_existing_vthunder(self, vthunder):
        LOG.info("deleting thunder subflow")
        delete_existing_vthunder_flow = linear_flow.Flow(constants.DELETE_AMPHORA_FLOW)
        delete_existing_vthunder_flow.add(lifecycle_tasks.AmphoraToErrorOnRevertTask(
            requires=constants.AMPHORA))
        delete_existing_vthunder_flow.add(
            database_tasks.MarkAmphoraPendingDeleteInDB(
                rebind={constants.AMPHORA: constants.FAILED_AMPHORA},
                requires=constants.AMPHORA))
        delete_existing_vthunder_flow.add(
            database_tasks.MarkAmphoraHealthBusy(
                rebind={constants.AMPHORA: constants.FAILED_AMPHORA},
                requires=constants.AMPHORA))
        delete_existing_vthunder_flow.add(compute_tasks.ComputeDelete(
            rebind={constants.AMPHORA: constants.FAILED_AMPHORA},
            requires=constants.AMPHORA))
        delete_existing_vthunder_flow.add(network_tasks.WaitForPortDetach(
            rebind={constants.AMPHORA: constants.FAILED_AMPHORA},
            requires=constants.AMPHORA))
        
        delete_existing_vthunder_flow.add(database_tasks.MarkAmphoraDeletedInDB(
            rebind={constants.AMPHORA: constants.FAILED_AMPHORA},
            requires=constants.AMPHORA))
        if not load_balancer:
            delete_existing_vthunder_flow.add(database_tasks.
                                    DisableAmphoraHealthMonitoring(
                                    rebind={constants.AMPHORA: constants.FAILED_AMPHORA},
                                    requires=constants.AMPHORA))
        return delete_existing_vthunder_flow
    

    def get_failover_flow(self, role=constants.ROLE_STANDALONE,
                          load_balancer=None):

        # import rpdb; rpdb.set_trace()
        # standalone vthunder failover 
        failover_amphora_flow = linear_flow.Flow(
            a10constants.FAILOVER_AMPHORA_FLOW)
    

        # delete existing and bootup a new vthunder inplace of failed one
        # failover_amphora_flow.add(self.delete_existing_vthunder(vthunder))
        failover_amphora_flow.add(
            a10_database_tasks.MarkVThunderPendingDeleteInDB(
                rebind={a10constants.VTHUNDER: a10constants.FAILED_VTHUNDER},
                requires=a10constants.VTHUNDER))
        # failover_amphora_flow.add(
        #     database_tasks.MarkAmphoraHealthBusy(
        #         rebind={constants.AMPHORA: constants.FAILED_AMPHORA},
        #         requires=constants.AMPHORA))
        failover_amphora_flow.add(compute_tasks.ComputeDelete(
            rebind={a10constants.VTHUNDER: a10constants.FAILED_VTHUNDER},
            requires=a10constants.VTHUNDER))
        
        failover_amphora_flow.add(a10_database_tasks.MarkVThunderDeletedInDB(
            rebind={a10constants.VTHUNDER: a10constants.FAILED_VTHUNDER},
            requires=a10constants.VTHUNDER))
        # if not load_balancer:
        #     failover_amphora_flow.add(database_tasks.
        #                             DisableAmphoraHealthMonitoring(
        #                             rebind={constants.AMPHORA: constants.FAILED_AMPHORA},
        #                             requires=constants.AMPHORA))
        
        # failover_amphora_flow.add(
        #     a10_database_tasks.GetVThunderaDetails(
        #         rebind={constants.AMPHORA: constants.FAILED_AMPHORA},
        #         requires=constants.AMPHORA,
        #         provides=constants.AMP_DATA))

        # if role == constants.ROLE_MASTER:
        #     create_vthunder_flow = self.get_create_vthunder_flow()          
        #     failover_amphora_flow.add(create_vthunder_flow)
        #     get_amp_subflow = self.get_vthunder_for_lb_subflow(
        #         prefix=constants.FAILOVER_AMPHORA_FLOW)
        #     failover_amphora_flow.add(get_amp_subflow)
        # elif role == constants.ROLE_BACKUP:
        #     create_vthunder_flow = self.get_create_vthunder_flow()          
        #     failover_amphora_flow.add(create_vthunder_flow)

        #     get_amp_subflow = self.get_vthunder_for_lb_subflow(
        #         prefix=constants.FAILOVER_AMPHORA_FLOW)
        #     failover_amphora_flow.add(get_amp_subflow)


        return failover_amphora_flow

    def _get_failover_flow(self, role=constants.ROLE_STANDALONE,
                          load_balancer=None):
        """Creates a flow to failover a stale amphora
        :returns: The flow for amphora failover
        """

        failover_amphora_flow = linear_flow.Flow(
            constants.FAILOVER_AMPHORA_FLOW)

        failover_amphora_flow.add(lifecycle_tasks.AmphoraToErrorOnRevertTask(
            rebind={constants.AMPHORA: constants.FAILED_AMPHORA},
            requires=constants.AMPHORA))

        failover_amphora_flow.add(network_tasks.FailoverPreparationForAmphora(
            rebind={constants.AMPHORA: constants.FAILED_AMPHORA},
            requires=constants.AMPHORA))

        # Note: It seems intuitive to boot an amphora prior to deleting
        #       the old amphora, however this is a complicated issue.
        #       If the target host (due to anit-affinity) is resource
        #       constrained, this will fail where a post-delete will
        #       succeed. Since this is async with the API it would result
        #       in the LB ending in ERROR though the amps are still alive.
        #       Consider in the future making this a complicated
        #       try-on-failure-retry flow, or move upgrade failovers to be
        #       synchronous with the API. For now spares pool and act/stdby
        #       will mitigate most of this delay.

        # Delete the old amphora
        failover_amphora_flow.add(
            database_tasks.MarkAmphoraPendingDeleteInDB(
                rebind={constants.AMPHORA: constants.FAILED_AMPHORA},
                requires=constants.AMPHORA))
        # failover_amphora_flow.add(
        #     database_tasks.MarkAmphoraHealthBusy(
        #         rebind={constants.AMPHORA: constants.FAILED_AMPHORA},
        #         requires=constants.AMPHORA))
        failover_amphora_flow.add(compute_tasks.ComputeDelete(
            rebind={constants.AMPHORA: constants.FAILED_AMPHORA},
            requires=constants.AMPHORA))
        failover_amphora_flow.add(network_tasks.WaitForPortDetach(
            rebind={constants.AMPHORA: constants.FAILED_AMPHORA},
            requires=constants.AMPHORA))
        failover_amphora_flow.add(database_tasks.MarkAmphoraDeletedInDB(
            rebind={constants.AMPHORA: constants.FAILED_AMPHORA},
            requires=constants.AMPHORA))

        # If this is an unallocated amp (spares pool), we're done
        if not load_balancer:
            failover_amphora_flow.add(
                database_tasks.DisableAmphoraHealthMonitoring(
                    rebind={constants.AMPHORA: constants.FAILED_AMPHORA},
                    requires=constants.AMPHORA))
            return failover_amphora_flow

        # Save failed amphora details for later
        failover_amphora_flow.add(
            database_tasks.GetAmphoraDetails(
                rebind={constants.AMPHORA: constants.FAILED_AMPHORA},
                requires=constants.AMPHORA,
                provides=constants.AMP_DATA))
    

        # Get a new Vthunder 
        
        # Note: Role doesn't matter here.  We will update it later.
        get_amp_subflow = self.get_vthunder_for_lb_subflow(
            prefix=constants.FAILOVER_AMPHORA_FLOW)
        failover_amphora_flow.add(get_amp_subflow)

        # Update the new amphora with the failed amphora details
        failover_amphora_flow.add(database_tasks.UpdateAmpFailoverDetails(
            requires=(constants.AMPHORA, constants.AMP_DATA)))

        # Update the data stored in the flow from the database
        failover_amphora_flow.add(database_tasks.ReloadLoadBalancer(
            requires=constants.LOADBALANCER_ID,
            provides=constants.LOADBALANCER))

        failover_amphora_flow.add(database_tasks.ReloadAmphora(
            requires=constants.AMPHORA_ID,
            provides=constants.AMPHORA))

        # Prepare to reconnect the network interface(s)
        failover_amphora_flow.add(network_tasks.GetAmphoraeNetworkConfigs(
            requires=constants.LOADBALANCER,
            provides=constants.AMPHORAE_NETWORK_CONFIG))
        failover_amphora_flow.add(database_tasks.GetListenersFromLoadbalancer(
            requires=constants.LOADBALANCER, provides=constants.LISTENERS))
        failover_amphora_flow.add(database_tasks.GetAmphoraeFromLoadbalancer(
            requires=constants.LOADBALANCER, provides=constants.AMPHORAE))

        # Plug the VIP ports into the new amphora
        # The reason for moving these steps here is the udp listeners want to
        # do some kernel configuration before Listener update for forbidding
        # failure during rebuild amphora.
        # failover_amphora_flow.add(network_tasks.PlugVIPPort(
        #     requires=(constants.AMPHORA, constants.AMPHORAE_NETWORK_CONFIG)))
        # failover_amphora_flow.add(amphora_driver_tasks.AmphoraPostVIPPlug(
        #     requires=(constants.AMPHORA, constants.LOADBALANCER,
        #               constants.AMPHORAE_NETWORK_CONFIG)))

        # Listeners update needs to be run on all amphora to update
        # their peer configurations. So parallelize this with an
        # unordered subflow.
        update_amps_subflow = unordered_flow.Flow(
            constants.UPDATE_AMPS_SUBFLOW)

        timeout_dict = {
            constants.CONN_MAX_RETRIES:
                CONF.haproxy_amphora.active_connection_max_retries,
            constants.CONN_RETRY_INTERVAL:
                CONF.haproxy_amphora.active_connection_rety_interval}

        # Setup parallel flows for each amp. We don't know the new amp
        # details at flow creation time, so setup a subflow for each
        # amp on the LB, they let the task index into a list of amps
        # to find the amphora it should work on.
        # amp_index = 0
        # for amp in load_balancer.amphorae:
        #     if amp.status == constants.DELETED:
        #         continue
        #     update_amps_subflow.add(
        #         amphora_driver_tasks.AmpListenersUpdate(
        #             name=constants.AMP_LISTENER_UPDATE + '-' + str(amp_index),
        #             requires=(constants.LOADBALANCER, constants.AMPHORAE),
        #             inject={constants.AMPHORA_INDEX: amp_index,
        #                     constants.TIMEOUT_DICT: timeout_dict}))
        #     amp_index += 1

        failover_amphora_flow.add(update_amps_subflow)

        # import rpdb; rpdb.set_trace()
        # Plug the member networks into the new amphora
        failover_amphora_flow.add(network_tasks.CalculateAmphoraDelta(
            requires=(constants.LOADBALANCER, constants.AMPHORA),
            provides=constants.DELTA))

        failover_amphora_flow.add(network_tasks.HandleNetworkDelta(
            requires=(constants.AMPHORA, constants.DELTA),
            provides=constants.ADDED_PORTS))

        # failover_amphora_flow.add(amphora_driver_tasks.AmphoraePostNetworkPlug(
        #     requires=(constants.LOADBALANCER, constants.ADDED_PORTS)))

        failover_amphora_flow.add(database_tasks.ReloadLoadBalancer(
            name='octavia-failover-LB-reload-2',
            requires=constants.LOADBALANCER_ID,
            provides=constants.LOADBALANCER))

        # Handle the amphora role and VRRP if necessary
        if role == constants.ROLE_MASTER:
            failover_amphora_flow.add(database_tasks.MarkAmphoraMasterInDB(
                name=constants.MARK_AMP_MASTER_INDB,
                requires=constants.AMPHORA))
            vrrp_subflow = self.get_vrrp_subflow(role)
            failover_amphora_flow.add(vrrp_subflow)
        elif role == constants.ROLE_BACKUP:
            failover_amphora_flow.add(database_tasks.MarkAmphoraBackupInDB(
                name=constants.MARK_AMP_BACKUP_INDB,
                requires=constants.AMPHORA))
            vrrp_subflow = self.get_vrrp_subflow(role)
            failover_amphora_flow.add(vrrp_subflow)
        elif role == constants.ROLE_STANDALONE:
            failover_amphora_flow.add(
                database_tasks.MarkAmphoraStandAloneInDB(
                    name=constants.MARK_AMP_STANDALONE_INDB,
                    requires=constants.AMPHORA))

        failover_amphora_flow.add(amphora_driver_tasks.ListenersStart(
            requires=(constants.LOADBALANCER, constants.AMPHORA)))
        failover_amphora_flow.add(
            database_tasks.DisableAmphoraHealthMonitoring(
                rebind={constants.AMPHORA: constants.FAILED_AMPHORA},
                requires=constants.AMPHORA))

        return failover_amphora_flow