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
from oslo_log import log as logging
from taskflow.patterns import linear_flow
from taskflow.patterns import unordered_flow

from octavia.common import constants
from octavia.common import exceptions
from octavia.controller.worker.flows import amphora_flows
from octavia.controller.worker.flows import listener_flows
from octavia.controller.worker.flows import member_flows
from octavia.controller.worker.flows import pool_flows
from octavia.controller.worker.tasks import compute_tasks
from octavia.controller.worker.tasks import database_tasks
from octavia.controller.worker.tasks import lifecycle_tasks
from octavia.controller.worker.tasks import network_tasks
from octavia.db import api as db_apis
from octavia.db import repositories as repo

from a10_octavia.common import a10constants
from a10_octavia.controller.worker.flows import a10_l7policy_flows
from a10_octavia.controller.worker.flows import a10_listener_flows
from a10_octavia.controller.worker.flows import a10_pool_flows
from a10_octavia.controller.worker.flows import vthunder_flows
from a10_octavia.controller.worker.tasks import a10_compute_tasks
from a10_octavia.controller.worker.tasks import a10_database_tasks
from a10_octavia.controller.worker.tasks import a10_network_tasks
from a10_octavia.controller.worker.tasks import nat_pool_tasks
from a10_octavia.controller.worker.tasks import virtual_server_tasks
from a10_octavia.controller.worker.tasks import vthunder_tasks
from a10_octavia.db import repositories as a10repo


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class LoadBalancerFlows(object):

    def __init__(self):
        self.amp_flows = amphora_flows.AmphoraFlows()
        self.listener_flows = listener_flows.ListenerFlows()
        self.pool_flows = pool_flows.PoolFlows()
        self.member_flows = member_flows.MemberFlows()
        self.vthunder_flows = vthunder_flows.VThunderFlows()
        self._listener_flows = a10_listener_flows.ListenerFlows()
        self._l7policy_flows = a10_l7policy_flows.L7PolicyFlows()
        self._pool_flows = a10_pool_flows.PoolFlows()
        self._lb_repo = repo.LoadBalancerRepository()
        self._vthunder_repo = a10repo.VThunderRepository()
        self.loadbalancer_repo = a10repo.LoadBalancerRepository()

    def get_create_load_balancer_flow(self, load_balancer_id, topology, project_id,
                                      listeners=None):
        """Flow to create a load balancer"""

        f_name = constants.CREATE_LOADBALANCER_FLOW
        lb_create_flow = linear_flow.Flow(f_name)
        lb_create_flow.add(lifecycle_tasks.LoadBalancerIDToErrorOnRevertTask(
            requires=constants.LOADBALANCER_ID))
        lb_create_flow.add(vthunder_tasks.VthunderInstanceBusy(
            requires=a10constants.COMPUTE_BUSY))

        lb_create_flow.add(database_tasks.ReloadLoadBalancer(
            requires=constants.LOADBALANCER_ID,
            provides=constants.LOADBALANCER))

        lb_create_flow.add(a10_database_tasks.CheckExistingVthunderTopology(
            requires=constants.LOADBALANCER,
            inject={"topology": topology}))

        # Attaching vThunder to LB in database
        if topology == constants.TOPOLOGY_ACTIVE_STANDBY:
            lb_create_flow.add(*self._create_active_standby_topology())
            LOG.info("TOPOLOGY ===" + str(topology))
        elif topology == constants.TOPOLOGY_SINGLE:
            lb_create_flow.add(*self._create_single_topology())
            LOG.info("TOPOLOGY ===" + str(topology))
        else:
            LOG.error("Unknown topology: %s.  Unable to build load balancer.",
                      topology)
            raise exceptions.InvalidTopology(topology=topology)

        # IMP: Now creating vThunder config here
        post_amp_prefix = constants.POST_LB_AMP_ASSOCIATION_SUBFLOW
        vthunder = self._vthunder_repo.get_vthunder_by_project_id(db_apis.get_session(),
                                                                  project_id)

        lb_create_flow.add(a10_database_tasks.GetFlavorData(
            rebind={a10constants.LB_RESOURCE: constants.LOADBALANCER},
            provides=constants.FLAVOR_DATA))
        lb_create_flow.add(
            self.get_post_lb_vthunder_association_flow(
                post_amp_prefix, load_balancer_id, topology, vthunder,
                mark_active=(not listeners)))
        lb_create_flow.add(a10_database_tasks.CountLoadbalancersWithFlavor(
            requires=(constants.LOADBALANCER, a10constants.VTHUNDER),
            provides=a10constants.LB_COUNT_FLAVOR))
        lb_create_flow.add(vthunder_tasks.AllowL2DSR(
            requires=(constants.SUBNET, constants.AMPHORA,
                      a10constants.LB_COUNT_FLAVOR, constants.FLAVOR_DATA)))
        lb_create_flow.add(nat_pool_tasks.NatPoolCreate(
            requires=(constants.LOADBALANCER,
                      a10constants.VTHUNDER, constants.FLAVOR_DATA)))
        lb_create_flow.add(virtual_server_tasks.CreateVirtualServerTask(
            requires=(constants.LOADBALANCER, a10constants.VTHUNDER,
                      constants.FLAVOR_DATA)))
        lb_create_flow.add(vthunder_tasks.WriteMemory(
            requires=a10constants.VTHUNDER))
        lb_create_flow.add(a10_database_tasks.SetThunderUpdatedAt(
            requires=a10constants.VTHUNDER))

        # For first LB, vcs just setup and need sync. config and reload vBlade severial times.
        if not vthunder and topology == constants.TOPOLOGY_ACTIVE_STANDBY:
            lb_create_flow.add(a10_database_tasks.GetBackupVThunderByLoadBalancer(
                name="get-blade-thunder-for-checking",
                requires=constants.LOADBALANCER,
                provides=a10constants.BACKUP_VTHUNDER))
            lb_create_flow.add(virtual_server_tasks.WaitVirtualServerReadyOnBlade(
                requires=(constants.LOADBALANCER),
                rebind={a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER}))

        return lb_create_flow

    def _create_single_topology(self):
        return (self.vthunder_flows.get_vthunder_for_lb_subflow(
            prefix=constants.ROLE_STANDALONE,
            role=constants.ROLE_MASTER),)

    def _create_active_standby_topology(
            self, lf_name=constants.CREATE_LOADBALANCER_FLOW):
        anti_affinity = CONF.a10_nova.enable_anti_affinity
        flows = []
        if anti_affinity:
            flows.append(
                a10_compute_tasks.NovaServerGroupCreate(
                    name=lf_name + '-' +
                    constants.CREATE_SERVER_GROUP_FLOW,
                    requires=(constants.LOADBALANCER_ID),
                    provides=constants.SERVER_GROUP_ID))

            flows.append(
                database_tasks.UpdateLBServerGroupInDB(
                    name=lf_name + '-' +
                    constants.UPDATE_LB_SERVERGROUPID_FLOW,
                    requires=(constants.LOADBALANCER_ID,
                              constants.SERVER_GROUP_ID)))

        f_name = constants.CREATE_LOADBALANCER_FLOW
        amps_flow = unordered_flow.Flow(f_name)
        master_amp_sf = self.vthunder_flows.get_vthunder_for_lb_subflow(
            prefix=constants.ROLE_MASTER, role=constants.ROLE_MASTER)

        backup_amp_sf = self.vthunder_flows.get_vthunder_for_lb_subflow(
            prefix=constants.ROLE_BACKUP, role=constants.ROLE_BACKUP)
        amps_flow.add(master_amp_sf, backup_amp_sf)

        return flows + [amps_flow]

    def get_post_lb_vthunder_association_flow(self, prefix, load_balancer_id, topology,
                                              vthunder, mark_active=True):
        """Flow to manage networking after lb creation"""
        sf_name = prefix + '-' + constants.POST_LB_AMP_ASSOCIATION_SUBFLOW
        post_create_lb_flow = linear_flow.Flow(sf_name)
        post_create_lb_flow.add(
            database_tasks.ReloadLoadBalancer(
                name=sf_name + '-' + constants.RELOAD_LB_AFTER_AMP_ASSOC,
                requires=constants.LOADBALANCER_ID,
                provides=constants.LOADBALANCER))
        # IMP: here we will inject network flow
        new_LB_net_subflow = self.get_new_lb_networking_subflow(topology, vthunder)
        post_create_lb_flow.add(new_LB_net_subflow)

        if not vthunder and topology == constants.TOPOLOGY_ACTIVE_STANDBY:
            post_create_lb_flow.add(
                vthunder_tasks.CreateHealthMonitorOnVThunder(
                    name=a10constants.CREATE_HEALTH_MONITOR_ON_VTHUNDER_MASTER,
                    requires=a10constants.VTHUNDER))
            vrrp_subflow = self.vthunder_flows.get_vrrp_subflow(prefix)
            post_create_lb_flow.add(vrrp_subflow)

        post_create_lb_flow.add(database_tasks.UpdateLoadbalancerInDB(
            requires=[constants.LOADBALANCER, constants.UPDATE_DICT]))

        if CONF.a10_global.handle_vrid:
            post_create_lb_flow.add(self.handle_vrid_for_loadbalancer_subflow())

        if mark_active:
            post_create_lb_flow.add(database_tasks.MarkLBActiveInDB(
                name=sf_name + '-' + constants.MARK_LB_ACTIVE_INDB,
                requires=constants.LOADBALANCER))
        return post_create_lb_flow

    def get_delete_load_balancer_flow(self, lb, deleteCompute, cascade):
        """Flow to delete load balancer"""

        store = {}
        delete_LB_flow = linear_flow.Flow(constants.DELETE_LOADBALANCER_FLOW)
        delete_LB_flow.add(lifecycle_tasks.LoadBalancerToErrorOnRevertTask(
            requires=constants.LOADBALANCER))
        delete_LB_flow.add(vthunder_tasks.VthunderInstanceBusy(
            requires=a10constants.COMPUTE_BUSY))

        delete_LB_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        if lb.topology == constants.TOPOLOGY_ACTIVE_STANDBY:
            delete_LB_flow.add(vthunder_tasks.GetMasterVThunder(
                name=a10constants.GET_MASTER_VTHUNDER,
                requires=a10constants.VTHUNDER,
                provides=a10constants.VTHUNDER))
        delete_LB_flow.add(a10_database_tasks.MarkVThunderStatusInDB(
            requires=a10constants.VTHUNDER,
            inject={"status": constants.PENDING_DELETE}))
        delete_LB_flow.add(compute_tasks.NovaServerGroupDelete(
            requires=constants.SERVER_GROUP_ID))
        delete_LB_flow.add(database_tasks.MarkLBAmphoraeHealthBusy(
            requires=constants.LOADBALANCER))
        if cascade:
            (pools_listeners_delete, store) = self._get_cascade_delete_pools_listeners_flow(lb)
            delete_LB_flow.add(pools_listeners_delete)
        delete_LB_flow.add(database_tasks.GetAmphoraeFromLoadbalancer(
            requires=constants.LOADBALANCER,
            provides=constants.AMPHORA))
        delete_LB_flow.add(a10_database_tasks.GetLoadBalancerListForDeletion(
            requires=(a10constants.VTHUNDER, constants.LOADBALANCER),
            provides=a10constants.LOADBALANCERS_LIST))
        if lb.topology == "ACTIVE_STANDBY":
            delete_LB_flow.add(a10_database_tasks.GetBackupVThunderByLoadBalancer(
                requires=(constants.LOADBALANCER, a10constants.VTHUNDER),
                provides=a10constants.BACKUP_VTHUNDER))
        if not deleteCompute:
            delete_LB_flow.add(a10_network_tasks.CalculateDelta(
                requires=(constants.LOADBALANCER, a10constants.LOADBALANCERS_LIST),
                provides=constants.DELTAS))
            delete_LB_flow.add(a10_network_tasks.HandleNetworkDeltas(
                requires=constants.DELTAS, provides=constants.ADDED_PORTS))
            delete_LB_flow.add(vthunder_tasks.AmphoraePostNetworkUnplug(
                name=a10constants.AMPHORA_POST_NETWORK_UNPLUG,
                requires=(constants.LOADBALANCER, constants.ADDED_PORTS, a10constants.VTHUNDER)))
            delete_LB_flow.add(
                vthunder_tasks.VThunderComputeConnectivityWait(
                    name=a10constants.VTHUNDER_CONNECTIVITY_WAIT,
                    requires=(a10constants.VTHUNDER, constants.AMPHORA)))
            if lb.topology == "ACTIVE_STANDBY":
                delete_LB_flow.add(
                    vthunder_tasks.VThunderComputeConnectivityWait(
                        name=a10constants.BACKUP_CONNECTIVITY_WAIT + "-before-unplug",
                        rebind={a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER},
                        requires=constants.AMPHORA))
                delete_LB_flow.add(vthunder_tasks.AmphoraePostNetworkUnplug(
                    name=a10constants.AMPHORA_POST_NETWORK_UNPLUG_FOR_BACKUP_VTHUNDER,
                    requires=(constants.LOADBALANCER, constants.ADDED_PORTS),
                    rebind={a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER}))
                delete_LB_flow.add(
                    vthunder_tasks.VThunderComputeConnectivityWait(
                        name=a10constants.BACKUP_CONNECTIVITY_WAIT,
                        rebind={a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER},
                        requires=constants.AMPHORA))
                delete_LB_flow.add(vthunder_tasks.VCSSyncWait(
                    name="vip-unplug-wait-vcs-ready",
                    requires=a10constants.VTHUNDER))
                delete_LB_flow.add(vthunder_tasks.GetMasterVThunder(
                    name=a10constants.GET_VTHUNDER_MASTER,
                    requires=a10constants.VTHUNDER,
                    provides=a10constants.VTHUNDER))
        delete_LB_flow.add(a10_network_tasks.GetLBResourceSubnet(
            rebind={a10constants.LB_RESOURCE: constants.LOADBALANCER},
            provides=constants.SUBNET))
        delete_LB_flow.add(
            a10_database_tasks.GetChildProjectsOfParentPartition(
                requires=[a10constants.VTHUNDER],
                rebind={a10constants.LB_RESOURCE: constants.LOADBALANCER},
                provides=a10constants.PARTITION_PROJECT_LIST
            ))
        delete_LB_flow.add(
            a10_database_tasks.CountLoadbalancersInProjectBySubnet(
                requires=[constants.SUBNET, a10constants.PARTITION_PROJECT_LIST],
                provides=a10constants.LB_COUNT_SUBNET))
        if CONF.a10_global.handle_vrid:
            delete_LB_flow.add(self.get_delete_lb_vrid_subflow(deleteCompute))
        delete_LB_flow.add(a10_network_tasks.DeallocateVIP(
            requires=[constants.LOADBALANCER, a10constants.LB_COUNT_SUBNET]))
        delete_LB_flow.add(virtual_server_tasks.DeleteVirtualServerTask(
            requires=(constants.LOADBALANCER, a10constants.VTHUNDER)))
        delete_LB_flow.add(a10_database_tasks.GetFlavorData(
            rebind={a10constants.LB_RESOURCE: constants.LOADBALANCER},
            provides=constants.FLAVOR_DATA))
        delete_LB_flow.add(a10_database_tasks.CountLoadbalancersWithFlavor(
            requires=(constants.LOADBALANCER, a10constants.VTHUNDER),
            provides=a10constants.LB_COUNT_FLAVOR))
        delete_LB_flow.add(vthunder_tasks.DeleteL2DSR(
            requires=(constants.SUBNET, constants.AMPHORA,
                      a10constants.LB_COUNT_FLAVOR,
                      a10constants.LB_COUNT_SUBNET,
                      constants.FLAVOR_DATA)))
        delete_LB_flow.add(nat_pool_tasks.NatPoolDelete(
            requires=(constants.LOADBALANCER, a10constants.VTHUNDER,
                      a10constants.LB_COUNT_FLAVOR, constants.FLAVOR_DATA)))
        if deleteCompute:
            delete_LB_flow.add(compute_tasks.DeleteAmphoraeOnLoadBalancer(
                requires=constants.LOADBALANCER))
        delete_LB_flow.add(a10_database_tasks.MarkVThunderStatusInDB(
            name=a10constants.MARK_VTHUNDER_MASTER_DELETED_IN_DB,
            requires=a10constants.VTHUNDER,
            inject={"status": constants.DELETED}))
        delete_LB_flow.add(database_tasks.MarkLBAmphoraeDeletedInDB(
            requires=constants.LOADBALANCER))
        delete_LB_flow.add(database_tasks.DisableLBAmphoraeHealthMonitoring(
            requires=constants.LOADBALANCER))
        delete_LB_flow.add(database_tasks.MarkLBDeletedInDB(
            requires=constants.LOADBALANCER))
        delete_LB_flow.add(database_tasks.DecrementLoadBalancerQuota(
            requires=constants.LOADBALANCER))
        if not deleteCompute:
            delete_LB_flow.add(vthunder_tasks.WriteMemory(
                requires=a10constants.VTHUNDER))
        delete_LB_flow.add(a10_database_tasks.SetThunderUpdatedAt(
            name=a10constants.SET_THUNDER_UPDATE_AT,
            requires=a10constants.VTHUNDER))
        if lb.topology == "ACTIVE_STANDBY":
            delete_LB_flow.add(a10_database_tasks.MarkVThunderStatusInDB(
                name=a10constants.MARK_VTHUNDER_BACKUP_DELETED_IN_DB,
                rebind={a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER},
                inject={"status": constants.DELETED}))
            delete_LB_flow.add(a10_database_tasks.SetThunderUpdatedAt(
                name=a10constants.SET_THUNDER_BACKUP_UPDATE_AT,
                rebind={a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER}))
        return (delete_LB_flow, store)

    def get_new_lb_networking_subflow(self, topology, vthunder):
        """Subflow to setup networking for amphora"""
        new_LB_net_subflow = linear_flow.Flow(constants.
                                              LOADBALANCER_NETWORKING_SUBFLOW)
        new_LB_net_subflow.add(database_tasks.GetAmphoraeFromLoadbalancer(
            requires=constants.LOADBALANCER,
            provides=constants.AMPHORA))
        new_LB_net_subflow.add(vthunder_tasks.UpdateAcosVersionInVthunderEntry(
            name=a10constants.UPDATE_ACOS_VERSION_IN_VTHUNDER_ENTRY,
            requires=(constants.LOADBALANCER, a10constants.VTHUNDER)))
        new_LB_net_subflow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            name=a10constants.GET_VTHUNDER_BY_LB,
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        if vthunder and topology == constants.TOPOLOGY_SINGLE:
            new_LB_net_subflow.add(a10_database_tasks.GetLoadBalancerListByProjectID(
                requires=a10constants.VTHUNDER,
                provides=a10constants.LOADBALANCERS_LIST))
            new_LB_net_subflow.add(a10_network_tasks.CalculateDelta(
                requires=(constants.LOADBALANCER, a10constants.LOADBALANCERS_LIST),
                provides=constants.DELTAS))
            new_LB_net_subflow.add(a10_network_tasks.HandleNetworkDeltas(
                requires=constants.DELTAS, provides=constants.ADDED_PORTS))
            # managing interface additions here
            new_LB_net_subflow.add(vthunder_tasks.AmphoraePostVIPPlug(
                name=a10constants.AMPHORAE_POST_VIP_PLUG,
                requires=(constants.LOADBALANCER, a10constants.VTHUNDER,
                          constants.ADDED_PORTS)))
            new_LB_net_subflow.add(
                vthunder_tasks.VThunderComputeConnectivityWait(
                    name=a10constants.VTHUNDER_CONNECTIVITY_WAIT,
                    requires=(a10constants.VTHUNDER, constants.AMPHORA)))
            new_LB_net_subflow.add(vthunder_tasks.EnableInterface(
                name=a10constants.ENABLE_VTHUNDER_INTERFACE,
                requires=(a10constants.VTHUNDER, constants.LOADBALANCER,
                          constants.ADDED_PORTS)))
        else:
            new_LB_net_subflow.add(vthunder_tasks.VThunderComputeConnectivityWait(
                name=a10constants.VTHUNDER_CONNECTIVITY_WAIT,
                requires=(a10constants.VTHUNDER, constants.AMPHORA)))
        new_LB_net_subflow.add(vthunder_tasks.EnableInterface(
            name=a10constants.ENABLE_MASTER_VTHUNDER_INTERFACE,
            inject={constants.ADDED_PORTS: {}},
            requires=(a10constants.VTHUNDER, constants.LOADBALANCER, constants.ADDED_PORTS)))
        new_LB_net_subflow.add(a10_database_tasks.MarkVThunderStatusInDB(
            name=a10constants.MARK_VTHUNDER_MASTER_ACTIVE_IN_DB,
            requires=a10constants.VTHUNDER,
            inject={a10constants.STATUS: constants.ACTIVE}))
        if topology == constants.TOPOLOGY_ACTIVE_STANDBY:
            new_LB_net_subflow.add(
                a10_database_tasks.GetBackupVThunderByLoadBalancer(
                    name=a10constants.GET_BACKUP_VTHUNDER_BY_LB,
                    requires=constants.LOADBALANCER,
                    provides=a10constants.BACKUP_VTHUNDER))
            new_LB_net_subflow.add(vthunder_tasks.UpdateAcosVersionInVthunderEntry(
                name=a10constants.UPDATE_ACOS_VERSION_FOR_BACKUP_VTHUNDER,
                requires=constants.LOADBALANCER,
                rebind={a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER}))
            new_LB_net_subflow.add(
                a10_database_tasks.GetBackupVThunderByLoadBalancer(
                    name=a10constants.BACKUP_VTHUNDER,
                    requires=(constants.LOADBALANCER, a10constants.VTHUNDER),
                    provides=a10constants.BACKUP_VTHUNDER))
            if vthunder:
                new_LB_net_subflow.add(a10_database_tasks.GetLoadBalancerListByProjectID(
                    requires=a10constants.VTHUNDER,
                    provides=a10constants.LOADBALANCERS_LIST))
                new_LB_net_subflow.add(a10_network_tasks.CalculateDelta(
                    requires=(constants.LOADBALANCER, a10constants.LOADBALANCERS_LIST),
                    provides=constants.DELTAS))
                new_LB_net_subflow.add(a10_network_tasks.HandleNetworkDeltas(
                    requires=constants.DELTAS, provides=constants.ADDED_PORTS))

                # Make sure vcs ready before first probe-network-devices on Master
                new_LB_net_subflow.add(
                    vthunder_tasks.VThunderComputeConnectivityWait(
                        name="backup-compute-conn-wait-before-probe-device",
                        rebind={
                            a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER},
                        requires=constants.AMPHORA))
                new_LB_net_subflow.add(vthunder_tasks.VCSSyncWait(
                    name="wait-vcs-ready-before-probe-device",
                    requires=a10constants.VTHUNDER))
                new_LB_net_subflow.add(vthunder_tasks.AmphoraePostVIPPlug(
                    name=a10constants.AMPHORAE_POST_VIP_PLUG_FOR_MASTER,
                    requires=(constants.LOADBALANCER, a10constants.VTHUNDER,
                              constants.ADDED_PORTS)))
                new_LB_net_subflow.add(
                    vthunder_tasks.VThunderComputeConnectivityWait(
                        name="make-sure-backup-is-ready-after-reload-master",
                        rebind={
                            a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER},
                        requires=constants.AMPHORA))
                new_LB_net_subflow.add(vthunder_tasks.AmphoraePostVIPPlug(
                    name=a10constants.AMPHORAE_POST_VIP_PLUG_FOR_BACKUP,
                    requires=(constants.LOADBALANCER, constants.ADDED_PORTS),
                    rebind={a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER}))
                new_LB_net_subflow.add(
                    vthunder_tasks.VThunderComputeConnectivityWait(
                        name=a10constants.MASTER_CONNECTIVITY_WAIT,
                        requires=(a10constants.VTHUNDER, constants.AMPHORA)))
                new_LB_net_subflow.add(
                    vthunder_tasks.VThunderComputeConnectivityWait(
                        name=a10constants.BACKUP_CONNECTIVITY_WAIT,
                        rebind={
                            a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER},
                        requires=constants.AMPHORA))
                new_LB_net_subflow.add(vthunder_tasks.VCSSyncWait(
                    name="backup-plug-wait-vcs-ready",
                    requires=a10constants.VTHUNDER))
                new_LB_net_subflow.add(vthunder_tasks.GetVThunderInterface(
                    name=a10constants.GET_MASTER_VTHUNDER_INTERFACE,
                    requires=a10constants.VTHUNDER,
                    provides=(a10constants.IFNUM_MASTER, a10constants.IFNUM_BACKUP)))
                new_LB_net_subflow.add(vthunder_tasks.EnableInterface(
                    name=a10constants.MASTER_ENABLE_INTERFACE,
                    requires=(a10constants.VTHUNDER, constants.LOADBALANCER, constants.ADDED_PORTS,
                              a10constants.IFNUM_MASTER, a10constants.IFNUM_BACKUP)))
                new_LB_net_subflow.add(vthunder_tasks.GetVThunderInterface(
                    name=a10constants.GET_BACKUP_VTHUNDER_INTERFACE,
                    requires=a10constants.VTHUNDER,
                    rebind={a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER},
                    provides=(a10constants.IFNUM_MASTER, a10constants.IFNUM_BACKUP)))
                new_LB_net_subflow.add(vthunder_tasks.VCSSyncWait(
                    name="wait-vcs-ready-before-master-reload",
                    requires=a10constants.VTHUNDER))
                new_LB_net_subflow.add(vthunder_tasks.AmphoraePostVIPPlug(
                    name=a10constants.AMP_POST_VIP_PLUG,
                    requires=(constants.LOADBALANCER, a10constants.VTHUNDER,
                              constants.ADDED_PORTS)))
                new_LB_net_subflow.add(
                    vthunder_tasks.VThunderComputeConnectivityWait(
                        name=a10constants.CONNECTIVITY_WAIT_FOR_MASTER_VTHUNDER,
                        requires=(a10constants.VTHUNDER, constants.AMPHORA)))
                new_LB_net_subflow.add(
                    vthunder_tasks.VThunderComputeConnectivityWait(
                        name=a10constants.CONNECTIVITY_WAIT_FOR_BACKUP_VTHUNDER,
                        rebind={
                            a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER},
                        requires=constants.AMPHORA))
                new_LB_net_subflow.add(vthunder_tasks.VCSSyncWait(
                    name="int-sync-reload-wait-vcs-ready",
                    requires=a10constants.VTHUNDER))
                new_LB_net_subflow.add(vthunder_tasks.GetMasterVThunder(
                    name=a10constants.GET_VTHUNDER_MASTER,
                    requires=a10constants.VTHUNDER,
                    provides=a10constants.VTHUNDER))
                new_LB_net_subflow.add(a10_database_tasks.GetBackupVThunderByLoadBalancer(
                    name="get-backup-vthunder-after-get-master",
                    requires=(constants.LOADBALANCER, a10constants.VTHUNDER),
                    provides=a10constants.BACKUP_VTHUNDER))
                new_LB_net_subflow.add(vthunder_tasks.EnableInterface(
                    name=a10constants.BACKUP_ENABLE_INTERFACE,
                    requires=(a10constants.VTHUNDER, constants.LOADBALANCER, constants.ADDED_PORTS,
                              a10constants.IFNUM_MASTER, a10constants.IFNUM_BACKUP)))
            else:
                new_LB_net_subflow.add(vthunder_tasks.VThunderComputeConnectivityWait(
                    name=a10constants.CONNECTIVITY_WAIT_FOR_BACKUP_VTHUNDER,
                    rebind={a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER},
                    requires=constants.AMPHORA))
            new_LB_net_subflow.add(vthunder_tasks.EnableInterface(
                name=a10constants.ENABLE_BACKUP_VTHUNDER_INTERFACE,
                rebind={a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER},
                inject={constants.ADDED_PORTS: {}},
                requires=(constants.LOADBALANCER, constants.ADDED_PORTS)))
            new_LB_net_subflow.add(a10_database_tasks.MarkVThunderStatusInDB(
                name=a10constants.MARK_VTHUNDER_BACKUP_ACTIVE_IN_DB,
                rebind={a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER},
                inject={a10constants.STATUS: constants.ACTIVE}))
        new_LB_net_subflow.add(a10_network_tasks.PlugVIP(
            requires=constants.LOADBALANCER,
            provides=constants.AMPS_DATA))
        new_LB_net_subflow.add(a10_network_tasks.ApplyQos(
            requires=(constants.LOADBALANCER, constants.AMPS_DATA, constants.UPDATE_DICT)))
        new_LB_net_subflow.add(database_tasks.UpdateAmphoraeVIPData(
            requires=constants.AMPS_DATA))
        new_LB_net_subflow.add(database_tasks.ReloadLoadBalancer(
            name=constants.RELOAD_LB_AFTER_PLUG_VIP,
            requires=constants.LOADBALANCER_ID,
            provides=constants.LOADBALANCER))
        return new_LB_net_subflow

    def get_update_load_balancer_flow(self, topology):
        """Flow to update load balancer."""

        update_LB_flow = linear_flow.Flow(constants.UPDATE_LOADBALANCER_FLOW)
        update_LB_flow.add(lifecycle_tasks.LoadBalancerToErrorOnRevertTask(
            requires=constants.LOADBALANCER))
        update_LB_flow.add(vthunder_tasks.VthunderInstanceBusy(
            requires=a10constants.COMPUTE_BUSY))
        update_LB_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        if topology == constants.TOPOLOGY_ACTIVE_STANDBY:
            update_LB_flow.add(vthunder_tasks.GetMasterVThunder(
                name=a10constants.GET_MASTER_VTHUNDER,
                requires=a10constants.VTHUNDER,
                provides=a10constants.VTHUNDER))
        update_LB_flow.add(a10_database_tasks.MarkVThunderStatusInDB(
            requires=a10constants.VTHUNDER,
            inject={"status": constants.PENDING_UPDATE}))
        update_LB_flow.add(vthunder_tasks.SetupDeviceNetworkMap(
            requires=a10constants.VTHUNDER,
            provides=a10constants.VTHUNDER))
        update_LB_flow.add(network_tasks.ApplyQos(
            requires=(constants.LOADBALANCER, constants.UPDATE_DICT)))
        # update_LB_flow.add(amphora_driver_tasks.ListenersUpdate(
        #    requires=[constants.LOADBALANCER, constants.LISTENERS]))
        # post_create_lb_flow.add(handle_vrid_for_loadbalancer_subflow())
        if CONF.a10_global.handle_vrid:
            update_LB_flow.add(self.handle_vrid_for_loadbalancer_subflow())
        update_LB_flow.add(database_tasks.GetAmphoraeFromLoadbalancer(
            requires=constants.LOADBALANCER,
            provides=constants.AMPHORA))
        update_LB_flow.add(a10_database_tasks.GetLoadbalancersInProjectBySubnet(
            requires=[constants.SUBNET, a10constants.PARTITION_PROJECT_LIST],
            provides=a10constants.LOADBALANCERS_LIST))
        update_LB_flow.add(a10_database_tasks.CheckForL2DSRFlavor(
            rebind={a10constants.LB_RESOURCE: a10constants.LOADBALANCERS_LIST},
            provides=a10constants.L2DSR_FLAVOR))
        update_LB_flow.add(a10_database_tasks.CountMembersInProjectBySubnet(
            requires=[constants.SUBNET, a10constants.PARTITION_PROJECT_LIST],
            provides=a10constants.MEMBER_COUNT))
        update_LB_flow.add(vthunder_tasks.UpdateL2DSR(
            requires=(constants.SUBNET, constants.AMPHORA,
                      a10constants.MEMBER_COUNT, a10constants.L2DSR_FLAVOR)))
        update_LB_flow.add(a10_database_tasks.GetFlavorData(
            rebind={a10constants.LB_RESOURCE: constants.LOADBALANCER},
            provides=constants.FLAVOR_DATA))
        update_LB_flow.add(virtual_server_tasks.UpdateVirtualServerTask(
            requires=(constants.LOADBALANCER, a10constants.VTHUNDER,
                      constants.FLAVOR_DATA)))
        update_LB_flow.add(database_tasks.UpdateLoadbalancerInDB(
            requires=[constants.LOADBALANCER, constants.UPDATE_DICT]))
        update_LB_flow.add(database_tasks.MarkLBActiveInDB(
            requires=constants.LOADBALANCER))
        update_LB_flow.add(vthunder_tasks.WriteMemory(
            requires=a10constants.VTHUNDER))
        update_LB_flow.add(a10_database_tasks.MarkVThunderStatusInDB(
            name="pending_update_to_active",
            requires=a10constants.VTHUNDER,
            inject={"status": constants.ACTIVE}))
        update_LB_flow.add(a10_database_tasks.SetThunderUpdatedAt(
            requires=a10constants.VTHUNDER))
        return update_LB_flow

    def get_update_rack_load_balancer_flow(self, vthunder_conf, device_dict, topology):
        """Flow to update load balancer."""

        update_LB_flow = linear_flow.Flow(constants.UPDATE_LOADBALANCER_FLOW)
        update_LB_flow.add(lifecycle_tasks.LoadBalancerToErrorOnRevertTask(
            requires=constants.LOADBALANCER))

        # device-name flavor support
        update_LB_flow.add(a10_database_tasks.GetFlavorData(
            rebind={a10constants.LB_RESOURCE: constants.LOADBALANCER},
            provides=constants.FLAVOR_DATA))
        update_LB_flow.add(vthunder_tasks.GetVthunderConfByFlavor(
            inject={a10constants.VTHUNDER_CONFIG: vthunder_conf,
                    a10constants.DEVICE_CONFIG_DICT: device_dict},
            requires=(constants.LOADBALANCER, a10constants.VTHUNDER_CONFIG,
                      a10constants.DEVICE_CONFIG_DICT, constants.FLAVOR_DATA),
            provides=(a10constants.VTHUNDER_CONFIG, a10constants.USE_DEVICE_FLAVOR)))

        update_LB_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        if topology == constants.TOPOLOGY_ACTIVE_STANDBY:
            update_LB_flow.add(vthunder_tasks.GetMasterVThunder(
                name=a10constants.GET_MASTER_VTHUNDER,
                requires=a10constants.VTHUNDER,
                provides=a10constants.VTHUNDER))
        update_LB_flow.add(a10_database_tasks.MarkVThunderStatusInDB(
            requires=a10constants.VTHUNDER,
            inject={"status": constants.PENDING_UPDATE}))
        update_LB_flow.add(vthunder_tasks.SetupDeviceNetworkMap(
            requires=a10constants.VTHUNDER,
            provides=a10constants.VTHUNDER))
        update_LB_flow.add(network_tasks.ApplyQos(
            requires=(constants.LOADBALANCER, constants.UPDATE_DICT)))
        if CONF.a10_global.handle_vrid:
            update_LB_flow.add(self.handle_vrid_for_loadbalancer_subflow())

        update_LB_flow.add(virtual_server_tasks.UpdateVirtualServerTask(
            requires=(constants.LOADBALANCER, a10constants.VTHUNDER,
                      constants.FLAVOR_DATA)))
        update_LB_flow.add(database_tasks.UpdateLoadbalancerInDB(
            requires=[constants.LOADBALANCER, constants.UPDATE_DICT]))
        if CONF.a10_global.network_type == 'vlan':
            update_LB_flow.add(vthunder_tasks.TagInterfaceForLB(
                requires=[constants.LOADBALANCER,
                          a10constants.VTHUNDER]))
        update_LB_flow.add(database_tasks.MarkLBActiveInDB(
            requires=constants.LOADBALANCER))
        update_LB_flow.add(vthunder_tasks.WriteMemory(
            requires=a10constants.VTHUNDER))
        update_LB_flow.add(a10_database_tasks.MarkVThunderStatusInDB(
            name="pending_update_to_active",
            requires=a10constants.VTHUNDER,
            inject={"status": constants.ACTIVE}))
        update_LB_flow.add(a10_database_tasks.SetThunderUpdatedAt(
            requires=a10constants.VTHUNDER))
        return update_LB_flow

    def get_create_rack_vthunder_load_balancer_flow(
            self, vthunder_conf, device_dict, topology, listeners=None):
        """Flow to create rack load balancer"""

        f_name = constants.CREATE_LOADBALANCER_FLOW
        lb_create_flow = linear_flow.Flow(f_name)

        lb_create_flow.add(lifecycle_tasks.LoadBalancerIDToErrorOnRevertTask(
            requires=constants.LOADBALANCER_ID))
        lb_create_flow.add(database_tasks.ReloadLoadBalancer(
            requires=constants.LOADBALANCER_ID,
            provides=constants.LOADBALANCER))

        # device-name flavor support
        lb_create_flow.add(a10_database_tasks.GetFlavorData(
            rebind={a10constants.LB_RESOURCE: constants.LOADBALANCER},
            provides=constants.FLAVOR_DATA))
        lb_create_flow.add(vthunder_tasks.GetVthunderConfByFlavor(
            inject={a10constants.VTHUNDER_CONFIG: vthunder_conf,
                    a10constants.DEVICE_CONFIG_DICT: device_dict},
            requires=(constants.LOADBALANCER, a10constants.VTHUNDER_CONFIG,
                      a10constants.DEVICE_CONFIG_DICT, constants.FLAVOR_DATA),
            provides=(a10constants.VTHUNDER_CONFIG, a10constants.USE_DEVICE_FLAVOR)))
        lb_create_flow.add(vthunder_tasks.HandleACOSPartitionChange(
            requires=(constants.LOADBALANCER, a10constants.VTHUNDER_CONFIG),
            provides=a10constants.VTHUNDER_CONFIG))
        lb_create_flow.add(
            a10_database_tasks.CheckExistingThunderToProjectMappedEntries(
                requires=(
                    constants.LOADBALANCER,
                    a10constants.VTHUNDER_CONFIG,
                    a10constants.USE_DEVICE_FLAVOR)))
        lb_create_flow.add(
            self.vthunder_flows.get_rack_vthunder_for_lb_subflow(
                vthunder_conf=a10constants.VTHUNDER_CONFIG,
                prefix=constants.ROLE_STANDALONE,
                role=constants.ROLE_STANDALONE))
        post_amp_prefix = constants.POST_LB_AMP_ASSOCIATION_SUBFLOW
        lb_create_flow.add(
            self.get_post_lb_rack_vthunder_association_flow(
                post_amp_prefix, topology, mark_active=(not listeners)))
        lb_create_flow.add(nat_pool_tasks.NatPoolCreate(
            requires=(constants.LOADBALANCER,
                      a10constants.VTHUNDER, constants.FLAVOR_DATA)))
        lb_create_flow.add(virtual_server_tasks.CreateVirtualServerTask(
            requires=(constants.LOADBALANCER, a10constants.VTHUNDER,
                      constants.FLAVOR_DATA),
            provides=a10constants.STATUS))
        lb_create_flow.add(vthunder_tasks.WriteMemory(
            requires=a10constants.VTHUNDER))
        lb_create_flow.add(a10_database_tasks.SetThunderUpdatedAt(
            requires=a10constants.VTHUNDER))
        return lb_create_flow

    def get_delete_rack_vthunder_load_balancer_flow(self, lb, cascade, vthunder_conf, device_dict):
        """Flow to delete rack load balancer"""

        store = {}
        delete_LB_flow = linear_flow.Flow(constants.DELETE_LOADBALANCER_FLOW)
        delete_LB_flow.add(lifecycle_tasks.LoadBalancerToErrorOnRevertTask(
            requires=constants.LOADBALANCER))
        delete_LB_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        delete_LB_flow.add(a10_database_tasks.MarkVThunderStatusInDB(
            requires=a10constants.VTHUNDER,
            inject={"status": constants.PENDING_DELETE}))
        delete_LB_flow.add(vthunder_tasks.SetupDeviceNetworkMap(
            requires=a10constants.VTHUNDER,
            provides=a10constants.VTHUNDER))
        delete_LB_flow.add(compute_tasks.NovaServerGroupDelete(
            requires=constants.SERVER_GROUP_ID))
        delete_LB_flow.add(database_tasks.MarkLBAmphoraeHealthBusy(
            requires=constants.LOADBALANCER))
        delete_LB_flow.add(a10_database_tasks.GetFlavorData(
            rebind={a10constants.LB_RESOURCE: constants.LOADBALANCER},
            provides=constants.FLAVOR_DATA))
        delete_LB_flow.add(vthunder_tasks.GetVthunderConfByFlavor(
            inject={a10constants.VTHUNDER_CONFIG: vthunder_conf,
                    a10constants.DEVICE_CONFIG_DICT: device_dict},
            requires=(constants.LOADBALANCER, a10constants.VTHUNDER_CONFIG,
                      a10constants.DEVICE_CONFIG_DICT, constants.FLAVOR_DATA),
            provides=(a10constants.VTHUNDER_CONFIG, a10constants.USE_DEVICE_FLAVOR)))
        if cascade:
            (pools_listeners_delete, store) = self._get_cascade_delete_pools_listeners_flow(lb)
            delete_LB_flow.add(pools_listeners_delete)
        delete_LB_flow.add(a10_network_tasks.GetLBResourceSubnet(
            rebind={a10constants.LB_RESOURCE: constants.LOADBALANCER},
            provides=constants.SUBNET))
        delete_LB_flow.add(
            a10_database_tasks.GetChildProjectsOfParentPartition(
                requires=[a10constants.VTHUNDER],
                rebind={a10constants.LB_RESOURCE: constants.LOADBALANCER},
                provides=a10constants.PARTITION_PROJECT_LIST
            ))
        delete_LB_flow.add(
            a10_database_tasks.CountLoadbalancersInProjectBySubnet(
                requires=[
                    constants.SUBNET,
                    a10constants.PARTITION_PROJECT_LIST,
                    a10constants.USE_DEVICE_FLAVOR],
                provides=a10constants.LB_COUNT_SUBNET))
        delete_LB_flow.add(
            a10_database_tasks.CountLoadbalancersOnThunderBySubnet(
                requires=[a10constants.VTHUNDER, constants.SUBNET, a10constants.USE_DEVICE_FLAVOR],
                provides=a10constants.LB_COUNT_THUNDER))
        if CONF.a10_global.handle_vrid:
            delete_LB_flow.add(self.get_delete_rack_lb_vrid_subflow())
        delete_LB_flow.add(a10_network_tasks.DeallocateVIP(
            requires=[constants.LOADBALANCER, a10constants.LB_COUNT_SUBNET]))
        delete_LB_flow.add(virtual_server_tasks.DeleteVirtualServerTask(
            requires=(constants.LOADBALANCER, a10constants.VTHUNDER)))
        delete_LB_flow.add(a10_database_tasks.CountLoadbalancersWithFlavor(
            requires=(constants.LOADBALANCER, a10constants.VTHUNDER),
            provides=a10constants.LB_COUNT_FLAVOR))
        delete_LB_flow.add(nat_pool_tasks.NatPoolDelete(
            requires=(constants.LOADBALANCER, a10constants.VTHUNDER,
                      a10constants.LB_COUNT_FLAVOR, constants.FLAVOR_DATA)))
        if CONF.a10_global.network_type == 'vlan':
            delete_LB_flow.add(
                vthunder_tasks.DeleteInterfaceTagIfNotInUseForLB(
                    requires=[
                        constants.LOADBALANCER,
                        a10constants.VTHUNDER]))
        delete_LB_flow.add(a10_database_tasks.MarkVThunderStatusInDB(
            name=a10constants.MARK_VTHUNDER_MASTER_DELETED_IN_DB,
            requires=a10constants.VTHUNDER,
            inject={"status": constants.DELETED}))
        delete_LB_flow.add(database_tasks.MarkLBAmphoraeDeletedInDB(
            requires=constants.LOADBALANCER))
        delete_LB_flow.add(database_tasks.DisableLBAmphoraeHealthMonitoring(
            requires=constants.LOADBALANCER))
        delete_LB_flow.add(database_tasks.MarkLBDeletedInDB(
            requires=constants.LOADBALANCER))
        delete_LB_flow.add(database_tasks.DecrementLoadBalancerQuota(
            requires=constants.LOADBALANCER))
        delete_LB_flow.add(vthunder_tasks.WriteMemory(
            requires=a10constants.VTHUNDER))
        delete_LB_flow.add(a10_database_tasks.SetThunderUpdatedAt(
            name=a10constants.SET_THUNDER_UPDATE_AT,
            requires=a10constants.VTHUNDER))
        if lb.topology == "ACTIVE_STANDBY":
            delete_LB_flow.add(a10_database_tasks.GetBackupVThunderByLoadBalancer(
                requires=constants.LOADBALANCER,
                provides=a10constants.BACKUP_VTHUNDER))
            delete_LB_flow.add(a10_database_tasks.MarkVThunderStatusInDB(
                name=a10constants.MARK_VTHUNDER_BACKUP_DELETED_IN_DB,
                rebind={a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER},
                inject={"status": constants.DELETED}))
            delete_LB_flow.add(a10_database_tasks.SetThunderUpdatedAt(
                name=a10constants.SET_THUNDER_BACKUP_UPDATE_AT,
                rebind={a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER}))
        return (delete_LB_flow, store)

    def get_post_lb_rack_vthunder_association_flow(self, prefix, topology,
                                                   mark_active=True):
        """Flow to manage networking after rack lb creation"""

        sf_name = prefix + '-' + constants.POST_LB_AMP_ASSOCIATION_SUBFLOW
        post_create_lb_flow = linear_flow.Flow(sf_name)
        post_create_lb_flow.add(vthunder_tasks.SetupDeviceNetworkMap(
            requires=a10constants.VTHUNDER,
            provides=a10constants.VTHUNDER))
        post_create_lb_flow.add(
            database_tasks.ReloadLoadBalancer(
                name=sf_name + '-' + constants.RELOAD_LB_AFTER_AMP_ASSOC,
                requires=constants.LOADBALANCER_ID,
                provides=constants.LOADBALANCER))
        post_create_lb_flow.add(database_tasks.UpdateLoadbalancerInDB(
            requires=[constants.LOADBALANCER, constants.UPDATE_DICT]))
        if CONF.a10_global.network_type == 'vlan':
            post_create_lb_flow.add(vthunder_tasks.TagInterfaceForLB(
                requires=[constants.LOADBALANCER,
                          a10constants.VTHUNDER]))
        if CONF.a10_global.handle_vrid:
            post_create_lb_flow.add(self.handle_vrid_for_loadbalancer_subflow())
        if mark_active:
            post_create_lb_flow.add(database_tasks.MarkLBActiveInDB(
                name=sf_name + '-' + constants.MARK_LB_ACTIVE_INDB,
                requires=constants.LOADBALANCER))
        return post_create_lb_flow

    def handle_vrid_for_loadbalancer_subflow(self):
        handle_vrid_for_lb_subflow = linear_flow.Flow(
            a10constants.HANDLE_VRID_LOADBALANCER_SUBFLOW)
        handle_vrid_for_lb_subflow.add(a10_network_tasks.GetLBResourceSubnet(
            rebind={a10constants.LB_RESOURCE: constants.LOADBALANCER},
            provides=constants.SUBNET))
        handle_vrid_for_lb_subflow.add(
            a10_database_tasks.GetChildProjectsOfParentPartition(
                requires=[a10constants.VTHUNDER],
                rebind={a10constants.LB_RESOURCE: constants.LOADBALANCER},
                provides=a10constants.PARTITION_PROJECT_LIST
            ))
        handle_vrid_for_lb_subflow.add(
            a10_database_tasks.GetVRIDForLoadbalancerResource(
                requires=[
                    a10constants.PARTITION_PROJECT_LIST,
                    a10constants.VTHUNDER],
                provides=a10constants.VRID_LIST))
        handle_vrid_for_lb_subflow.add(vthunder_tasks.ConfigureVRID(
            requires=a10constants.VTHUNDER))
        handle_vrid_for_lb_subflow.add(
            a10_network_tasks.HandleVRIDFloatingIP(
                requires=[
                    a10constants.VTHUNDER,
                    a10constants.VRID_LIST,
                    constants.SUBNET,
                    a10constants.VTHUNDER_CONFIG,
                    a10constants.USE_DEVICE_FLAVOR],
                rebind={
                    a10constants.LB_RESOURCE: constants.LOADBALANCER},
                provides=a10constants.VRID_LIST))
        handle_vrid_for_lb_subflow.add(
            a10_database_tasks.UpdateVRIDForLoadbalancerResource(
                requires=[
                    a10constants.VRID_LIST,
                    a10constants.VTHUNDER],
                rebind={
                    a10constants.LB_RESOURCE: constants.LOADBALANCER}))
        return handle_vrid_for_lb_subflow

    def get_delete_rack_lb_vrid_subflow(self):
        delete_lb_vrid_subflow = linear_flow.Flow(
            a10constants.DELETE_LOADBALANCER_VRID_SUBFLOW)
        delete_lb_vrid_subflow.add(
            a10_database_tasks.CountMembersInProjectBySubnet(
                requires=[constants.SUBNET, a10constants.PARTITION_PROJECT_LIST],
                provides=a10constants.MEMBER_COUNT))
        delete_lb_vrid_subflow.add(
            a10_network_tasks.GetMembersOnThunder(
                requires=[a10constants.VTHUNDER, a10constants.USE_DEVICE_FLAVOR],
                provides=a10constants.MEMBERS))
        delete_lb_vrid_subflow.add(
            a10_database_tasks.CountMembersOnThunderBySubnet(
                requires=[
                    constants.SUBNET,
                    a10constants.USE_DEVICE_FLAVOR,
                    a10constants.MEMBERS],
                provides=a10constants.MEMBER_COUNT_THUNDER))
        delete_lb_vrid_subflow.add(
            a10_database_tasks.GetVRIDForLoadbalancerResource(
                requires=[
                    a10constants.PARTITION_PROJECT_LIST,
                    a10constants.VTHUNDER],
                provides=a10constants.VRID_LIST))
        delete_lb_vrid_subflow.add(
            a10_network_tasks.DeleteVRIDPort(
                requires=[
                    a10constants.VTHUNDER,
                    a10constants.VRID_LIST,
                    constants.SUBNET,
                    a10constants.USE_DEVICE_FLAVOR,
                    a10constants.LB_COUNT_SUBNET,
                    a10constants.MEMBER_COUNT,
                    a10constants.LB_COUNT_THUNDER,
                    a10constants.MEMBER_COUNT_THUNDER],
                rebind={a10constants.LB_RESOURCE: constants.LOADBALANCER},
                provides=(
                    a10constants.VRID,
                    a10constants.DELETE_VRID)))
        delete_lb_vrid_subflow.add(a10_database_tasks.DeleteVRIDEntry(
            requires=[a10constants.VRID, a10constants.DELETE_VRID]))

        return delete_lb_vrid_subflow

    def get_delete_lb_vrid_subflow(self, deleteCompute):
        topology = CONF.a10_controller_worker.loadbalancer_topology

        delete_lb_vrid_subflow = linear_flow.Flow(
            a10constants.DELETE_LOADBALANCER_VRID_SUBFLOW)
        delete_lb_vrid_subflow.add(
            a10_database_tasks.CountMembersInProjectBySubnet(
                requires=[constants.SUBNET, a10constants.PARTITION_PROJECT_LIST],
                provides=a10constants.MEMBER_COUNT))
        delete_lb_vrid_subflow.add(
            a10_database_tasks.GetVRIDForLoadbalancerResource(
                requires=[
                    a10constants.PARTITION_PROJECT_LIST,
                    a10constants.VTHUNDER],
                provides=a10constants.VRID_LIST))
        delete_lb_vrid_subflow.add(
            a10_network_tasks.DeleteVRIDPort(
                requires=[
                    a10constants.VTHUNDER,
                    a10constants.VRID_LIST,
                    constants.SUBNET,
                    a10constants.USE_DEVICE_FLAVOR,
                    a10constants.LB_COUNT_SUBNET,
                    a10constants.MEMBER_COUNT,
                    a10constants.LB_COUNT_THUNDER,
                    a10constants.MEMBER_COUNT_THUNDER],
                rebind={a10constants.LB_RESOURCE: constants.LOADBALANCER},
                provides=(
                    a10constants.VRID,
                    a10constants.DELETE_VRID)))
        delete_lb_vrid_subflow.add(a10_database_tasks.DeleteVRIDEntry(
            requires=[a10constants.VRID, a10constants.DELETE_VRID]))

        if deleteCompute and topology == constants.TOPOLOGY_ACTIVE_STANDBY:
            delete_lb_vrid_subflow.add(a10_database_tasks.DeleteProjectSetIdDB(
                requires=constants.LOADBALANCER))

        return delete_lb_vrid_subflow

    def _get_cascade_delete_pools_listeners_flow(self, lb):
        """Sets up an internal delete flow
        Because task flow doesn't support loops we store each pool
        and listener we want to delete in the store part and then rebind
        :param lb: load balancer
        :return: (flow, store) -- flow for the deletion and store with all
                  the listeners/pools stored properly
        """
        pools_listeners_delete_flow = linear_flow.Flow('pool_listener_delete_flow')
        store = {}
        # loop for loadbalancer's l7policy deletion
        l7policy_delete_flow = None
        for listener in lb.listeners:
            l7policy_delete_flow = linear_flow.Flow('l7policy_delete_flow')
            for l7policy in listener.l7policies:
                l7policy_name = 'l7policy_' + l7policy.id
                store[l7policy_name] = l7policy
                l7policy_delete_flow.add(
                    self._l7policy_flows.get_cascade_delete_l7policy_internal_flow(l7policy_name))
        if l7policy_delete_flow:
            pools_listeners_delete_flow.add(l7policy_delete_flow)

        # loop for loadbalancer's pool deletion
        for pool in lb.pools:
            pool_name = 'pool' + pool.id
            members = pool.members
            store[pool_name] = pool
            listeners = pool.listeners
            default_listener = None
            pool_listener_name = 'pool_listener' + pool.id
            if listeners:
                default_listener = pool.listeners[0]
            store[pool_listener_name] = default_listener
            health_mon = None
            health_monitor = pool.health_monitor
            if health_monitor is not None:
                health_mon = 'health_mon' + health_monitor.id
                store[health_mon] = health_monitor
            (pool_delete, pool_store) = self._pool_flows.get_cascade_delete_pool_internal_flow(
                pool_name, members, pool_listener_name, health_mon)
            store.update(pool_store)
            pools_listeners_delete_flow.add(pool_delete)

        # loop for loadbalancer's listener deletion
        listeners_delete_flow = unordered_flow.Flow('listener_delete_flow')
        compute_flag = lb.amphorae
        for listener in lb.listeners:
            listener_name = 'listener_' + listener.id
            store[listener_name] = listener
            listeners_delete_flow.add(
                self._listener_flows.get_cascade_delete_listener_internal_flow(
                    listener_name, compute_flag))
        pools_listeners_delete_flow.add(listeners_delete_flow)
        return (pools_listeners_delete_flow, store)
