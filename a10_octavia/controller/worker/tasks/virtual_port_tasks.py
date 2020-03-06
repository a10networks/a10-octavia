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

import json
from oslo_log import log as logging
from oslo_config import cfg
from a10_octavia.controller.worker.tasks import persist
from a10_octavia.controller.worker.tasks.common import BaseVThunderTask
import acos_client.errors as acos_errors
from octavia.certificates.common.auth.barbican_acl import BarbicanACLAuth


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class ListenersParent(object):

    def set(self, set_method, loadbalancer, listeners, vthunder):
        ipinip = CONF.listener.ipinip
        no_dest_nat = CONF.listener.no_dest_nat
        ha_conn_mirror = CONF.listener.ha_conn_mirror
        autosnat = CONF.listener.autosnat
        conn_limit = CONF.listener.conn_limit
        virtual_port_templates = {}
        template_virtual_port = CONF.listener.template_virtual_port
        virtual_port_templates['template-virtual-port'] = template_virtual_port

        template_args = {}
        try:
            c = self.client_factory(vthunder)
            status = c.slb.UP
            for listener in listeners:
                if listener.connection_limit != -1:
                    conn_limit = listener.connection_limit
                if conn_limit < 1 or conn_limit > 8000000:
                    LOG.warning("The specified member server connection limit " +
                                "(configuration setting: conn-limit) is out of " +
                                "bounds with value {0}. Please set to between " +
                                "1-8000000. Defaulting to 8000000".format(conn_limit))
                listener.load_balancer = loadbalancer
                if not listener.enabled:
                    status = c.slb.DOWN
                persistence = persist.PersistHandler(c, listener.default_pool)
                s_pers = persistence.s_persistence()
                c_pers = persistence.c_persistence()
                if listener.protocol == "TERMINATED_HTTPS":
                    listener.protocol = 'HTTPS'
                    template_args["template_client_ssl"] = self.cert_handler(
                        loadbalancer, listener, vthunder)

                if listener.protocol.lower() == 'http':
                    # TODO work around for issue in acos client
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
                           # TODO resolve in acos client
                           # ha_conn_mirror=ha_conn_mirror,
                           conn_limit=conn_limit,
                           virtual_port_templates=virtual_port_templates,
                           **template_args)
                LOG.info("Listener created successfully.")
        except Exception as e:
            LOG.error(str(e))
            LOG.info("Error occurred")

    def cert_handler(self, loadbalancer, listener, vthunder):
        """ function to handle certs """
        cert_data = dict()
        bauth = BarbicanACLAuth()
        client = bauth.get_barbican_client(loadbalancer.project_id)
        container = client.containers.get(container_ref=listener.tls_certificate_id)

        cert_data["cert_content"] = container.certificate.payload
        cert_data["key_content"] = container.private_key.payload
        cert_data["key_pass"] = container.private_key_passphrase
        cert_data["template_name"] = listener.id
        cert_data["cert_filename"] = container.certificate.name
        cert_data["key_filename"] = container.private_key.name

        c = self.client_factory(vthunder)

        try:
            c.file.ssl_cert.create(file=cert_data["cert_filename"],
                                   cert=cert_data["cert_content"],
                                   size=len(cert_data["cert_content"]),
                                   action="import", certificate_type="pem")
        except acos_errors.Exists:
            c.file.ssl_cert.update(file=cert_data["cert_filename"],
                                   cert=cert_data["cert_content"],
                                   size=len(cert_data["cert_content"]),
                                   action="import", certificate_type="pem")
        try:
            c.file.ssl_key.create(file=cert_data["key_filename"],
                                  cert=cert_data["key_content"],
                                  size=len(cert_data["key_content"]),
                                  action="import")
        except acos_errors.Exists:
            c.file.ssl_key.update(file=cert_data["key_filename"],
                                  cert=cert_data["key_content"],
                                  size=len(cert_data["key_content"]),
                                  action="import")
        # create template
        try:
            c.slb.template.client_ssl.create(cert_data["template_name"],
                                             cert=cert_data["cert_filename"],
                                             key=cert_data["key_filename"],
                                             passphrase=cert_data["key_pass"])
        except acos_errors.Exists:
            c.slb.template.client_ssl.update(cert_data["template_name"],
                                             cert=cert_data["cert_filename"],
                                             key=cert_data["key_filename"],
                                             passphrase=cert_data["key_pass"])

        return cert_data["template_name"]


class ListenersCreate(ListenersParent, BaseVThunderTask):
    """ Task to create listener """

    def execute(self, loadbalancer, listeners, vthunder):
        """ Execute updates per listener """
        c = self.client_factory(vthunder)
        self.set(c.slb.virtual_server.vport.create, loadbalancer, listeners, vthunder)

    def revert(self, loadbalancer, *args, **kwargs):
        """ Handle failed listeners updates """
        LOG.warning("Reverting listeners updates.")

        for listener in loadbalancer.listeners:
            self.task_utils.mark_listener_prov_status_error(listener.id)

        return None


class ListenersUpdate(ListenersParent, BaseVThunderTask):
    """ Task to update listener """

    def execute(self, loadbalancer, listeners, vthunder):
        """ Execute updates per listener """
        c = self.client_factory(vthunder)
        self.set(c.slb.virtual_server.vport.update, loadbalancer, listeners, vthunder)

    def revert(self, loadbalancer, *args, **kwargs):
        """ Handle failed listeners updates """
        LOG.warning("Reverting listeners updates.")

        for listener in loadbalancer.listeners:
            self.task_utils.mark_listener_prov_status_error(listener.id)

        return None


class ListenerDelete(BaseVThunderTask):
    """ Task to delete the listener """

    def execute(self, loadbalancer, listener, vthunder):
        """ Execute listener delete """
        try:
            c = self.client_factory(vthunder)
            name = loadbalancer.id + "_" + str(listener.protocol_port)
            c.slb.virtual_server.vport.delete(loadbalancer.id, name, listener.protocol,
                                              listener.protocol_port)

            LOG.info("Listener deleted successfully.")
        except Exception as e:
            LOG.error(str(e))
            LOG.debug("Deleted the listener on the vip")

    def revert(self, listener, *args, **kwargs):
        """ Handle a failed listener delete """
        LOG.warning("Reverting listener delete.")

        self.task_utils.mark_listener_prov_status_error(listener.id)
