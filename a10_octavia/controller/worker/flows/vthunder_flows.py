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


import logging
from oslo_config import cfg
from taskflow.patterns import graph_flow
from taskflow.patterns import linear_flow

from octavia.common import constants
from octavia.controller.worker.tasks import database_tasks

from a10_octavia.common import a10constants
from a10_octavia.controller.worker.tasks import a10_compute_tasks as compute_tasks
from a10_octavia.controller.worker.tasks import a10_database_tasks
from a10_octavia.controller.worker.tasks import a10_network_tasks
from a10_octavia.controller.worker.tasks import vthunder_tasks

CONF = cfg.CONF

LOG = logging.getLogger(__name__)


class VThunderFlows(object):

    def __init__(self):
        # for some reason only this has the values from the config file
        # self.REST_AMPHORA_DRIVER = (CONF.controller_worker.amphora_driver ==
        #                            'amphora_haproxy_rest_driver')
        pass

    def get_create_vthunder_flow(self):
        """Creates a flow to create a spare amphora.

        :returns: The flow for creating the amphora
        """

        create_vthunder_flow = linear_flow.Flow(
            constants.CREATE_AMPHORA_FLOW)
        sf_name = 'spare_vthunder_create'
        create_vthunder_flow.add(database_tasks.CreateAmphoraInDB(
            name=sf_name + '-' + constants.CREATE_AMPHORA_INDB,
            provides=constants.AMPHORA_ID))

        create_vthunder_flow.add(compute_tasks.ComputeCreate(
            name=sf_name + '-' + constants.COMPUTE_CREATE,
            requires=(constants.AMPHORA_ID,
                      constants.BUILD_TYPE_PRIORITY,
                      ),
            provides=constants.COMPUTE_ID))
        create_vthunder_flow.add(database_tasks.UpdateAmphoraComputeId(
            name=sf_name + '-' + constants.UPDATE_AMPHORA_COMPUTEID,
            requires=(constants.AMPHORA_ID, constants.COMPUTE_ID)))

        create_vthunder_flow.add(database_tasks.MarkAmphoraBootingInDB(
            name=sf_name + '-' + constants.MARK_AMPHORA_BOOTING_INDB,
            requires=(constants.AMPHORA_ID, constants.COMPUTE_ID)))
        create_vthunder_flow.add(compute_tasks.ComputeActiveWait(
            name=sf_name + '-' + constants.COMPUTE_WAIT,
            requires=(constants.COMPUTE_ID, constants.AMPHORA_ID),
            provides=constants.COMPUTE_OBJ))
        create_vthunder_flow.add(database_tasks.UpdateAmphoraInfo(
            name=sf_name + '-' + constants.UPDATE_AMPHORA_INFO,
            requires=(constants.AMPHORA_ID, constants.COMPUTE_OBJ),
            provides=constants.AMPHORA))
        create_vthunder_flow.add(a10_database_tasks.CreateSpareVThunderEntry(
            name=sf_name + '-' + 'create_vThunder_entry_in_database',
            requires=(constants.AMPHORA),
            provides=a10constants.VTHUNDER))
        create_vthunder_flow.add(
            vthunder_tasks.VThunderComputeConnectivityWait(
                name=sf_name + '-' + constants.AMP_COMPUTE_CONNECTIVITY_WAIT,
                requires=(a10constants.VTHUNDER, constants.AMPHORA)))
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

    def _get_create_amp_for_lb_subflow(self, prefix, role):
        """Create a new amphora for lb."""

        sf_name = prefix + '-' + constants.CREATE_AMP_FOR_LB_SUBFLOW
        create_amp_for_lb_subflow = linear_flow.Flow(sf_name)
        create_amp_for_lb_subflow.add(database_tasks.CreateAmphoraInDB(
            name=sf_name + '-' + constants.CREATE_AMPHORA_INDB,
            provides=constants.AMPHORA_ID))
        # VIP subnet integration at bootup
        create_amp_for_lb_subflow.add(database_tasks.ReloadLoadBalancer(
            name=sf_name + '-' + constants.RELOADLOAD_BALANCER,
            requires=constants.LOADBALANCER_ID,
            provides=constants.LOADBALANCER))
        create_amp_for_lb_subflow.add(a10_network_tasks.AllocateVIP(
            name=sf_name + '-' + a10constants.ALLOCATE_VIP,
            requires=constants.LOADBALANCER,
            provides=constants.VIP))
        create_amp_for_lb_subflow.add(database_tasks.UpdateVIPAfterAllocation(
            name=sf_name + '-' + a10constants.UPDATE_VIP_AFTER_ALLOCATION,
            requires=(constants.LOADBALANCER_ID, constants.VIP),
            provides=constants.LOADBALANCER))

        require_server_group_id_condition = (
            role in (constants.ROLE_BACKUP, constants.ROLE_MASTER) and
            CONF.a10_nova.enable_anti_affinity)

        if require_server_group_id_condition:
            create_amp_for_lb_subflow.add(compute_tasks.ComputeCreate(
                name=sf_name + '-' + constants.COMPUTE_CREATE,
                requires=(
                    constants.AMPHORA_ID,
                    constants.BUILD_TYPE_PRIORITY,
                    constants.SERVER_GROUP_ID,
                    constants.LOADBALANCER
                ),
                provides=constants.COMPUTE_ID))
        else:
            create_amp_for_lb_subflow.add(compute_tasks.ComputeCreate(
                name=sf_name + '-' + constants.COMPUTE_CREATE,
                requires=(
                    constants.AMPHORA_ID,
                    constants.BUILD_TYPE_PRIORITY,
                    constants.LOADBALANCER
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
        create_amp_for_lb_subflow.add(a10_database_tasks.CreateVThunderEntry(
            name=sf_name + '-' + a10constants.CREATE_VTHUNDER_ENTRY,
            requires=(constants.AMPHORA, constants.LOADBALANCER),
            inject={a10constants.ROLE: role, a10constants.STATUS: constants.PENDING_CREATE}))
        # Get VThunder details from database
        create_amp_for_lb_subflow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            name=sf_name + '-' + a10constants.VTHUNDER_BY_LB,
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
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
        vthunder_for_amphora_subflow.add(a10_database_tasks.CreateVThunderEntry(
            name=sf_name + '-' + 'set load balancer status PENDING_CREATE',
            requires=(constants.AMPHORA, constants.LOADBALANCER),
            inject={"role": role, "status": constants.PENDING_CREATE}))
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
        # TODO(omkartelee01) Need HA variables here
        vrrp_subflow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            name=sf_name + '-' + a10constants.GET_LOADBALANCER_FROM_DB,
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        vrrp_subflow.add(a10_database_tasks.GetBackupVThunderByLoadBalancer(
            name=sf_name + '-' + a10constants.GET_BACKUP_LOADBALANCER_FROM_DB,
            requires=constants.LOADBALANCER,
            provides=a10constants.BACKUP_VTHUNDER))
        # VRRP Configuration
        vrrp_subflow.add(vthunder_tasks.ConfigureVRRPMaster(
            name=sf_name + '-' + a10constants.CONFIGURE_VRRP_FOR_MASTER_VTHUNDER,
            requires=(a10constants.VTHUNDER)))
        vrrp_subflow.add(vthunder_tasks.ConfigureVRRPBackup(
            name=sf_name + '-' + a10constants.CONFIGURE_VRRP_FOR_BACKUP_VTHUNDER,
            rebind={a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER}))
        vrrp_subflow.add(self._get_vrrp_status_subflow(sf_name))

        return vrrp_subflow

    def _get_vrrp_status_subflow(self, sf_name):
        check_vrrp_status = graph_flow.Flow(a10constants.CHECK_VRRP_STATUS)
        check_vrrp_status.add(vthunder_tasks.CheckVRRPStatus(
            name=a10constants.CHECK_VRRP_MASTER_STATUS,
            requires=(a10constants.VTHUNDER),
            provides=(a10constants.MASTER_VRRP_STATUS)))
        check_vrrp_status.add(vthunder_tasks.CheckVRRPStatus(
            name=a10constants.CHECK_VRRP_BACKUP_STATUS,
            rebind={a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER},
            provides=(a10constants.BACKUP_VRRP_STATUS)))
        confirm_vrrp = vthunder_tasks.ConfirmVRRPStatus(
            name=a10constants.CONFIRM_VRRP_STATUS,
            requires=(a10constants.MASTER_VRRP_STATUS, a10constants.BACKUP_VRRP_STATUS),
            provides=(a10constants.VRRP_STATUS))
        configure_vrrp = self._configure_vrrp_subflow(sf_name)
        check_vrrp_status.add(confirm_vrrp, configure_vrrp)
        check_vrrp_status.link(confirm_vrrp, configure_vrrp,
                               decider=self._is_vrrp_configured)
        return check_vrrp_status

    def _configure_vrrp_subflow(self, sf_name):
        configure_vrrp_subflow = linear_flow.Flow(sf_name)
        # VRID Configuration
        configure_vrrp_subflow.add(vthunder_tasks.ConfigureVRID(
            name=sf_name + '-' + a10constants.CONFIGURE_VRID_FOR_MASTER_VTHUNDER,
            requires=(a10constants.VTHUNDER)))
        configure_vrrp_subflow.add(vthunder_tasks.ConfigureVRID(
            name=sf_name + '-' + a10constants.CONFIGURE_VRID_FOR_BACKUP_VTHUNDER,
            rebind={a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER}))
        # VRRP synch
        configure_vrrp_subflow.add(vthunder_tasks.ConfigureVRRPSync(
            name=sf_name + '-' + a10constants.CONFIGURE_VRRP_SYNC,
            requires=(a10constants.VTHUNDER, a10constants.BACKUP_VTHUNDER)))
        # Wait for VRRP synch
        configure_vrrp_subflow.add(vthunder_tasks.VThunderComputeConnectivityWait(
            name=sf_name + '-' + a10constants.WAIT_FOR_MASTER_SYNC,
            requires=(a10constants.VTHUNDER, constants.AMPHORA)))
        configure_vrrp_subflow.add(vthunder_tasks.VThunderComputeConnectivityWait(
            name=sf_name + '-' + a10constants.WAIT_FOR_BACKUP_SYNC,
            rebind={a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER},
            requires=(constants.AMPHORA)))
        # Configure aVCS
        configure_vrrp_subflow.add(vthunder_tasks.ConfigureaVCSMaster(
            name=sf_name + '-' + a10constants.CONFIGURE_AVCS_SYNC_FOR_MASTER,
            requires=(a10constants.VTHUNDER)))
        configure_vrrp_subflow.add(vthunder_tasks.ConfigureaVCSBackup(
            name=sf_name + '-' + a10constants.CONFIGURE_AVCS_SYNC_FOR_BACKUP,
            rebind={a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER}))
        return configure_vrrp_subflow

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

    def _is_vrrp_configured(self, history):
        """Checks whether vrrp is configured
        :returns: True if vrrp is configured
        """
        return history[history.keys()[0]]
