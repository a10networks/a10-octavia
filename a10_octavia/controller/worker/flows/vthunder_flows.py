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
from octavia.controller.worker.v1.tasks import compute_tasks as compute
from octavia.controller.worker.v1.tasks import database_tasks

from a10_octavia.common import a10constants
from a10_octavia.controller.worker.tasks import a10_compute_tasks as compute_tasks
from a10_octavia.controller.worker.tasks import a10_database_tasks
from a10_octavia.controller.worker.tasks import a10_network_tasks
from a10_octavia.controller.worker.tasks import glm_tasks
from a10_octavia.controller.worker.tasks import vthunder_tasks

CONF = cfg.CONF

LOG = logging.getLogger(__name__)


class VThunderFlows(object):

    def __init__(self):
        pass

    def get_create_vthunder_flow(self):
        """Flow to create a spare amphora."""

        create_vthunder_flow = linear_flow.Flow(
            constants.CREATE_AMPHORA_FLOW)
        sf_name = a10constants.SPARE_VTHUNDER_CREATE
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
            requires=(constants.AMPHORA),
            provides=a10constants.VTHUNDER))
        create_vthunder_flow.add(
            vthunder_tasks.VThunderComputeConnectivityWait(
                name=sf_name + '-' + constants.AMP_COMPUTE_CONNECTIVITY_WAIT,
                requires=(a10constants.VTHUNDER, constants.AMPHORA)))
        create_vthunder_flow.add(vthunder_tasks.EnableInterfaceOnSpare(
            name=sf_name + '-' + a10constants.ENABLE_VTHUNDER_INTERFACE,
            requires=(a10constants.VTHUNDER)))
        create_vthunder_flow.add(
            vthunder_tasks.UpdateAcosVersionInVthunderEntry(
                name=sf_name + '-' + a10constants.UPDATE_ACOS_VERSION_IN_VTHUNDER_ENTRY,
                requires=(a10constants.VTHUNDER)))
        create_vthunder_flow.add(
            database_tasks.MarkAmphoraReadyInDB(
                name=sf_name + '-' + a10constants.MARK_AMPHORA_READY_INDB,
                requires=(constants.AMPHORA)))
        create_vthunder_flow.add(self.get_glm_license_subflow(
            prefix=a10constants.SPARE_VTHUNDER_CREATE, role=a10constants.SPARE_VTHUNDER))
        create_vthunder_flow.add(
            vthunder_tasks.CreateHealthMonitorOnVThunder(
                name=sf_name + '-' + a10constants.CREATE_HEALTH_MONITOR_ON_SPARE,
                requires=(a10constants.VTHUNDER)))

        create_vthunder_flow.add(a10_database_tasks.MarkVThunderStatusInDB(
            requires=(a10constants.VTHUNDER),
            inject={"status": a10constants.READY}))
        return create_vthunder_flow

    def get_vthunder_for_lb_subflow(
            self, prefix, role=constants.ROLE_STANDALONE):
        """Flow to get vThunder for lb"""

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
            inject={a10constants.ROLE: role},
            provides=constants.AMPHORA_ID)

        create_amp = self._get_create_amp_for_lb_subflow(prefix, role)

        map_lb_to_vthunder = self._get_vthunder_for_amphora_subflow(
            prefix, role)

        # Add them to the graph flow
        amp_for_lb_flow.add(allocate_and_associate_amp,
                            map_lb_to_vthunder, create_amp)

        # Setup the decider for the path if we can map vThunder
        amp_for_lb_flow.link(allocate_and_associate_amp, map_lb_to_vthunder,
                             decider=self._allocate_amp_to_lb_decider,
                             decider_depth='flow')
        # Setup the decider to create a vThunder
        amp_for_lb_flow.link(allocate_and_associate_amp, create_amp,
                             decider=self._create_new_amp_for_lb_decider,
                             decider_depth='flow')

        return amp_for_lb_flow

    def _get_create_amp_for_lb_subflow(self, prefix, role):
        """Flow to create a new vThunder for lb."""

        sf_name = prefix + '-' + constants.CREATE_AMP_FOR_LB_SUBFLOW
        create_amp_for_lb_subflow = linear_flow.Flow(sf_name)
        create_amp_for_lb_subflow.add(database_tasks.CreateAmphoraInDB(
            name=sf_name + '-' + constants.CREATE_AMPHORA_INDB,
            provides=constants.AMPHORA_ID))
        # VIP subnet integration at bootup
        create_amp_for_lb_subflow.add(database_tasks.ReloadLoadBalancer(
            name=sf_name + '-' + a10constants.RELOADLOAD_BALANCER,
            requires=constants.LOADBALANCER_ID,
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
        # Create vThunder entry in custom DB
        create_amp_for_lb_subflow.add(a10_database_tasks.CreateVThunderEntry(
            name=sf_name + '-' + a10constants.CREATE_VTHUNDER_ENTRY,
            requires=(constants.AMPHORA, constants.LOADBALANCER),
            inject={a10constants.ROLE: role, a10constants.STATUS: constants.PENDING_CREATE}))
        # Rebind requires vthunder in store and vMaster requires vThunder
        create_amp_for_lb_subflow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            name=sf_name + '-' + a10constants.VTHUNDER_BY_LB,
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        # Get VThunder details from database
        if role == constants.ROLE_BACKUP:
            create_amp_for_lb_subflow.add(
                a10_database_tasks.GetBackupVThunderByLoadBalancer(
                    requires=constants.LOADBALANCER,
                    provides=a10constants.BACKUP_VTHUNDER))
            create_amp_for_lb_subflow.add(
                vthunder_tasks.VThunderComputeConnectivityWait(
                    name=sf_name + '-' + a10constants.BACKUP_CONNECTIVITY_WAIT,
                    rebind={a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER},
                    requires=constants.AMPHORA))
        else:
            create_amp_for_lb_subflow.add(
                vthunder_tasks.VThunderComputeConnectivityWait(
                    name=sf_name + '-' + a10constants.WAIT_FOR_VTHUNDER_CONNECTIVITY,
                    requires=(a10constants.VTHUNDER, constants.AMPHORA)))
        # License the vThunder-Amphora
        create_amp_for_lb_subflow.add(
            *self.get_glm_license_subflow(prefix + '-' + role, role))
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

        if role == constants.ROLE_BACKUP:
            create_amp_for_lb_subflow.add(
                a10_database_tasks.GetBackupVThunderByLoadBalancer(
                    name=sf_name + '-' + a10constants.BACKUP_VTHUNDER,
                    requires=constants.LOADBALANCER,
                    provides=a10constants.BACKUP_VTHUNDER))
            create_amp_for_lb_subflow.add(
                vthunder_tasks.UpdateAcosVersionInVthunderEntry(
                    name=sf_name + '-' + a10constants.UPDATE_ACOS_VERSION_FOR_BACKUP_VTHUNDER,
                    rebind={a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER}))
        else:
            create_amp_for_lb_subflow.add(
                vthunder_tasks.UpdateAcosVersionInVthunderEntry(
                    name=sf_name + '-' + a10constants.UPDATE_ACOS_VERSION_FOR_BACKUP_VTHUNDER,
                    requires=(a10constants.VTHUNDER)))

        return create_amp_for_lb_subflow

    def _allocate_amp_to_lb_decider(self, history):
        """Decider to allocate lb to vThunder"""

        return list(history.values())[0] is not None

    def _create_new_amp_for_lb_decider(self, history):
        """Decider to create vThunder for lb"""

        return list(history.values())[0] is None

    def _get_vthunder_for_amphora_subflow(self, prefix, role):
        """Subflow to create lb in existing vThunder."""

        sf_name = prefix + '-' + a10constants.LB_TO_VTHUNDER_SUBFLOW
        vthunder_for_amphora_subflow = linear_flow.Flow(sf_name)
        vthunder_for_amphora_subflow.add(database_tasks.CreateAmphoraInDB(
            name=sf_name + '-' + constants.CREATE_AMPHORA_INDB,
            provides=constants.AMPHORA_ID))
        vthunder_for_amphora_subflow.add(a10_database_tasks.ValidateComputeForProject(
            name=sf_name + '-' + a10constants.VALIDATE_COMPUTE_FOR_PROJECT,
            requires=constants.LOADBALANCER,
            inject={"role": role},
            provides=constants.COMPUTE_ID))

        # if no compute, use spare vThunder and prepare network for spare vThunder
        vthunder_for_amphora_subflow.add(a10_database_tasks.GetSpareComputeForProject(
            name=sf_name + '-' + a10constants.GET_SPARE_COMPUTE_FOR_PROJECT,
            requires=constants.COMPUTE_ID,
            provides=(constants.COMPUTE_ID, a10constants.SPARE_VTHUNDER)))
        vthunder_for_amphora_subflow.add(a10_network_tasks.PlugVipNetworkOnSpare(
            name=sf_name + '-' + a10constants.PLUG_VIP_NETWORK_ON_SPARE,
            requires=(a10constants.SPARE_VTHUNDER, constants.LOADBALANCER),
            provides=a10constants.ADDED_NETWORK))
        vthunder_for_amphora_subflow.add(vthunder_tasks.SparePostNetworkPlug(
            name=sf_name + '-' + a10constants.POST_SPARE_PLUG_NETWORK,
            rebind={a10constants.VTHUNDER: a10constants.SPARE_VTHUNDER},
            requires=(a10constants.ADDED_NETWORK)))
        vthunder_for_amphora_subflow.add(a10_database_tasks.GetVThunderAmphora(
            name=sf_name + '-' + a10constants.GET_VTHUNDER_AMPHORA,
            rebind={a10constants.VTHUNDER: a10constants.SPARE_VTHUNDER},
            provides=constants.AMPHORA))
        vthunder_for_amphora_subflow.add(vthunder_tasks.VThunderComputeConnectivityWait(
            name=sf_name + '-' + constants.AMP_COMPUTE_CONNECTIVITY_WAIT,
            rebind={a10constants.VTHUNDER: a10constants.SPARE_VTHUNDER},
            requires=(constants.AMPHORA)))
        vthunder_for_amphora_subflow.add(vthunder_tasks.EnableInterfaceOnSpare(
            name=sf_name + '-' + a10constants.ENABLE_VTHUNDER_INTERFACE,
            rebind={a10constants.VTHUNDER: a10constants.SPARE_VTHUNDER},
            requires=(a10constants.ADDED_NETWORK)))

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
            name=sf_name + '-' + a10constants.CREATE_VTHUNDER_ENTRY,
            requires=(constants.AMPHORA, constants.LOADBALANCER),
            inject={"role": role, "status": constants.PENDING_CREATE}))
        # Get VThunder details from database
        vthunder_for_amphora_subflow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            name=sf_name + '-' + a10constants.VTHUNDER_BY_LB,
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        vthunder_for_amphora_subflow.add(database_tasks.ReloadLoadBalancer(
            name=sf_name + '-' + a10constants.RELOADLOAD_BALANCER,
            requires=constants.LOADBALANCER_ID,
            provides=constants.LOADBALANCER))
        vthunder_for_amphora_subflow.add(a10_network_tasks.GetLBResourceSubnet(
            name=sf_name + '-' + a10constants.GET_LB_RESOURCE,
            rebind={a10constants.LB_RESOURCE: constants.LOADBALANCER},
            provides=constants.SUBNET))
        vthunder_for_amphora_subflow.add(
            a10_database_tasks.GetChildProjectsOfParentPartition(
                name=sf_name + '-' + a10constants.GET_PROJECT_COUNT,
                requires=[a10constants.VTHUNDER],
                rebind={a10constants.LB_RESOURCE: constants.LOADBALANCER},
                provides=a10constants.PARTITION_PROJECT_LIST
            ))
        vthunder_for_amphora_subflow.add(
            a10_database_tasks.CountLoadbalancersInProjectBySubnet(
                name=sf_name + '-' + a10constants.GET_LB_COUNT_SUBNET,
                requires=[constants.SUBNET, a10constants.PARTITION_PROJECT_LIST],
                provides=a10constants.LB_COUNT_SUBNET))
        vthunder_for_amphora_subflow.add(a10_network_tasks.AllocateVIP(
            name=sf_name + '-' + a10constants.ALLOCATE_VIP,
            requires=[constants.LOADBALANCER, a10constants.LB_COUNT_SUBNET],
            provides=constants.VIP))
        vthunder_for_amphora_subflow.add(database_tasks.UpdateVIPAfterAllocation(
            name=sf_name + '-' + a10constants.UPDATE_VIP_AFTER_ALLOCATION,
            requires=(constants.LOADBALANCER_ID, constants.VIP),
            provides=constants.LOADBALANCER))
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
            vthunder_for_amphora_subflow.add(
                vthunder_tasks.UpdateAcosVersionInVthunderEntry(
                    name=sf_name + '-' + a10constants.UPDATE_ACOS_VERSION_FOR_BACKUP_VTHUNDER,
                    requires=(a10constants.VTHUNDER)))
        elif role == constants.ROLE_BACKUP:
            vthunder_for_amphora_subflow.add(database_tasks.MarkAmphoraBackupInDB(
                name=sf_name + '-' + constants.MARK_AMP_BACKUP_INDB,
                requires=constants.AMPHORA))
            vthunder_for_amphora_subflow.add(
                a10_database_tasks.GetBackupVThunderByLoadBalancer(
                    name=sf_name + '-' + a10constants.BACKUP_VTHUNDER,
                    requires=constants.LOADBALANCER,
                    provides=a10constants.BACKUP_VTHUNDER))
            vthunder_for_amphora_subflow.add(
                vthunder_tasks.UpdateAcosVersionInVthunderEntry(
                    name=sf_name + '-' + a10constants.UPDATE_ACOS_VERSION_FOR_BACKUP_VTHUNDER,
                    rebind={a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER}))
        elif role == constants.ROLE_STANDALONE:
            vthunder_for_amphora_subflow.add(
                database_tasks.MarkAmphoraStandAloneInDB(
                    name=sf_name + '-' + constants.MARK_AMP_STANDALONE_INDB,
                    requires=constants.AMPHORA))
            vthunder_for_amphora_subflow.add(
                vthunder_tasks.UpdateAcosVersionInVthunderEntry(
                    name=sf_name + '-' + a10constants.UPDATE_ACOS_VERSION_FOR_BACKUP_VTHUNDER,
                    requires=(a10constants.VTHUNDER)))

        # If spare vThunder is used, remove spare vThunder the database
        vthunder_for_amphora_subflow.add(a10_database_tasks.DeleteStaleSpareVThunder(
            name=sf_name + '-' + a10constants.DELETE_STALE_SPARE_VTHUNDER,
            requires=(a10constants.SPARE_VTHUNDER)))
        return vthunder_for_amphora_subflow

    def get_glm_license_subflow(self, prefix, role):
        sf_name = prefix + '-' + a10constants.ACTIVATE_GLM_LICENSE_SUBFLOW
        glm_license_subflow = linear_flow.Flow(sf_name)

        if role == constants.ROLE_BACKUP:
            glm_license_subflow.add(vthunder_tasks.SetVThunderHostname(
                name=sf_name + '-' + a10constants.SET_VTHUNDER_HOSTNAME,
                requires=constants.AMPHORA,
                rebind={a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER}
            ))
            glm_license_subflow.add(glm_tasks.ConfigureForwardProxyServer(
                name=sf_name + '-' + a10constants.CONFIGURE_PROXY_SERVER,
                requires=constants.FLAVOR,
                rebind={a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER}
            ))
            glm_license_subflow.add(glm_tasks.DNSConfiguration(
                name=sf_name + '-' + a10constants.CONFIGURE_DNS_NAMESERVERS,
                requires=constants.FLAVOR,
                rebind={a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER},
            ))
            glm_license_subflow.add(glm_tasks.ActivateFlexpoolLicense(
                name=sf_name + '-' + a10constants.ACTIVATE_FLEXPOOL_LICENSE,
                requires=(constants.AMPHORA, constants.FLAVOR),
                rebind={a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER},
            ))
        else:
            glm_license_subflow.add(vthunder_tasks.SetVThunderHostname(
                name=sf_name + '-' + a10constants.SET_VTHUNDER_HOSTNAME,
                requires=(constants.AMPHORA, a10constants.VTHUNDER)
            ))
            glm_license_subflow.add(glm_tasks.ConfigureForwardProxyServer(
                name=sf_name + '-' + a10constants.CONFIGURE_PROXY_SERVER,
                requires=(constants.FLAVOR, a10constants.VTHUNDER)
            ))
            glm_license_subflow.add(glm_tasks.DNSConfiguration(
                name=sf_name + '-' + a10constants.CONFIGURE_DNS_NAMESERVERS,
                requires=(constants.FLAVOR, a10constants.VTHUNDER)
            ))
            glm_license_subflow.add(glm_tasks.ActivateFlexpoolLicense(
                name=sf_name + '-' + a10constants.ACTIVATE_FLEXPOOL_LICENSE,
                requires=(constants.AMPHORA, a10constants.VTHUNDER, constants.FLAVOR),
            ))
        return glm_license_subflow

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
            requires=(constants.LOADBALANCER, a10constants.VTHUNDER),
            provides=a10constants.BACKUP_VTHUNDER))
        # Make sure devices are ready
        vrrp_subflow.add(vthunder_tasks.VThunderComputeConnectivityWait(
            name=sf_name + '-' + a10constants.WAIT_FOR_MASTER_SYNC + '-for-thunder',
            requires=(a10constants.VTHUNDER, constants.AMPHORA)))
        vrrp_subflow.add(vthunder_tasks.VThunderComputeConnectivityWait(
            name=sf_name + '-' + a10constants.WAIT_FOR_BACKUP_SYNC + '-for-thunder',
            rebind={a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER},
            requires=(constants.AMPHORA)))
        # VRRP Configuration
        vrrp_subflow.add(a10_database_tasks.AddProjectSetIdDB(
            name=sf_name + '-' + a10constants.ADD_VRRP_SET_ID_INDB,
            requires=constants.LOADBALANCER,
            provides=a10constants.SET_ID))
        vrrp_subflow.add(vthunder_tasks.ConfigureVRRPMaster(
            name=sf_name + '-' + a10constants.CONFIGURE_VRRP_FOR_MASTER_VTHUNDER,
            requires=(a10constants.VTHUNDER, a10constants.SET_ID)))
        vrrp_subflow.add(vthunder_tasks.ConfigureVRRPBackup(
            name=sf_name + '-' + a10constants.CONFIGURE_VRRP_FOR_BACKUP_VTHUNDER,
            requires=(a10constants.VTHUNDER, a10constants.SET_ID),
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
        # Configure aVCS
        configure_vrrp_subflow.add(vthunder_tasks.ConfigureaVCSMaster(
            name=sf_name + '-' + a10constants.CONFIGURE_AVCS_SYNC_FOR_MASTER,
            requires=(a10constants.VTHUNDER)))
        configure_vrrp_subflow.add(vthunder_tasks.ConfigureaVCSBackup(
            name=sf_name + '-' + a10constants.CONFIGURE_AVCS_SYNC_FOR_BACKUP,
            rebind={a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER}))
        # Wait for aVCS sync
        configure_vrrp_subflow.add(vthunder_tasks.VCSSyncWait(
            name=sf_name + '-' + a10constants.VCS_SYNC_WAIT,
            requires=a10constants.VTHUNDER))
        return configure_vrrp_subflow

    def get_rack_vthunder_for_lb_subflow(
            self, vthunder_conf, prefix, role=constants.ROLE_STANDALONE):
        """ reload the loadbalancer and make entry in database"""

        sf_name = prefix + '-' + constants.GET_AMPHORA_FOR_LB_SUBFLOW

        amp_for_lb_flow = linear_flow.Flow(sf_name)
        amp_for_lb_flow.add(a10_database_tasks.CreateRackVthunderEntry(
            name=sf_name + '-' + 'create_rack_vThunder_entry_in_database',
            requires=(constants.LOADBALANCER, a10constants.VTHUNDER_CONFIG)))
        amp_for_lb_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        amp_for_lb_flow.add(vthunder_tasks.UpdateAcosVersionInVthunderEntry(
            name=sf_name + '-' + a10constants.UPDATE_ACOS_VERSION_IN_VTHUNDER_ENTRY,
            requires=(a10constants.VTHUNDER)))
        return amp_for_lb_flow

    def _is_vrrp_configured(self, history):
        """Checks whether vrrp is configured
        :returns: True if vrrp is configured
        """
        return history[list(history.keys())[0]]

    def get_write_memory_flow(self, vthunder, store, deleteCompute):
        """Perform write memory for thunder """
        sf_name = 'a10-house-keeper' + '-' + a10constants.WRITE_MEMORY_THUNDER_FLOW

        write_memory_flow = linear_flow.Flow(sf_name)
        vthunder_store = {}
        vthunder_store[vthunder.vthunder_id] = vthunder
        write_memory_flow.add(a10_database_tasks.GetActiveLoadBalancersByThunder(
            requires=a10constants.VTHUNDER,
            rebind={a10constants.VTHUNDER: vthunder.vthunder_id},
            name='{flow}-{id}'.format(
                id=vthunder.vthunder_id,
                flow='GetActiveLoadBalancersByThunder'),
            provides=a10constants.LOADBALANCERS_LIST))
        write_memory_flow.add(a10_database_tasks.MarkLoadBalancersPendingUpdateInDB(
            name='{flow}-{id}'.format(
                id=vthunder.vthunder_id,
                flow='MarkLoadBalancersPendingUpdateInDB'),
            requires=a10constants.LOADBALANCERS_LIST))
        if not deleteCompute:
            write_memory_flow.add(vthunder_tasks.WriteMemoryHouseKeeper(
                requires=(a10constants.VTHUNDER, a10constants.LOADBALANCERS_LIST,
                          a10constants.WRITE_MEM_SHARED_PART),
                rebind={a10constants.VTHUNDER: vthunder.vthunder_id},
                name='{flow}-{partition}-{id}'.format(
                    id=vthunder.vthunder_id,
                    flow='WriteMemory-' + a10constants.WRITE_MEMORY_THUNDER_FLOW,
                    partition=a10constants.WRITE_MEM_FOR_SHARED_PARTITION),
                provides=a10constants.WRITE_MEM_SHARED))
            write_memory_flow.add(vthunder_tasks.WriteMemoryHouseKeeper(
                requires=(a10constants.VTHUNDER, a10constants.LOADBALANCERS_LIST),
                rebind={a10constants.VTHUNDER: vthunder.vthunder_id},
                name='{flow}-{partition}-{id}'.format(
                    id=vthunder.vthunder_id,
                    flow='WriteMemory-' + a10constants.WRITE_MEMORY_THUNDER_FLOW,
                    partition=a10constants.WRITE_MEM_FOR_LOCAL_PARTITION),
                provides=a10constants.WRITE_MEM_PRIVATE))
            write_memory_flow.add(a10_database_tasks.SetThunderLastWriteMem(
                requires=(a10constants.VTHUNDER,
                          a10constants.WRITE_MEM_SHARED,
                          a10constants.WRITE_MEM_PRIVATE),
                rebind={a10constants.VTHUNDER: vthunder.vthunder_id},
                name='{flow}-{id}'.format(
                    id=vthunder.vthunder_id,
                    flow='SetThunderLastWriteMem')))
        else:
            write_memory_flow.add(a10_database_tasks.SetThunderLastWriteMem(
                requires=(a10constants.VTHUNDER),
                inject={a10constants.WRITE_MEM_SHARED: True, a10constants.WRITE_MEM_PRIVATE: True},
                rebind={a10constants.VTHUNDER: vthunder.vthunder_id},
                name='{flow}-{id}'.format(
                    id=vthunder.vthunder_id,
                    flow='SetThunderLastWriteMem')))
        write_memory_flow.add(a10_database_tasks.MarkLoadBalancersActiveInDB(
            name='{flow}-{id}'.format(
                id=vthunder.vthunder_id,
                flow='MarkLoadBalancersActiveInDB'),
            requires=a10constants.LOADBALANCERS_LIST))

        store.update(vthunder_store)
        return write_memory_flow

    def get_reload_check_flow(self, vthunder, store):
        """Perform write memory for thunder """
        sf_name = 'a10-house-keeper' + '-' + a10constants.RELOAD_CHECK_THUNDER_FLOW

        reload_check_flow = linear_flow.Flow(sf_name)
        vthunder_store = {}
        vthunder_store[vthunder.vthunder_id] = vthunder
        reload_check_flow.add(a10_database_tasks.GetActiveLoadBalancersByThunder(
            requires=a10constants.VTHUNDER,
            rebind={a10constants.VTHUNDER: vthunder.vthunder_id},
            name='{flow}-{id}'.format(
                id=vthunder.vthunder_id,
                flow='GetActiveLoadBalancersByThunder'),
            provides=a10constants.LOADBALANCERS_LIST))
        reload_check_flow.add(vthunder_tasks.WriteMemoryThunderStatusCheck(
            name='{flow}-{id}'.format(
                id=vthunder.vthunder_id,
                flow='WriteMemoryThunderStatusCheck'),
            requires=(a10constants.VTHUNDER, a10constants.LOADBALANCERS_LIST),
            rebind={a10constants.VTHUNDER: vthunder.vthunder_id}))

        store.update(vthunder_store)
        return reload_check_flow

    def get_failover_spare_vthunder_flow(self):
        """Perform failover for spare vthunder"""
        sf_name = 'a10-house-keeper-failover-spare-vthunder'
        failover_flow = linear_flow.Flow(sf_name)

        failover_flow.add(a10_database_tasks.GetVThunderAmphora(
            name=sf_name + '-' + a10constants.GET_VTHUNDER_AMPHORA,
            requires=a10constants.VTHUNDER,
            provides=constants.AMPHORA))
        failover_flow.add(compute.ComputeDelete(
            name=sf_name + '-' + a10constants.COMPUTE_DELETE,
            requires=constants.AMPHORA))
        failover_flow.add(a10_database_tasks.DeleteStaleSpareVThunder(
            name=sf_name + '-' + a10constants.DELETE_STALE_SPARE_VTHUNDER,
            rebind={a10constants.SPARE_VTHUNDER: a10constants.VTHUNDER}))

        return failover_flow

    def _get_failover_use_spare_amphora_subflow(self, prefix):
        """Flow to get spare amphora for failvoer"""
        sf_name = 'failover_get_spare_amphora'
        get_spare_flow = linear_flow.Flow(sf_name)
        get_spare_flow.add(a10_network_tasks.PlugNetworksByID(
            name=sf_name + '-' + a10constants.PLUG_NETWORK_BY_IDS,
            requires=(a10constants.NETWORK_LIST),
            rebind={a10constants.VTHUNDER: a10constants.SPARE_VTHUNDER},
            provides=a10constants.ADDED_NETWORK))
        get_spare_flow.add(vthunder_tasks.SparePostNetworkPlug(
            name=sf_name + '-' + a10constants.POST_SPARE_PLUG_NETWORK,
            rebind={a10constants.VTHUNDER: a10constants.SPARE_VTHUNDER},
            requires=(a10constants.ADDED_NETWORK)))
        get_spare_flow.add(a10_database_tasks.GetVThunderAmphora(
            name=sf_name + '-' + a10constants.GET_VTHUNDER_AMPHORA,
            rebind={a10constants.VTHUNDER: a10constants.SPARE_VTHUNDER},
            provides=constants.AMPHORA))
        get_spare_flow.add(vthunder_tasks.VThunderComputeConnectivityWait(
            name=sf_name + '-' + constants.AMP_COMPUTE_CONNECTIVITY_WAIT,
            rebind={a10constants.VTHUNDER: a10constants.SPARE_VTHUNDER},
            requires=(constants.AMPHORA)))
        get_spare_flow.add(vthunder_tasks.EnableInterfaceOnSpare(
            name=sf_name + '-' + a10constants.ENABLE_VTHUNDER_INTERFACE,
            rebind={a10constants.VTHUNDER: a10constants.SPARE_VTHUNDER},
            requires=(a10constants.ADDED_NETWORK)))

        return get_spare_flow

    def _get_failover_create_amphora_subflow(self, prefix):
        """Flow to create amphora for failover"""
        create_amp_flow = linear_flow.Flow(constants.CREATE_AMPHORA_FLOW)
        sf_name = prefix + '-' + a10constants.SPARE_VTHUNDER_CREATE

        create_amp_flow.add(database_tasks.CreateAmphoraInDB(
            name=sf_name + '-' + constants.CREATE_AMPHORA_INDB,
            provides=constants.AMPHORA_ID))
        create_amp_flow.add(compute_tasks.ComputeCreate(
            name=sf_name + '-' + constants.COMPUTE_CREATE,
            requires=(constants.AMPHORA_ID, a10constants.NETWORK_LIST),
            provides=constants.COMPUTE_ID))
        create_amp_flow.add(database_tasks.UpdateAmphoraComputeId(
            name=sf_name + '-' + constants.UPDATE_AMPHORA_COMPUTEID,
            requires=(constants.AMPHORA_ID, constants.COMPUTE_ID)))

        create_amp_flow.add(database_tasks.MarkAmphoraBootingInDB(
            name=sf_name + '-' + constants.MARK_AMPHORA_BOOTING_INDB,
            requires=(constants.AMPHORA_ID, constants.COMPUTE_ID)))
        create_amp_flow.add(compute_tasks.ComputeActiveWait(
            name=sf_name + '-' + constants.COMPUTE_WAIT,
            requires=(constants.COMPUTE_ID, constants.AMPHORA_ID),
            provides=constants.COMPUTE_OBJ))
        create_amp_flow.add(database_tasks.UpdateAmphoraInfo(
            name=sf_name + '-' + constants.UPDATE_AMPHORA_INFO,
            requires=(constants.AMPHORA_ID, constants.COMPUTE_OBJ),
            provides=constants.AMPHORA))
        create_amp_flow.add(a10_database_tasks.CreateSpareVThunderEntry(
            requires=(constants.AMPHORA),
            provides=a10constants.SPARE_VTHUNDER))
        create_amp_flow.add(
            vthunder_tasks.VThunderComputeConnectivityWait(
                name=sf_name + '-' + constants.AMP_COMPUTE_CONNECTIVITY_WAIT,
                requires=constants.AMPHORA,
                rebind={a10constants.VTHUNDER: a10constants.SPARE_VTHUNDER}))
        create_amp_flow.add(a10_database_tasks.MarkVThunderStatusInDB(
            rebind={a10constants.VTHUNDER: a10constants.SPARE_VTHUNDER},
            inject={"status": a10constants.READY}))
        create_amp_flow.add(
            vthunder_tasks.UpdateAcosVersionInVthunderEntry(
                name=sf_name + '-' + a10constants.UPDATE_ACOS_VERSION_IN_VTHUNDER_ENTRY,
                rebind={a10constants.VTHUNDER: a10constants.SPARE_VTHUNDER}))
        create_amp_flow.add(vthunder_tasks.EnableInterfaceOnSpare(
            name=sf_name + '-' + a10constants.ENABLE_VTHUNDER_INTERFACE,
            rebind={a10constants.VTHUNDER: a10constants.SPARE_VTHUNDER}))
        return create_amp_flow

    def _get_failover_amphora_subflow(self, prefix):
        """Flow to get vThunder for failover process"""
        sf_name = prefix + '-' + a10constants.GET_AMPHORA_FOR_FAILOVER
        failover_get_amp_flow = graph_flow.Flow(sf_name)

        check_spare = a10_database_tasks.TryGetSpareCompute(
            name=sf_name + '-' + 'check-spare-exist',
            provides=(a10constants.SPARE_VTHUNDER))
        get_spare_amp = self._get_failover_use_spare_amphora_subflow(sf_name)
        create_amp = self._get_failover_create_amphora_subflow(sf_name)
        failover_get_amp_flow.add(check_spare, get_spare_amp, create_amp)
        failover_get_amp_flow.link(check_spare, get_spare_amp,
                                   decider=self._allocate_amp_to_lb_decider,
                                   decider_depth='flow')
        failover_get_amp_flow.link(check_spare, create_amp,
                                   decider=self._create_new_amp_for_lb_decider,
                                   decider_depth='flow')
        return failover_get_amp_flow

    def _get_failover_configure_vcs_subflow(self, prefix):
        """Flow to get failover vcs configure process"""
        sf_name = prefix + '-' + 'conf-vcs'
        failover_vcs_flow = linear_flow.Flow(sf_name)

        failover_vcs_flow.add(a10_database_tasks.GetProjectVRRPSetId(
            name=sf_name + '-' + a10constants.GET_VRRP_SET_ID_INDB,
            requires=a10constants.VTHUNDER,
            provides=a10constants.SET_ID))
        failover_vcs_flow.add(a10_database_tasks.GetVThunderDeviceID(
            name=sf_name + '-' + a10constants.GET_VCS_DEVICE_ID,
            requires=a10constants.VTHUNDER,
            provides=a10constants.DEVICE_ID))
        failover_vcs_flow.add(vthunder_tasks.ConfigureVRRPFailover(
            rebind={a10constants.VTHUNDER: a10constants.SPARE_VTHUNDER},
            requires=(a10constants.DEVICE_ID, a10constants.SET_ID)))
        failover_vcs_flow.add(vthunder_tasks.ConfigureaVCSFailover(
            name=sf_name + '-' + a10constants.CONFIGURE_AVCS_FOR_FAILOVER,
            rebind={a10constants.VTHUNDER: a10constants.SPARE_VTHUNDER},
            requires=a10constants.DEVICE_ID))
        # Wait for aVCS sync
        failover_vcs_flow.add(vthunder_tasks.VCSSyncWait(
            name=sf_name + '-' + a10constants.VCS_SYNC_WAIT,
            rebind={a10constants.VTHUNDER: a10constants.SPARE_VTHUNDER}))

        return failover_vcs_flow

    def get_failover_vcs_vthunder_flow(self):
        """Perform failover for VCS vthunder device"""
        sf_name = 'a10-house-keeper-failover-vcs-vthunder'
        failover_flow = linear_flow.Flow(sf_name)

        failover_flow.add(a10_database_tasks.GetComputeVThundersAndLoadBalancers(
            name=sf_name + '-' + a10constants.GET_LBS_BY_THUNDER,
            requires=a10constants.VTHUNDER,
            provides=(a10constants.VTHUNDER_LIST, a10constants.LOADBALANCERS_LIST)))
        # Switch role may not necessary
        failover_flow.add(a10_database_tasks.SetVThunderToStandby(
            name=sf_name + '-' + a10constants.SET_VTHUNDER_TO_STANDBY,
            requires=a10constants.VTHUNDER_LIST))
        failover_flow.add(a10_database_tasks.LoadBalancerListToErrorOnRevertTask(
            name=sf_name + '-' + a10constants.MARK_LB_LIST_ERROR_ON_REVERT,
            requires=a10constants.LOADBALANCERS_LIST))
        failover_flow.add(a10_database_tasks.MarkLoadBalancersPendingUpdateInDB(
            name=sf_name + '-' + a10constants.MARK_LB_PENIND_UPDATE_IN_DB,
            requires=a10constants.LOADBALANCERS_LIST))
        failover_flow.add(a10_network_tasks.GetVThunderNetworkList(
            name=sf_name + '-' + a10constants.GET_VTHUNDER_NETWORK_LIST,
            requires=a10constants.VTHUNDER,
            provides=a10constants.NETWORK_LIST))
        failover_flow.add(self._get_failover_amphora_subflow(sf_name))
        failover_flow.add(self._get_failover_configure_vcs_subflow(sf_name))

        failover_flow.add(compute_tasks.DeleteStaleCompute(
            name=sf_name + '-' + 'delete-stale-compute',
            requires=(a10constants.VTHUNDER)))
        failover_flow.add(a10_database_tasks.FailoverPostDbUpdate(
            name=sf_name + '-' + a10constants.POST_FAILOVER_DB_UPDATE,
            requires=(a10constants.VTHUNDER, a10constants.SPARE_VTHUNDER)))
        failover_flow.add(a10_database_tasks.DeleteStaleSpareVThunder(
            name=sf_name + '-' + a10constants.DELETE_STALE_SPARE_VTHUNDER,
            requires=(a10constants.SPARE_VTHUNDER)))
        failover_flow.add(a10_database_tasks.MarkLoadBalancersActiveInDB(
            name=sf_name + '-' + a10constants.MARK_LB_ACTIVE_IN_DB,
            requires=a10constants.LOADBALANCERS_LIST))
        return failover_flow

    def get_failover_restore_vthunder_flow(self):
        """Perform vthunder restore"""
        sf_name = 'a10-house-keeper-failover-restore-vthunder'
        failover_flow = linear_flow.Flow(sf_name)

        return failover_flow
