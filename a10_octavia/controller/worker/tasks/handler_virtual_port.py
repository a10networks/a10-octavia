from taskflow import task

from octavia.controller.worker import task_utils as task_utilities
from octavia.common import constants
import acos_client
from octavia.amphorae.driver_exceptions import exceptions as driver_except
import time
from oslo_log import log as logging
from oslo_config import cfg
from a10_octavia.common import openstack_mappings
from a10_octavia.controller.worker.tasks.policy import PolicyUtil
from a10_octavia.controller.worker.tasks import persist
from a10_octavia.controller.worker.tasks.common import BaseVThunderTask

CONF = cfg.CONF
LOG = logging.getLogger(__name__)

class ListenersCreate(BaseVThunderTask):
    """Task to update amphora with all specified listeners' configurations."""

    def execute(self, loadbalancer, listeners, vthunder):
        """Execute updates per listener for an amphora."""
        axapi_version = acos_client.AXAPI_21 if vthunder.axapi_version == 21 else acos_client.AXAPI_30
        for listener in listeners:
            listener.load_balancer = loadbalancer
            #self.amphora_driver.update(listener, loadbalancer.vip)
            try:
                c = acos_client.Client(vthunder.ip_address, axapi_version, vthunder.username,
                                       vthunder.password)
                name = loadbalancer.id + "_" + str(listener.protocol_port)
                out = c.slb.virtual_server.vport.create(loadbalancer.id, name, listener.protocol,
                                                listener.protocol_port, listener.default_pool_id,
                                                autosnat=True )
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


class ListenersUpdate(BaseVThunderTask):
    """Task to update amphora with all specified listeners' configurations."""

    def execute(self, loadbalancer, listeners, vthunder):
        """Execute updates per listener for an amphora."""
        for listener in listeners:
            listener.load_balancer = loadbalancer
            #self.amphora_driver.update(listener, loadbalancer.vip)
            try:
                axapi_version = acos_client.AXAPI_21 if vthunder.axapi_version == 21 else acos_client.AXAPI_30
                c = acos_client.Client(vthunder.ip_address, axapi_version, vthunder.username,
                                       vthunder.password)
                name = loadbalancer.id + "_" + str(listener.protocol_port)
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
            axapi_version = acos_client.AXAPI_21 if vthunder.axapi_version == 21 else acos_client.AXAPI_30
            c = acos_client.Client(vthunder.ip_address, axapi_version, vthunder.username,
                                       vthunder.password)
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



    


