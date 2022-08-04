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


from taskflow.patterns import graph_flow
from taskflow.patterns import linear_flow

from octavia.common import constants
from octavia.controller.worker.v1.tasks import database_tasks
from octavia.controller.worker.v1.tasks import lifecycle_tasks
from octavia.controller.worker.v1.tasks import network_tasks

from a10_octavia.common import a10constants
from a10_octavia.controller.worker.flows import a10_l7policy_flows
from a10_octavia.controller.worker.tasks import a10_database_tasks
from a10_octavia.controller.worker.tasks import a10_network_tasks
from a10_octavia.controller.worker.tasks import cert_tasks
from a10_octavia.controller.worker.tasks import nat_pool_tasks
from a10_octavia.controller.worker.tasks import virtual_port_tasks
from a10_octavia.controller.worker.tasks import vthunder_tasks


class ListenerFlows(object):

    def __init__(self):
        self._l7policy_flows = a10_l7policy_flows.L7PolicyFlows()

    def get_create_listener_flow(self, topology):
        """Flow to create a listener"""

        create_listener_flow = linear_flow.Flow(constants.CREATE_LISTENER_FLOW)
        create_listener_flow.add(lifecycle_tasks.ListenerToErrorOnRevertTask(
            requires=[constants.LISTENER]))
        create_listener_flow.add(vthunder_tasks.VthunderInstanceBusy(
            requires=a10constants.COMPUTE_BUSY))
        create_listener_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        if topology == constants.TOPOLOGY_ACTIVE_STANDBY:
            create_listener_flow.add(vthunder_tasks.GetMasterVThunder(
                name=a10constants.GET_MASTER_VTHUNDER,
                requires=a10constants.VTHUNDER,
                provides=a10constants.VTHUNDER))
        create_listener_flow.add(self.handle_ssl_cert_flow(flow_type='create'))
        create_listener_flow.add(a10_database_tasks.GetFlavorData(
            rebind={a10constants.LB_RESOURCE: constants.LISTENER},
            provides=constants.FLAVOR_DATA))
        create_listener_flow.add(nat_pool_tasks.NatPoolCreate(
            requires=(constants.LOADBALANCER,
                      a10constants.VTHUNDER, constants.FLAVOR_DATA)))
        create_listener_flow.add(virtual_port_tasks.ListenerCreate(
            requires=[constants.LOADBALANCER, constants.LISTENER,
                      a10constants.VTHUNDER, constants.FLAVOR_DATA]))
        create_listener_flow.add(a10_network_tasks.UpdateVIP(
            requires=constants.LOADBALANCER))
        create_listener_flow.add(a10_database_tasks.
                                 MarkLBAndListenerActiveInDB(
                                     requires=[constants.LOADBALANCER,
                                               constants.LISTENER]))
        create_listener_flow.add(vthunder_tasks.WriteMemory(
            requires=a10constants.VTHUNDER))
        create_listener_flow.add(a10_database_tasks.SetThunderUpdatedAt(
            requires=a10constants.VTHUNDER))
        return create_listener_flow

    def get_vthunder_fully_populated_create_listener_flow(self, topology, listener):
        """Flow to create fully populated loadbalancer listeners"""

        sf_name = constants.CREATE_LISTENER_FLOW + '_' + listener.id
        create_listener_flow = linear_flow.Flow(sf_name)
        create_listener_flow.add(lifecycle_tasks.ListenerToErrorOnRevertTask(
            name=sf_name + a10constants.FULLY_POPULATED_ERROR_ON_REVERT,
            requires=[constants.LISTENER],
            inject={constants.LISTENER: listener}))
        create_listener_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            name=sf_name + '-' + a10constants.GET_VTHUNDER_BY_LB,
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        if topology == constants.TOPOLOGY_ACTIVE_STANDBY:
            create_listener_flow.add(vthunder_tasks.GetMasterVThunder(
                name=sf_name + a10constants.GET_MASTER_VTHUNDER,
                requires=a10constants.VTHUNDER,
                provides=a10constants.VTHUNDER))
        create_listener_flow.add(self.handle_ssl_cert_flow(flow_type='create', listener=listener))
        create_listener_flow.add(a10_database_tasks.GetFlavorData(
            name=sf_name + a10constants.FULLY_POPULATED_GET_FLAVOR,
            rebind={a10constants.LB_RESOURCE: constants.LISTENER},
            inject={constants.LISTENER: listener},
            provides=constants.FLAVOR_DATA))
        create_listener_flow.add(nat_pool_tasks.NatPoolCreate(
            name=sf_name + a10constants.FULLY_POPULATED_NAT_CREATE,
            requires=(constants.LOADBALANCER,
                      a10constants.VTHUNDER, constants.FLAVOR_DATA)))
        create_listener_flow.add(virtual_port_tasks.ListenerCreate(
            name=sf_name + a10constants.FULLY_POPULATED_CREATE_LISTENER,
            requires=[constants.LOADBALANCER, constants.LISTENER,
                      a10constants.VTHUNDER, constants.FLAVOR_DATA],
            inject={constants.LISTENER: listener}))
        create_listener_flow.add(a10_network_tasks.UpdateVIP(
            name=sf_name + a10constants.UPDATE_VIP_AFTER_ALLOCATION,
            requires=constants.LOADBALANCER))

        for l7policy in listener.l7policies:
            create_listener_flow.add(
                self._l7policy_flows.get_fully_populated_create_l7policy_flow(
                    topology, listener, l7policy))

        create_listener_flow.add(a10_database_tasks.MarkLBAndListenerActiveInDB(
            name=sf_name + a10constants.FULLY_POPULATED_MARK_LISTENER_ACTIVE,
            requires=[constants.LOADBALANCER,
                      constants.LISTENER],
            inject={constants.LISTENER: listener}))
        return create_listener_flow

    def handle_ssl_cert_flow(self, flow_type='create', listener=None):
        if flow_type == 'create':
            configure_ssl = self.get_ssl_certificate_create_flow(listener)
        elif flow_type == 'update':
            configure_ssl = self.get_ssl_certificate_update_flow(listener)
        else:
            configure_ssl = self.get_ssl_certificate_delete_flow(listener)

        configure_ssl_flow = graph_flow.Flow(
            a10constants.LISTENER_TYPE_DECIDER_FLOW)

        if listener is not None:
            check_ssl = cert_tasks.CheckListenerType(
                name='check_listener_type_' + listener.id,
                requires=constants.LISTENER,
                inject={constants.LISTENER: listener})
        else:
            check_ssl = cert_tasks.CheckListenerType(
                requires=constants.LISTENER)
        configure_ssl_flow.add(check_ssl, configure_ssl)
        configure_ssl_flow.link(check_ssl, configure_ssl,
                                decider=self._check_ssl_data, decider_depth='flow')
        return configure_ssl_flow

    def _check_ssl_data(self, history):
        return list(history.values())[0]

    def get_delete_listener_flow(self, topology):
        """Flow to delete a listener"""

        delete_listener_flow = linear_flow.Flow(constants.DELETE_LISTENER_FLOW)
        delete_listener_flow.add(lifecycle_tasks.ListenerToErrorOnRevertTask(
            requires=constants.LISTENER))
        delete_listener_flow.add(vthunder_tasks.VthunderInstanceBusy(
            requires=a10constants.COMPUTE_BUSY))
        delete_listener_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        if topology == constants.TOPOLOGY_ACTIVE_STANDBY:
            delete_listener_flow.add(vthunder_tasks.GetMasterVThunder(
                name=a10constants.GET_MASTER_VTHUNDER,
                requires=a10constants.VTHUNDER,
                provides=a10constants.VTHUNDER))
        delete_listener_flow.add(self.handle_ssl_cert_flow(flow_type='delete'))
        delete_listener_flow.add(virtual_port_tasks.ListenerDelete(
            requires=[constants.LOADBALANCER, constants.LISTENER, a10constants.VTHUNDER]))
        delete_listener_flow.add(network_tasks.UpdateVIPForDelete(
            requires=constants.LOADBALANCER))
        delete_listener_flow.add(database_tasks.DeleteListenerInDB(
            requires=constants.LISTENER))
        delete_listener_flow.add(database_tasks.DecrementListenerQuota(
            requires=constants.LISTENER))
        delete_listener_flow.add(database_tasks.MarkLBActiveInDB(
            requires=constants.LOADBALANCER))
        delete_listener_flow.add(vthunder_tasks.WriteMemory(
            requires=a10constants.VTHUNDER))
        delete_listener_flow.add(a10_database_tasks.SetThunderUpdatedAt(
            requires=a10constants.VTHUNDER))
        return delete_listener_flow

    def get_cascade_delete_listener_internal_flow(self, listener, listener_name):
        """Create a flow to delete a listener
           (will skip deletion on the amp and marking LB active)
        :returns: The flow for deleting a listener
        """
        delete_listener_flow = linear_flow.Flow(constants.DELETE_LISTENER_FLOW)
        delete_listener_flow.add(self.handle_ssl_cert_flow(
            flow_type='delete', listener=listener))
        delete_listener_flow.add(database_tasks.DeleteListenerInDB(
            name='delete_listener_in_db_' + listener_name,
            requires=constants.LISTENER,
            rebind={constants.LISTENER: listener_name}))
        delete_listener_flow.add(database_tasks.DecrementListenerQuota(
            name='decrement_listener_quota_' + listener_name,
            requires=constants.LISTENER,
            rebind={constants.LISTENER: listener_name}))
        return delete_listener_flow

    def get_delete_rack_listener_flow(self):
        """Flow to delete a rack listener """

        delete_listener_flow = linear_flow.Flow(constants.DELETE_LISTENER_FLOW)
        delete_listener_flow.add(lifecycle_tasks.ListenerToErrorOnRevertTask(
            requires=constants.LISTENER))
        delete_listener_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        delete_listener_flow.add(self.handle_ssl_cert_flow(flow_type='delete'))
        delete_listener_flow.add(virtual_port_tasks.ListenerDelete(
            requires=[constants.LOADBALANCER, constants.LISTENER, a10constants.VTHUNDER]))
        delete_listener_flow.add(database_tasks.DeleteListenerInDB(
            requires=constants.LISTENER))
        delete_listener_flow.add(database_tasks.DecrementListenerQuota(
            requires=constants.LISTENER))
        delete_listener_flow.add(database_tasks.MarkLBActiveInDB(
            requires=constants.LOADBALANCER))
        delete_listener_flow.add(vthunder_tasks.WriteMemory(
            requires=a10constants.VTHUNDER))
        delete_listener_flow.add(a10_database_tasks.SetThunderUpdatedAt(
            requires=a10constants.VTHUNDER))
        return delete_listener_flow

    def get_update_listener_flow(self, topology):
        """Flow to update a listener"""

        update_listener_flow = linear_flow.Flow(constants.UPDATE_LISTENER_FLOW)
        update_listener_flow.add(lifecycle_tasks.ListenerToErrorOnRevertTask(
            requires=[constants.LISTENER]))
        update_listener_flow.add(vthunder_tasks.VthunderInstanceBusy(
            requires=a10constants.COMPUTE_BUSY))
        update_listener_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        if topology == constants.TOPOLOGY_ACTIVE_STANDBY:
            update_listener_flow.add(vthunder_tasks.GetMasterVThunder(
                name=a10constants.GET_MASTER_VTHUNDER,
                requires=a10constants.VTHUNDER,
                provides=a10constants.VTHUNDER))
        update_listener_flow.add(self.handle_ssl_cert_flow(flow_type='update'))
        update_listener_flow.add(a10_database_tasks.GetFlavorData(
            rebind={a10constants.LB_RESOURCE: constants.LISTENER},
            provides=constants.FLAVOR_DATA))
        update_listener_flow.add(virtual_port_tasks.ListenerUpdate(
            requires=[constants.LOADBALANCER, constants.LISTENER,
                      a10constants.VTHUNDER, constants.FLAVOR_DATA, constants.UPDATE_DICT]))
        update_listener_flow.add(database_tasks.UpdateListenerInDB(
            requires=[constants.LISTENER, constants.UPDATE_DICT]))
        update_listener_flow.add(a10_database_tasks.
                                 MarkLBAndListenerActiveInDB(
                                     requires=[constants.LOADBALANCER,
                                               constants.LISTENER]))
        update_listener_flow.add(vthunder_tasks.WriteMemory(
            requires=a10constants.VTHUNDER))
        update_listener_flow.add(a10_database_tasks.SetThunderUpdatedAt(
            requires=a10constants.VTHUNDER))
        return update_listener_flow

    def get_rack_vthunder_create_listener_flow(self, project_id):
        """Create a flow to create a rack listener"""

        create_listener_flow = linear_flow.Flow(constants.CREATE_LISTENER_FLOW)
        create_listener_flow.add(lifecycle_tasks.ListenerToErrorOnRevertTask(
            requires=[constants.LISTENER]))
        create_listener_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        create_listener_flow.add(self.handle_ssl_cert_flow(flow_type='create'))
        create_listener_flow.add(a10_database_tasks.GetFlavorData(
            rebind={a10constants.LB_RESOURCE: constants.LISTENER},
            provides=constants.FLAVOR_DATA))
        create_listener_flow.add(nat_pool_tasks.NatPoolCreate(
            requires=(constants.LOADBALANCER,
                      a10constants.VTHUNDER, constants.FLAVOR_DATA)))
        create_listener_flow.add(virtual_port_tasks.ListenerCreate(
            requires=[constants.LOADBALANCER, constants.LISTENER,
                      a10constants.VTHUNDER, constants.FLAVOR_DATA]))
        create_listener_flow.add(a10_database_tasks.
                                 MarkLBAndListenerActiveInDB(
                                     requires=[constants.LOADBALANCER,
                                               constants.LISTENER]))
        create_listener_flow.add(vthunder_tasks.WriteMemory(
            requires=a10constants.VTHUNDER))
        create_listener_flow.add(a10_database_tasks.SetThunderUpdatedAt(
            requires=a10constants.VTHUNDER))
        return create_listener_flow

    def get_rack_fully_populated_create_listener_flow(self, topology, listener):
        """Create a flow to create listener for fully populated loadbalancer creation"""

        sf_name = constants.CREATE_LISTENER_FLOW + '_' + listener.id
        create_listener_flow = linear_flow.Flow(sf_name)
        create_listener_flow.add(lifecycle_tasks.ListenerToErrorOnRevertTask(
            name=sf_name + a10constants.FULLY_POPULATED_ERROR_ON_REVERT,
            requires=[constants.LISTENER],
            inject={constants.LISTENER: listener}))

        create_listener_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            name=sf_name + '-' + a10constants.GET_VTHUNDER_BY_LB,
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        create_listener_flow.add(self.handle_ssl_cert_flow(flow_type='create', listener=listener))
        create_listener_flow.add(a10_database_tasks.GetFlavorData(
            name=sf_name + a10constants.FULLY_POPULATED_GET_FLAVOR,
            rebind={a10constants.LB_RESOURCE: constants.LISTENER},
            inject={constants.LISTENER: listener},
            provides=constants.FLAVOR_DATA))
        create_listener_flow.add(nat_pool_tasks.NatPoolCreate(
            name=sf_name + a10constants.FULLY_POPULATED_NAT_CREATE,
            requires=(constants.LOADBALANCER,
                      a10constants.VTHUNDER, constants.FLAVOR_DATA)))
        create_listener_flow.add(virtual_port_tasks.ListenerCreate(
            name=sf_name + a10constants.FULLY_POPULATED_CREATE_LISTENER,
            requires=[constants.LOADBALANCER, constants.LISTENER,
                      a10constants.VTHUNDER, constants.FLAVOR_DATA],
            inject={constants.LISTENER: listener}))

        for l7policy in listener.l7policies:
            create_listener_flow.add(
                self._l7policy_flows.get_fully_populated_create_l7policy_flow(
                    topology, listener, l7policy))

        create_listener_flow.add(a10_database_tasks.MarkLBAndListenerActiveInDB(
            name=sf_name + a10constants.FULLY_POPULATED_MARK_LISTENER_ACTIVE,
            requires=[constants.LOADBALANCER, constants.LISTENER],
            inject={constants.LISTENER: listener}))
        return create_listener_flow

    def get_ssl_certificate_create_flow(self, listener=None):
        suffix = 'listener'
        if listener is not None:
            suffix = 'listener_' + listener.id

        create_ssl_cert_flow = linear_flow.Flow(
            a10constants.CREATE_SSL_CERT_FLOW + suffix)
        if listener is not None:
            create_ssl_cert_flow.add(cert_tasks.GetSSLCertData(
                name='get_ssl_cert_data_' + suffix,
                requires=[constants.LOADBALANCER, constants.LISTENER],
                inject={constants.LISTENER: listener},
                provides=a10constants.CERT_DATA))
        else:
            create_ssl_cert_flow.add(cert_tasks.GetSSLCertData(
                requires=[constants.LOADBALANCER, constants.LISTENER],
                provides=a10constants.CERT_DATA))
        create_ssl_cert_flow.add(cert_tasks.SSLCertCreate(
            name='ssl_cert_create_' + suffix,
            requires=[a10constants.CERT_DATA, a10constants.VTHUNDER]))
        create_ssl_cert_flow.add(cert_tasks.SSLKeyCreate(
            name='ssl_key_create_' + suffix,
            requires=[a10constants.CERT_DATA, a10constants.VTHUNDER]))
        create_ssl_cert_flow.add(cert_tasks.ClientSSLTemplateCreate(
            name='client_ssl_template_create_' + suffix,
            requires=[a10constants.CERT_DATA, a10constants.VTHUNDER]))
        return create_ssl_cert_flow

    def get_ssl_certificate_delete_flow(self, listener=None):
        suffix = 'listener'
        if listener is not None:
            suffix = 'listener_' + listener.id

        delete_ssl_cert_flow = linear_flow.Flow(
            a10constants.DELETE_SSL_CERT_FLOW)
        if listener is not None:
            delete_ssl_cert_flow.add(cert_tasks.GetSSLCertData(
                name='get_ssl_cert_data_' + suffix,
                requires=[constants.LOADBALANCER, constants.LISTENER],
                inject={constants.LISTENER: listener},
                provides=a10constants.CERT_DATA))
        else:
            delete_ssl_cert_flow.add(cert_tasks.GetSSLCertData(
                name='get_ssl_cert_data_' + suffix,
                requires=[constants.LOADBALANCER, constants.LISTENER],
                provides=a10constants.CERT_DATA))
        delete_ssl_cert_flow.add(cert_tasks.ClientSSLTemplateDelete(
            name='client_ssl_template_delete_' + suffix,
            requires=[a10constants.CERT_DATA, a10constants.VTHUNDER]))
        delete_ssl_cert_flow.add(cert_tasks.SSLCertDelete(
            name='ssl_cert_delete_' + suffix,
            requires=[a10constants.CERT_DATA, a10constants.VTHUNDER]))
        delete_ssl_cert_flow.add(cert_tasks.SSLKeyDelete(
            name='ssl_key_delete_' + suffix,
            requires=[a10constants.CERT_DATA, a10constants.VTHUNDER]))
        return delete_ssl_cert_flow

    def get_ssl_certificate_update_flow(self, listener=None):
        suffix = 'listener'
        if listener is not None:
            suffix = 'listener_' + listener.id

        update_ssl_cert_flow = linear_flow.Flow(
            a10constants.DELETE_SSL_CERT_FLOW + suffix)
        if listener is not None:
            update_ssl_cert_flow.add(cert_tasks.GetSSLCertData(
                name='get_ssl_cert_data_' + suffix,
                requires=[constants.LOADBALANCER, constants.LISTENER],
                inject={constants.LISTENER: listener},
                provides=a10constants.CERT_DATA))
        else:
            update_ssl_cert_flow.add(cert_tasks.GetSSLCertData(
                requires=[constants.LOADBALANCER, constants.LISTENER],
                provides=a10constants.CERT_DATA))
        update_ssl_cert_flow.add(cert_tasks.SSLCertUpdate(
            name='ssl_cert_update_' + suffix,
            requires=[a10constants.CERT_DATA, a10constants.VTHUNDER]))
        update_ssl_cert_flow.add(cert_tasks.SSLKeyUpdate(
            name='ssl_key_update_' + suffix,
            requires=[a10constants.CERT_DATA, a10constants.VTHUNDER]))
        update_ssl_cert_flow.add(cert_tasks.ClientSSLTemplateUpdate(
            name='client_ssl_template_update_' + suffix,
            requires=[a10constants.CERT_DATA, a10constants.VTHUNDER]))
        return update_ssl_cert_flow

    def get_listener_stats_flow(self, vthunder, store):
        """Perform Listener Statistics update """

        sf_name = 'a10-health-monitor' + '-' + a10constants.UPDATE_LISTENER_STATS_FLOW

        listener_stats_flow = linear_flow.Flow(sf_name)
        vthunder_store = {}
        vthunder_store[vthunder] = vthunder
        listener_stats_flow.add(vthunder_tasks.GetListenersStats(
            name='{flow}-{id}'.format(
                id=vthunder.vthunder_id,
                flow='GetListenersStats'),
            requires=(a10constants.VTHUNDER),
            rebind={a10constants.VTHUNDER: vthunder},
            provides=a10constants.LISTENER_STATS))
        listener_stats_flow.add(a10_database_tasks.UpdateListenersStats(
            name='{flow}-{id}'.format(
                id=vthunder.vthunder_id,
                flow='UpdateListenersStats'),
            requires=a10constants.LISTENER_STATS))

        store.update(vthunder_store)
        return listener_stats_flow
