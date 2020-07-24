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

import acos_client.errors as acos_errors
from oslo_config import cfg
from oslo_log import log as logging
from requests.exceptions import ConnectionError
from taskflow import task

from a10_octavia.common import a10constants
from a10_octavia.common import openstack_mappings
from a10_octavia.controller.worker.tasks.decorators import axapi_client_decorator
from a10_octavia.controller.worker.tasks import utils

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class ListenersParent(object):

    def set(self, set_method, loadbalancer, listener, ssl_template=None):

        ipinip = CONF.listener.ipinip
        no_dest_nat = CONF.listener.no_dest_nat
        autosnat = CONF.listener.autosnat
        conn_limit = CONF.listener.conn_limit
        use_rcv_hop = CONF.listener.use_rcv_hop_for_resp
        ha_conn_mirror = CONF.listener.ha_conn_mirror

        virtual_port_templates = {}
        template_virtual_port = CONF.listener.template_virtual_port
        virtual_port_templates['template-virtual-port'] = template_virtual_port

        template_args = {}

        if listener.connection_limit != -1:
            conn_limit = listener.connection_limit
        if conn_limit < 1 or conn_limit > 64000000:
            LOG.warning('The specified member server connection limit '
                        '(configuration setting: conn-limit) is out of '
                        'bounds with value {0}. Please set to between '
                        '1-64000000. Defaulting to 64000000'.format(conn_limit))
        listener.load_balancer = loadbalancer
        status = self.axapi_client.slb.UP
        if not listener.enabled:
            status = self.axapi_client.slb.DOWN
        c_pers, s_pers = utils.get_sess_pers_templates(listener.default_pool)

        listener.protocol = openstack_mappings.virtual_port_protocol(self.axapi_client,
                                                                     listener.protocol)
        # Adding TERMINATED_HTTPS SSL cert, created in previous task
        if listener.protocol == 'HTTPS' and listener.tls_certificate_id:
            template_args["template_client_ssl"] = listener.id

        if listener.protocol in a10constants.HTTP_TYPE:
            # TODO(hthompson6) work around for issue in acos client
            listener.protocol = listener.protocol.lower()
            virtual_port_template = CONF.listener.template_http
            virtual_port_templates['template-http'] = virtual_port_template
            ha_conn_mirror = None
            LOG.warning("'ha_conn_mirror' is not allowed for HTTP, TERMINATED_HTTPS listener.")
        else:
            virtual_port_template = CONF.listener.template_tcp
            virtual_port_templates['template-tcp'] = virtual_port_template

        virtual_port_template = CONF.listener.template_policy
        virtual_port_templates['template-policy'] = virtual_port_template

        # Add all config filters here
        if no_dest_nat and (
                listener.protocol.lower()
                not in a10constants.NO_DEST_NAT_SUPPORTED_PROTOCOL):
            LOG.warning("'no_dest_nat' is not allowed for HTTP," +
                        "HTTPS or TERMINATED_HTTPS listener.")
            no_dest_nat = False

        set_method(loadbalancer.id, listener.id,
                   listener.protocol,
                   listener.protocol_port,
                   listener.default_pool_id,
                   s_pers_name=s_pers, c_pers_name=c_pers,
                   status=status, no_dest_nat=no_dest_nat,
                   autosnat=autosnat, ipinip=ipinip,
                   # TODO(hthompson6) resolve in acos client
                   ha_conn_mirror=ha_conn_mirror,
                   use_rcv_hop=use_rcv_hop,
                   conn_limit=conn_limit,
                   virtual_port_templates=virtual_port_templates,
                   **template_args)


class ListenerCreate(ListenersParent, task.Task):
    """Task to create listener"""

    @axapi_client_decorator
    def execute(self, loadbalancer, listener, vthunder):
        try:
            self.set(self.axapi_client.slb.virtual_server.vport.create,
                     loadbalancer, listener)
            LOG.debug("Successfully created listener: %s", listener.id)
        except (acos_errors.ACOSException, ConnectionError) as e:
            LOG.exception("Failed to create listener: %s", listener.id)
            raise e

    @axapi_client_decorator
    def revert(self, loadbalancer, listener, vthunder, *args, **kwargs):
        LOG.warning("Reverting creation of listener: %s", listener.id)
        try:
            self.axapi_client.slb.virtual_server.vport.delete(
                loadbalancer.id, listener.id, listener.protocol,
                listener.protocol_port)
        except ConnectionError:
            LOG.exception(
                "Failed to connect A10 Thunder device: %s", vthunder.ip_address)
        except Exception as e:
            LOG.exception("Failed to revert creation of listener: %s due to %s",
                          listener.id, str(e))


class ListenerUpdate(ListenersParent, task.Task):
    """Task to update listener"""

    @axapi_client_decorator
    def execute(self, loadbalancer, listener, vthunder):
        try:
            if listener:
                self.set(self.axapi_client.slb.virtual_server.vport.update,
                         loadbalancer, listener)
                LOG.debug("Successfully updated listener: %s", listener.id)
        except (acos_errors.ACOSException, ConnectionError) as e:
            LOG.exception("Failed to update listener: %s", listener.id)
            raise e


class ListenerDelete(ListenersParent, task.Task):
    """Task to delete the listener"""

    @axapi_client_decorator
    def execute(self, loadbalancer, listener, vthunder):
        listener.protocol = openstack_mappings.virtual_port_protocol(self.axapi_client,
                                                                     listener.protocol)
        try:
            self.axapi_client.slb.virtual_server.vport.delete(
                loadbalancer.id, listener.id, listener.protocol,
                listener.protocol_port)
            LOG.debug("Successfully deleted listener: %s", listener.id)
        except (acos_errors.ACOSException, ConnectionError) as e:
            LOG.exception("Failed to delete listener: %s", listener.id)
            raise e
