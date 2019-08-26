from taskflow import task
from octavia.controller.worker import task_utils as task_utilities
from octavia.common import constants
import acos_client
import acos_client.errors as acos_errors
from octavia.amphorae.driver_exceptions import exceptions as driver_except
import octavia.certificates.manager.barbican as barbican_cert_mgr
import time
from oslo_log import log as logging
from oslo_config import cfg
from a10_octavia.common import openstack_mappings
from octavia.certificates.common.auth.barbican_acl import BarbicanACLAuth
from a10_octavia.controller.worker.tasks.policy import PolicyUtil
from a10_octavia.controller.worker.tasks import persist
from a10_octavia.controller.worker.tasks.common import BaseVThunderTask


CONF = cfg.CONF
LOG = logging.getLogger(__name__)

class ListenersCreate(BaseVThunderTask):
    """Task to update amphora with all specified listeners' configurations."""
    def execute(self, loadbalancer, listeners, vthunder):
        """Execute updates per listener for an amphora."""
        #ipinip = self.config.getboolean('LISTENER','ipinip')
        ipinip = bool(self.config.get('LISTENER','ipinip'))
        no_dest_nat = bool(self.config.get('LISTENER','no_dest_nat'))
        ha_conn_mirror = bool(self.config.get('LISTENER','ha_conn_mirror'))
        template_policy = self.config.get('LISTENER','template_policy')
        autosnat=bool(self.config.get('LISTENER','autosnat'))
        conn_limit = self.config.getint('LISTENER', 'conn_limit')
        virtual_port_templates={}
        try:
            conf_templates = self.config.get('LISTENER','virtual_port_templates').replace('"', '')
            virtual_port_templates['virtual_port_templates'] = conf_templates
        except:
            virtual_port_templates['virtual_port_templates'] = None
        try:
            conf_templates = self.config.get('LISTENER','tcp_template').replace('"', '')
            virtual_port_templates['tcp_template'] = conf_templates
        except:
            virtual_port_templates['tcp_template'] = None
        try:
            conf_templates = self.config.get('LISTENER','http_template').replace('"', '')
            virtual_port_templates['http_template'] = conf_templates
        except:
            virtual_port_templates['http_template'] = None
        template_args = {}
        if conn_limit is not None:
            if conn_limit < 1 or conn_limit > 8000000:
                LOG.warning("The specified member server connection limit " +
                            "(configuration setting: conn-limit) is out of " +
                            "bounds with value {0}. Please set to between " +
                            "1-8000000. Defaulting to 8000000".format(conn_limit))
        for listener in listeners:
            listener.load_balancer = loadbalancer
            #self.amphora_driver.update(listener, loadbalancer.vip)
            try:
                c = self.client_factory(vthunder)
                persistence = persist.PersistHandler(c, listener.default_pool)
                s_pers = persistence.s_persistence()
                c_pers = persistence.c_persistence()
                status = c.slb.UP
                if not listener.provisioning_status:
                    status = c.slb.DOWN
                templates = self.meta(listener, "template", {})
                cert_data = dict()
                if listener.protocol == "TERMINATED_HTTPS":
                    listener.protocol = 'HTTPS'
                    template_args["template_client_ssl"] = self.cert_handler(loadbalancer, listener, vthunder)
                name = loadbalancer.id + "_" + str(listener.protocol_port)
                out = c.slb.virtual_server.vport.create(loadbalancer.id, name, listener.protocol,
                                                listener.protocol_port, listener.default_pool_id,
                                                s_pers_name=s_pers, c_pers_name=c_pers,
                                                status=status, autosnat=autosnat, ipinip=ipinip,
                                                no_dest_nat=no_dest_nat, ha_conn_mirror=ha_conn_mirror,
                                                conn_limit=conn_limit,
                                                virtual_port_templates=virtual_port_templates,
                                                **template_args)
                LOG.info("Listener created successfully.")
            except Exception as e:
                print(str(e))
                LOG.info("Error occurred")
    def revert(self, loadbalancer, *args, **kwargs):
        """Handle failed listeners updates."""

        LOG.warning("Reverting listeners updates.")

        for listener in loadbalancer.listeners:
            self.task_utils.mark_listener_prov_status_error(listener.id)

        return None

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
        cert_data["key_filename"] =  container.private_key.name

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
            c.slb.template.client_ssl.create(
                    cert_data["template_name"],
                    cert=cert_data["cert_filename"],
                    key=cert_data["key_filename"],
                    passphrase=cert_data["key_pass"])
        except acos_errors.Exists:
            c.slb.template.client_ssl.update(
                    cert_data["template_name"],
                    cert=cert_data["cert_filename"],
                    key=cert_data["key_filename"],
                    passphrase=cert_data["key_pass"])
        
        return cert_data["template_name"]

class ListenersUpdate(BaseVThunderTask):
    """Task to update amphora with all specified listeners' configurations."""

    def execute(self, loadbalancer, listeners, vthunder):
        """Execute updates per listener for an amphora."""
        for listener in listeners:
            listener.load_balancer = loadbalancer
            #self.amphora_driver.update(listener, loadbalancer.vip)
            try:
                c = self.client_factory(vthunder)
                name = loadbalancer.id + "_" + str(listener.protocol_port)
                if listener.protocol == "TERMINATED_HTTPS":
                    listener.protocol = 'HTTPS'
                out = c.slb.virtual_server.vport.update(loadbalancer.id, name, listener.protocol,
                                                listener.protocol_port, listener.default_pool_id)
                LOG.info("Listener created successfully.")
            except Exception as e:
                print(str(e))
                LOG.info("Error occurred")

    def revert(self, loadbalancer, *args, **kwargs):
        """Handle failed listeners updates."""

        LOG.warning("Reverting listeners updates.")

        for listener in loadbalancer.listeners:
            self.task_utils.mark_listener_prov_status_error(listener.id)

        return None

class ListenerDelete(BaseVThunderTask):
    """Task to delete the listener on the vip."""

    def execute(self, loadbalancer, listener, vthunder):
        """Execute listener delete routines for an amphora."""
        #self.amphora_driver.delete(listener, loadbalancer.vip)
        try:
            c = self.client_factory(vthunder)
            name = loadbalancer.id + "_" + str(listener.protocol_port)
            out = c.slb.virtual_server.vport.delete(loadbalancer.id, name, listener.protocol,
                                            listener.protocol_port)
            LOG.info("Listener deleted successfully.")
        except Exception as e:
            print(str(e))
            LOG.info("Error occurred")
        LOG.debug("Deleted the listener on the vip")

    def revert(self, listener, *args, **kwargs):
        """Handle a failed listener delete."""

        LOG.warning("Reverting listener delete.")

        self.task_utils.mark_listener_prov_status_error(listener.id)
