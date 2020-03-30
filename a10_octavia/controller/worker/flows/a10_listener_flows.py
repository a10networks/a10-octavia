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

from taskflow.patterns import graph_flow, linear_flow

from octavia.common import constants
from octavia.controller.worker.tasks import database_tasks
from octavia.controller.worker.tasks import lifecycle_tasks
from octavia.controller.worker.tasks import network_tasks

from a10_octavia.common import a10constants
from a10_octavia.controller.worker.tasks import a10_database_tasks
from a10_octavia.controller.worker.tasks import a10_network_tasks
from a10_octavia.controller.worker.tasks import cert_tasks
from a10_octavia.controller.worker.tasks import virtual_port_tasks


class ListenerFlows(object):

    def get_create_listener_flow(self):
        """Create a flow to create a listener

        :returns: The flow for creating a listener
        """
        create_listener_flow = linear_flow.Flow(constants.CREATE_LISTENER_FLOW)
        create_listener_flow.add(*self._get_create_listener_subflow())
        create_listener_flow.add(a10_network_tasks.UpdateVIP(
            requires=constants.LOADBALANCER))
        create_listener_flow.add(a10_database_tasks.
                                 MarkLBAndListenerActiveInDB(
                                     requires=[constants.LOADBALANCER,
                                               constants.LISTENER]))
        return create_listener_flow

    def _get_create_listener_subflow(self):
        create_listener_flow = linear_flow.Flow(a10constants.CREATE_LISTENER_SUBFLOW)
        create_listener_flow.add(lifecycle_tasks.ListenerToErrorOnRevertTask(
            requires=constants.LISTENER))
        create_listener_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        create_listener_flow.add(*self.get_listener_create_cert_template_subflow())
        create_listener_flow.add(virtual_port_tasks.ListenerCreate(
            requires=[constants.LOADBALANCER, constants.LISTENER, a10constants.VTHUNDER]))
        return create_listener_flow

    def _get_cert_create_subflow(self):
        get_create_cert_subflow = linear_flow.Flow(a10constants.CREATE_CERT_TEMPLATE_SUBFLOW)
        get_create_cert_subflow.add(cert_tasks.SSLKeyCreate(
            requires=(a10constants.CERT_DATA, a10constants.VTHUNDER)))
        get_create_cert_subflow.add(cert_tasks.ClientSSLTemplateCreate(
            requires=(a10constants.CERT_DATA, a10constants.VTHUNDER)))
        return get_create_cert_subflow

    def get_listener_create_cert_template_subflow(self):
        get_listener_create_cert_subflow = graph_flow.Flow(
            a10constants.CREATE_LISTENER_CERT_SUBFLOW)
        cert_create_task = cert_tasks.SSLCertCreate(
            requires=[constants.LOADBALANCER, constants.LISTENER, a10constants.VTHUNDER],
            provides=a10constants.CERT_DATA)
        cert_create_template_task = self._get_cert_create_subflow()
        get_listener_create_cert_subflow.add(cert_create_task, cert_create_template_task)
        get_listener_create_cert_subflow.link(
            cert_create_task, cert_create_template_task, decider=self._is_terminated_https)
        return get_listener_create_cert_subflow

    def _is_terminated_https(self, history):
        """Decides if the protocol is TERMINATED_HTTPS
        :returns: True if if protocol is TERMINATED_HTTPS
        """
        if history.values()[0]:
            return True
        else:
            return False

    def get_create_all_listeners_flow(self):
        """Create a flow to create all listeners

        :returns: The flow for creating all listeners
        """
        create_all_listeners_flow = linear_flow.Flow(
            constants.CREATE_LISTENERS_FLOW)
        create_all_listeners_flow.add(
            database_tasks.GetListenersFromLoadbalancer(
                requires=constants.LOADBALANCER,
                provides=constants.LISTENERS))
        create_all_listeners_flow.add(database_tasks.ReloadLoadBalancer(
            requires=constants.LOADBALANCER_ID,
            provides=constants.LOADBALANCER))
        create_all_listeners_flow.add(virtual_port_tasks.ListenerUpdate(
            requires=[constants.LOADBALANCER, constants.LISTENER]))
        create_all_listeners_flow.add(network_tasks.UpdateVIP(
            requires=constants.LOADBALANCER))
        return create_all_listeners_flow

    def get_delete_listener_flow(self):
        """Create a flow to delete a listener

        :returns: The flow for deleting a listener
        """
        delete_listener_flow = linear_flow.Flow(constants.DELETE_LISTENER_FLOW)
        delete_listener_flow.add(*self._get_delete_listener_subflow())
        delete_listener_flow.add(network_tasks.UpdateVIPForDelete(
            requires=constants.LOADBALANCER))
        delete_listener_flow.add(database_tasks.DeleteListenerInDB(
            requires=constants.LISTENER))
        delete_listener_flow.add(database_tasks.DecrementListenerQuota(
            requires=constants.LISTENER))
        delete_listener_flow.add(database_tasks.MarkLBActiveInDB(
            requires=constants.LOADBALANCER))

        return delete_listener_flow

    def _get_delete_listener_subflow(self):
        delete_listener_subflow = linear_flow.Flow(a10constants.DELETE_LISTENER_SUBFLOW)
        delete_listener_subflow.add(lifecycle_tasks.ListenerToErrorOnRevertTask(
            requires=constants.LISTENER))
        delete_listener_subflow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        delete_listener_subflow.add(*self.get_listener_delete_cert_template_subflow())
        delete_listener_subflow.add(virtual_port_tasks.ListenerDelete(
            requires=[constants.LOADBALANCER, constants.LISTENER, a10constants.VTHUNDER]))
        return delete_listener_subflow

    def _get_cert_delete_subflow(self):
        get_delete_cert_subflow = linear_flow.Flow(a10constants.DELETE_CERT_TEMPLATE_SUBFLOW)
        get_delete_cert_subflow.add(cert_tasks.SSLKeyDelete(
            requires=(a10constants.CERT_DATA, a10constants.VTHUNDER)))
        get_delete_cert_subflow.add(cert_tasks.ClientSSLTemplateDelete(
            requires=(a10constants.CERT_DATA, a10constants.VTHUNDER)))
        return get_delete_cert_subflow

    def get_listener_delete_cert_template_subflow(self):
        get_listener_delete_cert_subflow = graph_flow.Flow(
            a10constants.DELETE_LISTENER_CERT_SUBFLOW)
        cert_delete_task = cert_tasks.SSLCertDelete(
            requires=[constants.LOADBALANCER, constants.LISTENER, a10constants.VTHUNDER],
            provides=a10constants.CERT_DATA)
        cert_delete_template_task = self._get_cert_delete_subflow()
        get_listener_delete_cert_subflow.add(cert_delete_task, cert_delete_template_task)
        get_listener_delete_cert_subflow.link(
            cert_delete_task, cert_delete_template_task, decider=self._is_terminated_https)
        return get_listener_delete_cert_subflow

    def get_delete_rack_listener_flow(self):
        """Create a flow to delete a rack listener

        :returns: The flow for deleting a rack listener
        """
        delete_listener_flow = linear_flow.Flow(constants.DELETE_LISTENER_FLOW)
        delete_listener_flow.add(*self._get_delete_listener_subflow())
        delete_listener_flow.add(database_tasks.DeleteListenerInDB(
            requires=constants.LISTENER))
        delete_listener_flow.add(database_tasks.DecrementListenerQuota(
            requires=constants.LISTENER))
        delete_listener_flow.add(database_tasks.MarkLBActiveInDB(
            requires=constants.LOADBALANCER))

        return delete_listener_flow

    def get_delete_listener_internal_flow(self, listener_name):
        """Create a flow to delete a listener and l7policies internally

           (will skip deletion on the amp and marking LB active)

        :returns: The flow for deleting a listener
        """
        delete_listener_flow = linear_flow.Flow(constants.DELETE_LISTENER_FLOW)
        # Should cascade delete all L7 policies
        delete_listener_flow.add(a10_network_tasks.UpdateVIPForDelete(
            name='delete_update_vip_' + listener_name,
            requires=constants.LOADBALANCER))
        delete_listener_flow.add(database_tasks.DeleteListenerInDB(
            name='delete_listener_in_db_' + listener_name,
            requires=constants.LISTENER,
            rebind={constants.LISTENER: listener_name}))
        delete_listener_flow.add(database_tasks.DecrementListenerQuota(
            name='decrement_listener_quota_' + listener_name,
            requires=constants.LISTENER,
            rebind={constants.LISTENER: listener_name}))

        return delete_listener_flow

    def get_update_listener_flow(self):
        """Create a flow to update a listener

        :returns: The flow for updating a listener
        """
        update_listener_flow = linear_flow.Flow(constants.UPDATE_LISTENER_FLOW)
        update_listener_flow.add(lifecycle_tasks.ListenerToErrorOnRevertTask(
            requires=constants.LISTENER))
        update_listener_flow.add(a10_database_tasks.GetVThunderByLoadBalancer(
            requires=constants.LOADBALANCER,
            provides=a10constants.VTHUNDER))
        update_listener_flow.add(*self.get_listener_update_cert_template_subflow())
        update_listener_flow.add(virtual_port_tasks.ListenerUpdate(
            requires=[constants.LOADBALANCER, constants.LISTENER, a10constants.VTHUNDER]))
        update_listener_flow.add(database_tasks.UpdateListenerInDB(
            requires=[constants.LISTENER, constants.UPDATE_DICT]))
        update_listener_flow.add(a10_database_tasks.MarkLBAndListenerActiveInDB(
                                 requires=[constants.LOADBALANCER,
                                           constants.LISTENER]))

        return update_listener_flow

    def _get_cert_update_subflow(self):
        get_cert_update_subflow = linear_flow.Flow(a10constants.UPDATE_CERT_TEMPLATE_SUBFLOW)
        get_cert_update_subflow.add(cert_tasks.SSLKeyUpdate(
            requires=(a10constants.CERT_DATA, a10constants.VTHUNDER)))
        get_cert_update_subflow.add(cert_tasks.ClientSSLTemplateUpdate(
            requires=(a10constants.CERT_DATA, a10constants.VTHUNDER)))
        return get_cert_update_subflow

    def get_listener_update_cert_template_subflow(self):
        get_listener_update_cert_subflow = graph_flow.Flow(
            a10constants.UPDATE_LISTENER_CERT_SUBFLOW)
        cert_update_task = cert_tasks.SSLCertUpdate(
            requires=[constants.LOADBALANCER, constants.LISTENER, a10constants.VTHUNDER],
            provides=a10constants.CERT_DATA)
        cert_update_template_task = self._get_cert_update_subflow()
        get_listener_update_cert_subflow.add(cert_update_task, cert_update_template_task)
        get_listener_update_cert_subflow.link(
            cert_update_task, cert_update_template_task, decider=self._is_terminated_https)
        return get_listener_update_cert_subflow

    def get_rack_vthunder_create_listener_flow(self, project_id):
        """Create a flow to create a rack listener

        :returns: The flow for creating a rack listener
        """
        create_listener_flow = linear_flow.Flow(constants.CREATE_LISTENER_FLOW)
        create_listener_flow.add(*self._get_create_listener_subflow())
        if project_id is None:
            create_listener_flow.add(network_tasks.UpdateVIP(
                requires=constants.LOADBALANCER))
        create_listener_flow.add(a10_database_tasks.
                                 MarkLBAndListenerActiveInDB(
                                     requires=[constants.LOADBALANCER,
                                               constants.LISTENER]))
        return create_listener_flow
