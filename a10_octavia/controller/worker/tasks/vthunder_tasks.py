from taskflow import task

from octavia.controller.worker import task_utils as task_utilities
from octavia.common import constants
import acos_client
from octavia.amphorae.driver_exceptions import exceptions as driver_except
import time
from oslo_log import log as logging
from oslo_config import cfg
CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class BaseVThunderTask(task.Task):
    """Base task to instansiate common classes."""

    def __init__(self, **kwargs):
        self.task_utils = task_utilities.TaskUtils()
        super(BaseVThunderTask, self).__init__(**kwargs)

class CreateVitualServerTask(BaseVThunderTask):
    """Task to create a virtual server in vthunder device."""

    def execute(self, loadbalancer_id, loadbalancer, amphora):
        try:
            c = acos_client.Client(amphora[0].lb_network_ip, acos_client.AXAPI_30, 'admin', 'a10')
            r = c.slb.virtual_server.create(loadbalancer_id, loadbalancer.vip.ip_address)
            status = { 'loadbalancers': [{"id": loadbalancer_id,
                       "provisioning_status": constants.ACTIVE }]}
            LOG.info("amphora id is:" + str(amphora.id))
            #LOG.info("vthunder details:" + str(vthunder))
        except Exception as e:
            r = str(e)
            LOG.info(r)
            status = { 'loadbalancers': [{"id": loadbalancer_id,
                       "provisioning_status": constants.ERROR }]}
        LOG.info(str(status))
        return status


    def revert(self, loadbalancer_id, *args, **kwargs):
        pass

class DeleteVitualServerTask(BaseVThunderTask):
    """Task to delete a virtual server in vthunder device."""

    def execute(self, loadbalancer, amphora):
        loadbalancer_id = loadbalancer.id
        try:
            #IMP: update required
            
            vthunder = amphora[0].cached_zone
            #c = acos_client.Client(vthunder.ip, vthunder.acos_version, vthunder.username, vthunder.password)
            #r = self.c.slb.virtual_server.delete(loadbalancer_id)
            status = { 'loadbalancers': [{"id": loadbalancer_id,
                       "provisioning_status": constants.DELETED }]}
            LOG.info(amphora[0].cached_zone)
            LOG.info("amphora id is:" + str(amphora[0].id))
        except Exception as e:
            r = str(e)
            LOG.info(r)
            status = { 'loadbalancers': [{"id": loadbalancer_id,
                       "provisioning_status": constants.ERROR }]}
        LOG.info(str(status))
        return status

    def revert(self, loadbalancer, *args, **kwargs):
        pass

class VThunderComputeConnectivityWait(BaseVThunderTask):
    """"Task to wait for the compute instance to be up."""

    def execute(self, amphora):
        """Execute get_info routine for a vThunder until it responds."""
        try:
         
            LOG.info("Trying to connect vThunder after 180 sec")
            time.sleep(180)
            c = acos_client.Client(amphora.lb_network_ip, acos_client.AXAPI_30, 'admin', 'a10')
            amp_info = c.system.information()
            LOG.info(str(amp_info))
            LOG.info('Successfuly connected to amphora %s: %s',
                          amphora.id, amp_info)
        except driver_except.TimeOutException:
            LOG.error("Amphora compute instance failed to become reachable. "
                      "This either means the compute driver failed to fully "
                      "boot the instance inside the timeout interval or the "
                      "instance is not reachable via the lb-mgmt-net.")
            self.amphora_repo.update(db_apis.get_session(), amphora.id,
                                     status=constants.ERROR)
            raise

class AmphoraePostVIPPlug(BaseVThunderTask):
    """"Task to reload and configure vThunder device"""

    def execute(self, loadbalancer, amphora):
        """Execute get_info routine for a vThunder until it responds."""
        try:
            #import rpdb; rpdb.set_trace()
            c = acos_client.Client(amphora[0].lb_network_ip, acos_client.AXAPI_30, 'admin', 'a10')
            amp_info = c.system.action.reload()
            LOG.info("Reloaded vThunder successfully!")
        except Exception as e:
            LOG.error("Unable to reload vthunder device")
            LOG.info(str(e))
            raise

