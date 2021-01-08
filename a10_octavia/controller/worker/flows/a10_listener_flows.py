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
from octavia.controller.worker.tasks import database_tasks
from octavia.controller.worker.tasks import lifecycle_tasks
from octavia.controller.worker.tasks import network_tasks

from a10_octavia.common import a10constants
from a10_octavia.controller.worker.tasks import a10_database_tasks
from a10_octavia.controller.worker.tasks import a10_network_tasks
from a10_octavia.controller.worker.tasks import cert_tasks
from a10_octavia.controller.worker.tasks import nat_pool_tasks
from a10_octavia.controller.worker.tasks import virtual_port_tasks
from a10_octavia.controller.worker.tasks import vthunder_tasks


class ListenerFlows(object):

    def get_create_listener_flow(self):
        """Flow to create a listener"""

        create_listener_flow = linear_flow.Flow(constants.CREATE_LISTENER_FLOW)
        create_listener_flow.add(lifecycle_tasks.ListenerToErrorOnRevertTask(
            requires=[constants.LISTENER]))
        create_listener_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        create_listener_flow.add(self.handle_ssl_cert_flow(flow_type='create'))
        create_listener_flow.add(virtual_port_tasks.ListenerCreate(
            requires=[constants.LOADBALANCER, constants.LISTENER, a10constants.VTHUNDER]))
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

    def handle_ssl_cert_flow(self, flow_type='create'):
        if flow_type == 'create':
            configure_ssl = self.get_ssl_certificate_create_flow()
        elif flow_type == 'update':
            configure_ssl = self.get_ssl_certificate_update_flow()
        else:
            configure_ssl = self.get_ssl_certificate_delete_flow()

        configure_ssl_flow = graph_flow.Flow(
            a10constants.LISTENER_TYPE_DECIDER_FLOW)
        check_ssl = cert_tasks.CheckListenerType(requires=constants.LISTENER)
        configure_ssl_flow.add(check_ssl, configure_ssl)
        configure_ssl_flow.link(check_ssl, configure_ssl,
                                decider=self._check_ssl_data, decider_depth='flow')
        return configure_ssl_flow

    def _check_ssl_data(self, history):
        return list(history.values())[0]

    def get_delete_listener_flow(self):
        """Flow to delete a listener"""

        delete_listener_flow = linear_flow.Flow(constants.DELETE_LISTENER_FLOW)
        delete_listener_flow.add(lifecycle_tasks.ListenerToErrorOnRevertTask(
            requires=constants.LISTENER))
        delete_listener_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            requires=constants.LOADBALANCER,
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

    def get_update_listener_flow(self):
        """Flow to update a listener"""

        update_listener_flow = linear_flow.Flow(constants.UPDATE_LISTENER_FLOW)
        update_listener_flow.add(lifecycle_tasks.ListenerToErrorOnRevertTask(
            requires=[constants.LISTENER]))
        update_listener_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            requires=constants.LOADBALANCER,
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

    def get_ssl_certificate_create_flow(self):
        create_ssl_cert_flow = linear_flow.Flow(
            a10constants.CREATE_SSL_CERT_FLOW)
        create_ssl_cert_flow.add(cert_tasks.GetSSLCertData(
            requires=[constants.LOADBALANCER, constants.LISTENER],
            provides=a10constants.CERT_DATA))
        create_ssl_cert_flow.add(cert_tasks.SSLCertCreate(
            requires=[a10constants.CERT_DATA, a10constants.VTHUNDER]))
        create_ssl_cert_flow.add(cert_tasks.SSLKeyCreate(
            requires=[a10constants.CERT_DATA, a10constants.VTHUNDER]))
        create_ssl_cert_flow.add(cert_tasks.ClientSSLTemplateCreate(
            requires=[a10constants.CERT_DATA, a10constants.VTHUNDER]))
        return create_ssl_cert_flow

    def get_ssl_certificate_delete_flow(self):
        delete_ssl_cert_flow = linear_flow.Flow(
            a10constants.DELETE_SSL_CERT_FLOW)
        delete_ssl_cert_flow.add(cert_tasks.GetSSLCertData(
            requires=[constants.LOADBALANCER, constants.LISTENER],
            provides=a10constants.CERT_DATA))
        delete_ssl_cert_flow.add(cert_tasks.ClientSSLTemplateDelete(
            requires=[a10constants.CERT_DATA, a10constants.VTHUNDER]))
        delete_ssl_cert_flow.add(cert_tasks.SSLCertDelete(
            requires=[a10constants.CERT_DATA, a10constants.VTHUNDER]))
        delete_ssl_cert_flow.add(cert_tasks.SSLKeyDelete(
            requires=[a10constants.CERT_DATA, a10constants.VTHUNDER]))
        return delete_ssl_cert_flow

    def get_ssl_certificate_update_flow(self):
        update_ssl_cert_flow = linear_flow.Flow(
            a10constants.DELETE_SSL_CERT_FLOW)
        update_ssl_cert_flow.add(cert_tasks.GetSSLCertData(
            requires=[constants.LOADBALANCER, constants.LISTENER],
            provides=a10constants.CERT_DATA))
        update_ssl_cert_flow.add(cert_tasks.SSLCertUpdate(
            requires=[a10constants.CERT_DATA, a10constants.VTHUNDER]))
        update_ssl_cert_flow.add(cert_tasks.SSLKeyUpdate(
            requires=[a10constants.CERT_DATA, a10constants.VTHUNDER]))
        update_ssl_cert_flow.add(cert_tasks.ClientSSLTemplateUpdate(
            requires=[a10constants.CERT_DATA, a10constants.VTHUNDER]))
        return update_ssl_cert_flow
