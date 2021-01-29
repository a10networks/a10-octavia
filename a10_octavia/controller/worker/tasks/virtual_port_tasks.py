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
from a10_octavia.common import exceptions
from a10_octavia.common import openstack_mappings
from a10_octavia.controller.worker.tasks.decorators import axapi_client_decorator
from a10_octavia.controller.worker.tasks import utils

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class ListenersParent(object):

    def set(self, set_method, loadbalancer, listener, vthunder, flavor_data=None,
            update_dict=None, ssl_template=None):
        listener.load_balancer = loadbalancer
        listener.protocol = openstack_mappings.virtual_port_protocol(
            self.axapi_client, listener.protocol).lower()

        config_data = {
            'ipinip': CONF.listener.ipinip,
            'use_rcv_hop': CONF.listener.use_rcv_hop_for_resp,
            'ha_conn_mirror': CONF.listener.ha_conn_mirror
        }

        status = self.axapi_client.slb.UP
        if not listener.enabled:
            status = self.axapi_client.slb.DOWN
        config_data['status'] = status

        conn_limit = CONF.listener.conn_limit
        if listener.connection_limit != -1:
            conn_limit = listener.connection_limit
        if conn_limit < 1 or conn_limit > 64000000:
            LOG.warning('The specified member server connection limit '
                        '(configuration setting: conn-limit) is out of '
                        'bounds with value {0}. Please set to between '
                        '1-64000000. Defaulting to 64000000'.format(conn_limit))
        config_data['conn_limit'] = conn_limit

        no_dest_nat = CONF.listener.no_dest_nat
        if no_dest_nat and (
                listener.protocol
                not in a10constants.NO_DEST_NAT_SUPPORTED_PROTOCOL):
            LOG.warning("'no_dest_nat' is not allowed for HTTP," +
                        "HTTPS or TERMINATED_HTTPS listener.")
            no_dest_nat = False
        config_data['no_dest_nat'] = no_dest_nat

        autosnat = CONF.listener.autosnat
        if autosnat and no_dest_nat:
            raise exceptions.SNATConfigurationError()
        config_data['autosnat'] = autosnat

        c_pers, s_pers = utils.get_sess_pers_templates(listener.default_pool)
        device_templates = self.axapi_client.slb.template.templates.get()
        vport_templates = {}
        template_vport = CONF.listener.template_virtual_port
        if template_vport and template_vport.lower() != 'none':
            template_key = 'template-virtual-port'
            if vthunder.partition_name != "shared":
                if CONF.a10_global.use_shared_for_template_lookup:
                    template_key = utils.shared_template_modifier(template_key,
                                                                  template_vport,
                                                                  device_templates)
            vport_templates[template_key] = template_vport

        template_args = {}
        if listener.protocol.upper() in a10constants.HTTP_TYPE:
            if listener.protocol == 'https' and listener.tls_certificate_id:
                # Adding TERMINATED_HTTPS SSL cert, created in previous task
                template_args["template_client_ssl"] = listener.id

            template_http = CONF.listener.template_http
            if template_http and template_http.lower() != 'none':
                template_key = 'template-http'
                if vthunder.partition_name != "shared":
                    if CONF.a10_global.use_shared_for_template_lookup:
                        template_key = utils.shared_template_modifier(template_key,
                                                                      template_http,
                                                                      device_templates)
                vport_templates[template_key] = template_http
            """
            if ha_conn_mirror is not None:
                ha_conn_mirror = None
                LOG.warning("'ha_conn_mirror' is not allowed for HTTP "
                            "or TERMINATED_HTTPS listeners.")
            """
        elif listener.protocol == 'tcp':
            template_tcp = CONF.listener.template_tcp
            if template_tcp and template_tcp.lower() != 'none':
                template_key = 'template-tcp'
                if vthunder.partition_name != "shared":
                    if CONF.a10_global.use_shared_for_template_lookup:
                        template_key = utils.shared_template_modifier(template_key,
                                                                      template_tcp,
                                                                      device_templates)
                vport_templates[template_key] = template_tcp

        template_policy = CONF.listener.template_policy
        if template_policy and template_policy.lower() != 'none':
            template_key = 'template-policy'
            if vthunder.partition_name != "shared":
                if CONF.a10_global.use_shared_for_template_lookup:
                    template_key = utils.shared_template_modifier(template_key,
                                                                  template_policy,
                                                                  device_templates)
            vport_templates[template_key] = template_policy

        vport_args = {}
        if flavor_data:
            virtual_port_flavor = flavor_data.get('virtual_port')
            if virtual_port_flavor:
                name_exprs = virtual_port_flavor.get('name_expressions')
                parsed_exprs = utils.parse_name_expressions(
                    listener.name, name_exprs)
                virtual_port_flavor.pop('name_expressions', None)
                virtual_port_flavor.update(parsed_exprs)
                vport_args = {'port': virtual_port_flavor}

            # use default nat-pool pool if pool is not specified
            if 'port' not in vport_args or 'pool' not in vport_args['port']:
                pool_flavor = flavor_data.get('nat_pool')
                if pool_flavor and 'pool_name' in pool_flavor:
                    pool_arg = {}
                    pool_arg['pool'] = pool_flavor['pool_name']
                    if 'port' in vport_args:
                        vport_args['port'].update(pool_arg)
                    else:
                        vport_args['port'] = pool_arg
        config_data.update(template_args)
        config_data.update(vport_args)

        set_method(loadbalancer.id,
                   listener.id,
                   listener.protocol,
                   listener.protocol_port,
                   listener.default_pool_id,
                   s_pers_name=s_pers, c_pers_name=c_pers,
                   virtual_port_templates=vport_templates,
                   **config_data)


class ListenerCreate(ListenersParent, task.Task):
    """Task to create listener"""

    @axapi_client_decorator
    def execute(self, loadbalancer, listener, vthunder, flavor_data=None):
        try:
            self.set(self.axapi_client.slb.virtual_server.vport.create,
                     loadbalancer, listener, vthunder, flavor_data)
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
    def execute(self, loadbalancer, listener, vthunder, flavor_data=None, update_dict=None):
        try:
            if listener:
                self.set(self.axapi_client.slb.virtual_server.vport.replace,
                         loadbalancer, listener, vthunder, flavor_data, update_dict)
                LOG.debug("Successfully updated listener: %s", listener.id)
        except (acos_errors.ACOSException, ConnectionError) as e:
            LOG.exception("Failed to update listener: %s", listener.id)
            raise e


class ListenerUpdateForPool(ListenersParent, task.Task):
    """Task to update listener while pool delete"""

    @axapi_client_decorator
    def execute(self, loadbalancer, listener, vthunder):
        try:
            if listener:
                listener.protocol = openstack_mappings.virtual_port_protocol(
                    self.axapi_client, listener.protocol).lower()
                self.axapi_client.slb.virtual_server.vport.update(
                    loadbalancer.id,
                    listener.id,
                    listener.protocol,
                    listener.protocol_port,
                    listener.default_pool_id)
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
