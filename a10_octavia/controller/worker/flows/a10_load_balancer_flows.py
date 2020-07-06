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

from a10_octavia.common import a10constants
from a10_octavia.controller.worker.flows import vthunder_flows
from a10_octavia.controller.worker.tasks import a10_compute_tasks
from a10_octavia.controller.worker.tasks import a10_database_tasks
from a10_octavia.controller.worker.tasks import a10_network_tasks
from a10_octavia.controller.worker.tasks import virtual_server_tasks
from a10_octavia.controller.worker.tasks import vthunder_tasks

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class LoadBalancerFlows(object):

    def __init__(self):
        self.amp_flows = amphora_flows.AmphoraFlows()
        self.listener_flows = listener_flows.ListenerFlows()
        self.pool_flows = pool_flows.PoolFlows()
        self.member_flows = member_flows.MemberFlows()
        self.vthunder_flows = vthunder_flows.VThunderFlows()

    def get_create_load_balancer_flow(self, topology, listeners=None):
        """Creates a conditional graph flow that allocates a loadbalancer to

        two spare amphorae.
        :raises InvalidTopology: Invalid topology specified
        :return: The graph flow for creating a loadbalancer.
        """
        f_name = constants.CREATE_LOADBALANCER_FLOW
        lb_create_flow = linear_flow.Flow(f_name)
        lb_create_flow.add(lifecycle_tasks.LoadBalancerIDToErrorOnRevertTask(
            requires=constants.LOADBALANCER_ID))

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
        lb_create_flow.add(
            self.get_post_lb_vthunder_association_flow(
                post_amp_prefix, topology, mark_active=(not listeners)))
        lb_create_flow.add(virtual_server_tasks.CreateVirtualServerTask(
            requires=(constants.LOADBALANCER,
                           a10constants.VTHUNDER)))

        return lb_create_flow

    def _create_single_topology(self):
        return (self.vthunder_flows.get_vthunder_for_lb_subflow(
            prefix=constants.ROLE_STANDALONE,
            role=constants.ROLE_STANDALONE), )

    # IMP: lets think about this later
    def _create_active_standby_topology(
            self, lf_name=constants.CREATE_LOADBALANCER_FLOW):
        # When we boot up amphora for an active/standby topology,
        # we should leverage the Nova anti-affinity capabilities
        # to place the amphora on different hosts, also we need to check
        # if anti-affinity-flag is enabled or not:
        anti_affinity = CONF.a10_nova.enable_anti_affinity
        flows = []
        if anti_affinity:
            # we need to create a server group first
            flows.append(
                a10_compute_tasks.NovaServerGroupCreate(
                    name=lf_name + '-' +
                    constants.CREATE_SERVER_GROUP_FLOW,
                    requires=(constants.LOADBALANCER_ID),
                    provides=constants.SERVER_GROUP_ID))

            # update server group id in lb table
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

    def get_post_lb_vthunder_association_flow(self, prefix, topology,
                                              mark_active=True):
        """Reload the loadbalancer and create networking subflows for

            created/allocated amphorae.
        :return: Post amphorae association subflow
        """

        sf_name = prefix + '-' + constants.POST_LB_AMP_ASSOCIATION_SUBFLOW
        post_create_lb_flow = linear_flow.Flow(sf_name)
        post_create_lb_flow.add(
            database_tasks.ReloadLoadBalancer(
                name=sf_name + '-' + constants.RELOAD_LB_AFTER_AMP_ASSOC,
                requires=constants.LOADBALANCER_ID,
                provides=constants.LOADBALANCER))
        # IMP: here we will inject network flow
        new_LB_net_subflow = self.get_new_lb_networking_subflow(topology)
        post_create_lb_flow.add(new_LB_net_subflow)

        if topology == constants.TOPOLOGY_ACTIVE_STANDBY:
            vrrp_subflow = self.vthunder_flows.get_vrrp_subflow(prefix)
            post_create_lb_flow.add(vrrp_subflow)

        post_create_lb_flow.add(database_tasks.UpdateLoadbalancerInDB(
            requires=[constants.LOADBALANCER, constants.UPDATE_DICT]))
        if mark_active:
            post_create_lb_flow.add(database_tasks.MarkLBActiveInDB(
                name=sf_name + '-' + constants.MARK_LB_ACTIVE_INDB,
                requires=constants.LOADBALANCER))
        return post_create_lb_flow

    def get_delete_load_balancer_flow(self, lb, deleteCompute):
        """Creates a flow to delete a load balancer.

        :returns: The flow for deleting a load balancer
        """
        store = {}
        delete_LB_flow = linear_flow.Flow(constants.DELETE_LOADBALANCER_FLOW)
        delete_LB_flow.add(lifecycle_tasks.LoadBalancerToErrorOnRevertTask(
            requires=constants.LOADBALANCER))
        delete_LB_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        delete_LB_flow.add(a10_database_tasks.MarkVThunderStatusInDB(
            name="set load balancer status PENDING_DELETE",
            requires=a10constants.VTHUNDER,
            inject={"status": constants.PENDING_DELETE}))
        delete_LB_flow.add(compute_tasks.NovaServerGroupDelete(
            requires=constants.SERVER_GROUP_ID))
        delete_LB_flow.add(database_tasks.MarkLBAmphoraeHealthBusy(
            requires=constants.LOADBALANCER))
        delete_LB_flow.add(virtual_server_tasks.DeleteVirtualServerTask(
            requires=(constants.LOADBALANCER, a10constants.VTHUNDER)))

        # delete_LB_flow.add(listeners_delete)
        # delete_LB_flow.add(network_tasks.UnplugVIP(
        #    requires=constants.LOADBALANCER))
        # delete_LB_flow.add(network_tasks.DeallocateVIP(
        #    requires=constants.LOADBALANCER))
        if deleteCompute:
            delete_LB_flow.add(compute_tasks.DeleteAmphoraeOnLoadBalancer(
                requires=constants.LOADBALANCER))
        delete_LB_flow.add(a10_database_tasks.MarkVThunderStatusInDB(
            name="DELETED",
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

        return (delete_LB_flow, store)

    def get_new_lb_networking_subflow(self, topology):
        """Create a sub-flow to setup networking.

        :returns: The flow to setup networking for a new amphora
        """
        new_LB_net_subflow = linear_flow.Flow(constants.
                                              LOADBALANCER_NETWORKING_SUBFLOW)
        new_LB_net_subflow.add(a10_network_tasks.PlugVIP(
            requires=constants.LOADBALANCER,
            provides=constants.AMPS_DATA))
        new_LB_net_subflow.add(a10_network_tasks.ApplyQos(
            requires=(constants.LOADBALANCER, constants.AMPS_DATA,
                      constants.UPDATE_DICT)))
        new_LB_net_subflow.add(database_tasks.UpdateAmphoraeVIPData(
            requires=constants.AMPS_DATA))
        new_LB_net_subflow.add(database_tasks.ReloadLoadBalancer(
            name=constants.RELOAD_LB_AFTER_PLUG_VIP,
            requires=constants.LOADBALANCER_ID,
            provides=constants.LOADBALANCER))
        new_LB_net_subflow.add(a10_network_tasks.GetAmphoraeNetworkConfigs(
            requires=constants.LOADBALANCER,
            provides=constants.AMPHORAE_NETWORK_CONFIG))
        new_LB_net_subflow.add(database_tasks.GetAmphoraeFromLoadbalancer(
            requires=constants.LOADBALANCER,
            provides=constants.AMPHORA))
        new_LB_net_subflow.add(
            vthunder_tasks.VThunderComputeConnectivityWait(
                name=a10constants.MASTER_CONNECTIVITY_WAIT,
                requires=(a10constants.VTHUNDER, constants.AMPHORA)))
        new_LB_net_subflow.add(vthunder_tasks.EnableInterface(
            requires=a10constants.VTHUNDER))
        new_LB_net_subflow.add(a10_database_tasks.MarkVThunderStatusInDB(
            name=a10constants.MARK_VTHUNDER_MASTER_ACTIVE_IN_DB,
            requires=a10constants.VTHUNDER,
            inject={a10constants.STATUS: constants.ACTIVE}))
        if topology == constants.TOPOLOGY_ACTIVE_STANDBY:
            new_LB_net_subflow.add(vthunder_tasks.CreateHealthMonitorOnVThunder(
                name=a10constants.CREATE_HEALTH_MONITOR_ON_VTHUNDER_MASTER,
                requires=a10constants.VTHUNDER))
            new_LB_net_subflow.add(a10_database_tasks.GetBackupVThunderByLoadBalancer(
                name=a10constants.GET_BACKUP_VTHUNDER_BY_LB,
                requires=constants.LOADBALANCER,
                provides=a10constants.BACKUP_VTHUNDER))
            new_LB_net_subflow.add(vthunder_tasks.VThunderComputeConnectivityWait(
                name=a10constants.BACKUP_CONNECTIVITY_WAIT,
                rebind={a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER},
                requires=constants.AMPHORA))
            new_LB_net_subflow.add(vthunder_tasks.EnableInterface(
                name=a10constants.BACKUP_ENABLE_INTERFACE,
                rebind={a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER}))
            new_LB_net_subflow.add(a10_database_tasks.MarkVThunderStatusInDB(
                name=a10constants.MARK_VTHUNDER_BACKUP_ACTIVE_IN_DB,
                rebind={a10constants.VTHUNDER: a10constants.BACKUP_VTHUNDER},
                inject={a10constants.STATUS: constants.ACTIVE}))
        return new_LB_net_subflow

    def get_update_load_balancer_flow(self):
        """Creates a flow to update a load balancer.
        :returns: The flow for update a load balancer
        """
        update_LB_flow = linear_flow.Flow(constants.UPDATE_LOADBALANCER_FLOW)
        update_LB_flow.add(lifecycle_tasks.LoadBalancerToErrorOnRevertTask(
            requires=constants.LOADBALANCER))
        update_LB_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        update_LB_flow.add(a10_database_tasks.MarkVThunderStatusInDB(
            name="set load balancer status PENDING_UPDATE",
            requires=a10constants.VTHUNDER,
            inject={"status": constants.PENDING_UPDATE}))
        update_LB_flow.add(network_tasks.ApplyQos(
            requires=(constants.LOADBALANCER, constants.UPDATE_DICT)))
        # update_LB_flow.add(amphora_driver_tasks.ListenersUpdate(
        #    requires=[constants.LOADBALANCER, constants.LISTENERS]))
        update_LB_flow.add(virtual_server_tasks.UpdateVirtualServerTask(
            requires=(constants.LOADBALANCER, a10constants.VTHUNDER)))
        update_LB_flow.add(database_tasks.UpdateLoadbalancerInDB(
            requires=[constants.LOADBALANCER, constants.UPDATE_DICT]))
        update_LB_flow.add(database_tasks.MarkLBActiveInDB(
            requires=constants.LOADBALANCER))
        return update_LB_flow

    def get_create_rack_vthunder_load_balancer_flow(self, vthunder_conf, topology, listeners=None):
        """Creates a linear flow to create rack vthunder

        :return: The linear flow for creating a loadbalancer.
        """
        f_name = constants.CREATE_LOADBALANCER_FLOW
        lb_create_flow = linear_flow.Flow(f_name)

        lb_create_flow.add(lifecycle_tasks.LoadBalancerIDToErrorOnRevertTask(
            requires=constants.LOADBALANCER_ID))

        lb_create_flow.add(self.vthunder_flows.get_rack_vthunder_for_lb_subflow(
            vthunder_conf=vthunder_conf,
            prefix=constants.ROLE_STANDALONE,
            role=constants.ROLE_STANDALONE))
        post_amp_prefix = constants.POST_LB_AMP_ASSOCIATION_SUBFLOW
        lb_create_flow.add(
            self.get_post_lb_rack_vthunder_association_flow(
                post_amp_prefix, topology, mark_active=(not listeners)))

        lb_create_flow.add(virtual_server_tasks.CreateVirtualServerTask(
            requires=(constants.LOADBALANCER, a10constants.VTHUNDER),
            provides=a10constants.STATUS))

        return lb_create_flow

    def get_post_lb_rack_vthunder_association_flow(self, prefix, topology,
                                                   mark_active=True):
        """Reload the loadbalancer and update loadbalancer in database."""

        sf_name = prefix + '-' + constants.POST_LB_AMP_ASSOCIATION_SUBFLOW
        post_create_lb_flow = linear_flow.Flow(sf_name)
        post_create_lb_flow.add(
            database_tasks.ReloadLoadBalancer(
                name=sf_name + '-' + constants.RELOAD_LB_AFTER_AMP_ASSOC,
                requires=constants.LOADBALANCER_ID,
                provides=constants.LOADBALANCER))

        post_create_lb_flow.add(database_tasks.UpdateLoadbalancerInDB(
            requires=[constants.LOADBALANCER, constants.UPDATE_DICT]))
        if mark_active:
            post_create_lb_flow.add(database_tasks.MarkLBActiveInDB(
                name=sf_name + '-' + constants.MARK_LB_ACTIVE_INDB,
                requires=constants.LOADBALANCER))
        return post_create_lb_flow