class EnableInterface(BaseVThunderTask):
    """"Task to configure vThunder ports"""

    def execute(self, amphora):
        """Execute get_info routine for a vThunder until it responds."""
        try:
            LOG.info("Waiting 120 sec after relaods")
            time.sleep(120)
            c = acos_client.Client(amphora[0].lb_network_ip, acos_client.AXAPI_30, 'admin', 'a10')
            amp_info = c.system.action.setInterface(1)
            LOG.info("Configured the devices")
        except Exception as e:
            LOG.error("Unable to configure vthunder interface")
            LOG.info(str(e))
            raise

class ListenersCreate(BaseVThunderTask):
    """Task to update amphora with all specified listeners' configurations."""

    def execute(self, loadbalancer, listeners, amphora):
        """Execute updates per listener for an amphora."""
        for listener in listeners:
            listener.load_balancer = loadbalancer
            #self.amphora_driver.update(listener, loadbalancer.vip)
            try:
                c = acos_client.Client(amphora[0].lb_network_ip, acos_client.AXAPI_30, 'admin', 'a10')
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

    def execute(self, loadbalancer, listeners, amphora):
        """Execute updates per listener for an amphora."""
        for listener in listeners:
            listener.load_balancer = loadbalancer
            #self.amphora_driver.update(listener, loadbalancer.vip)
            try:
                c = acos_client.Client(amphora[0].lb_network_ip, acos_client.AXAPI_30, 'admin', 'a10')
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

    def execute(self, loadbalancer, listener, amphora):
        """Execute listener delete routines for an amphora."""
        #self.amphora_driver.delete(listener, loadbalancer.vip)
        try:
            c = acos_client.Client(amphora[0].lb_network_ip, acos_client.AXAPI_30, 'admin', 'a10')
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


class PoolCreate(BaseVThunderTask):
    """Task to update amphora with all specified listeners' configurations."""

    def execute(self, pool, amphora):
        """Execute create pool for an amphora."""
        try:
            c = acos_client.Client(amphora[0].lb_network_ip, acos_client.AXAPI_30, 'admin', 'a10')
            #need to put algorithm logic
            out = c.slb.service_group.create(pool.id, pool.protocol)
            LOG.info("Pool created successfully.")
        except Exception as e:
            print(str(e))
            LOG.info("Error occurred")

class PoolDelete(BaseVThunderTask):
    """Task to update amphora with all specified listeners' configurations."""

    def execute(self, pool, amphora):
        """Execute create pool for an amphora."""
        try:
            c = acos_client.Client(amphora[0].lb_network_ip, acos_client.AXAPI_30, 'admin', 'a10')
            #need to put algorithm logic
            out = c.slb.service_group.delete(pool.id)
            LOG.info("Pool deleted successfully.")
        except Exception as e:
            print(str(e))
            LOG.info("Error occurred")


class MemberCreate(BaseVThunderTask):
    """Task to update amphora with all specified member configurations."""

    def execute(self, member, amphora, pool):
        """Execute create member for an amphora."""
        try:
            c = acos_client.Client(amphora[0].lb_network_ip, acos_client.AXAPI_30, 'admin', 'a10')
            out = c.slb.server.create(member.id, member.ip_address)
            LOG.info("Member created successfully.")
        except Exception as e:
            print(str(e))
        try:
            c = acos_client.Client(amphora[0].lb_network_ip, acos_client.AXAPI_30, 'admin', 'a10')
            out = c.slb.service_group.member.create(pool.id, member.id, member.protocol_port)
            LOG.info("Member associated to pool successfully.")
        except Exception as e:
            print(str(e))
            LOG.info("Error occurred")

class MemberDelete(BaseVThunderTask):
    """Task to update amphora with all specified member configurations."""

    def execute(self, member, amphora, pool):
        """Execute delete member for an amphora."""
        try:
            c = acos_client.Client(amphora[0].lb_network_ip, acos_client.AXAPI_30, 'admin', 'a10')
            out = c.slb.service_group.member.delete(pool.id, member.id, member.protocol_port)
            LOG.info("Member de-associated to pool successfully.")
        except Exception as e:
            print(str(e))
        try:
            c = acos_client.Client(amphora[0].lb_network_ip, acos_client.AXAPI_30, 'admin', 'a10')
            out = c.slb.server.delete(member.id)
            LOG.info("Member deleted successfully.")
        except Exception as e:
            print(str(e))
            LOG.info("Error occurred")

