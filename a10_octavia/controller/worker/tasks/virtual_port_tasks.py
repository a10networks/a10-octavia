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
from taskflow import task

import acos_client.errors as acos_errors
from octavia.certificates.common.auth.barbican_acl import BarbicanACLAuth

from a10_octavia.controller.worker.tasks.decorators import axapi_client_decorator
from a10_octavia.controller.worker.tasks import utils

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class ListenerParent(object):

    def set(self, set_method, loadbalancer, listener):
        ipinip = CONF.listener.ipinip
        no_dest_nat = CONF.listener.no_dest_nat
        autosnat = CONF.listener.autosnat
        conn_limit = CONF.listener.conn_limit
        virtual_port_templates = {}
        template_virtual_port = CONF.listener.template_virtual_port
        virtual_port_templates['template-virtual-port'] = template_virtual_port

        template_args = {}
        if listener.connection_limit != -1:
            conn_limit = listener.connection_limit
        if conn_limit < 1 or conn_limit > 64000000:
            LOG.warning("The specified member server connection limit " +
                        "(configuration setting: conn-limit) is out of " +
                        "bounds with value {0}. Please set to between " +
                        "1-64000000. Defaulting to 64000000".format(conn_limit))

        status = self.axapi_client.slb.UP

        if not listener.enabled:
            status = self.axapi_client.slb.DOWN
        c_pers, s_pers = utils.get_sess_pers_templates(listener.default_pool)

        if listener.protocol == "TERMINATED_HTTPS":
            listener.protocol = 'HTTPS'
            template_args["template_client_ssl"] = listener.id

        if listener.protocol.lower() == 'http':
            # TODO(hthompson6) work around for issue in acos client
            listener.protocol = listener.protocol.lower()
            virtual_port_template = CONF.listener.template_http
            virtual_port_templates['template-http'] = virtual_port_template
        else:
            virtual_port_template = CONF.listener.template_tcp
            virtual_port_templates['template-tcp'] = virtual_port_template

        virtual_port_template = CONF.listener.template_policy
        virtual_port_templates['template-policy'] = virtual_port_template

        name = loadbalancer.id + "_" + str(listener.protocol_port)

        set_method(loadbalancer.id, name,
                   listener.protocol,
                   listener.protocol_port,
                   listener.default_pool_id,
                   s_pers_name=s_pers, c_pers_name=c_pers,
                   status=status, no_dest_nat=no_dest_nat,
                   autosnat=autosnat, ipinip=ipinip,
                   # TODO(hthompson6) resolve in acos client
                   # ha_conn_mirror=ha_conn_mirror,
                   conn_limit=conn_limit,
                   virtual_port_templates=virtual_port_templates,
                   **template_args)


class ListenerCreate(ListenerParent, task.Task):

    """Task to create listener"""

    @axapi_client_decorator
    def execute(self, loadbalancer, listener, vthunder):
        self.set(self.axapi_client.slb.virtual_server.vport.create, loadbalancer, listener)

    def revert(self, loadbalancer, *args, **kwargs):
        """Handle failed listeners updates """
        LOG.warning("Reverting listener creates")


class ListenerUpdate(ListenerParent, task.Task):

    """Task to update listener"""

    @axapi_client_decorator
    def execute(self, loadbalancer, listener, vthunder):
        self.set(self.axapi_client.slb.virtual_server.vport.update, loadbalancer, listener)

    def revert(self, loadbalancer, *args, **kwargs):
        """ Handle failed listeners updates """
        LOG.warning("Reverting listener update")


class ListenerDelete(task.Task):

    """Task to delete the listener"""

    @axapi_client_decorator
    def execute(self, loadbalancer, listener, vthunder):
        name = loadbalancer.id + "_" + str(listener.protocol_port)
        if listener.protocol == "TERMINATED_HTTPS":
            listener.protocol = 'HTTPS'
        try:
            self.axapi_client.slb.virtual_server.vport.delete(
                loadbalancer.id, name, listener.protocol,
                listener.protocol_port)
            LOG.debug("Listener deleted successfully: %s", name)
        except Exception as e:
            LOG.warning("Failed to delete the listener: %s", str(e))

    def revert(self, listener, *args, **kwargs):
        """ Handle a failed listener delete """
        LOG.warning("Reverting listener delete")
