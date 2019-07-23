from taskflow import task

from octavia.controller.worker import task_utils as task_utilities
from octavia.common import constants
import acos_client
from octavia.amphorae.driver_exceptions import exceptions as driver_except
import time
from oslo_log import log as logging
from oslo_config import cfg
from octavia.common import utils
from a10_octavia.common import openstack_mappings
from a10_octavia.controller.worker.tasks.policy import PolicyUtil
from a10_octavia.controller.worker.tasks import persist
from a10_octavia.controller.worker.tasks.common import BaseVThunderTask

CONF = cfg.CONF
LOG = logging.getLogger(__name__)

class CreateVitualServerTask(BaseVThunderTask):
    """Task to create a virtual server in vthunder device."""

    def execute(self, loadbalancer_id, loadbalancer, vthunder):
        try:
            print("i am here")
            axapi_version = acos_client.AXAPI_21 if vthunder.axapi_version == 21 else acos_client.AXAPI_30
            c = acos_client.Client(vthunder.ip_address, axapi_version, vthunder.username,
                                       vthunder.password)
            r = c.slb.virtual_server.create(loadbalancer_id, loadbalancer.vip.ip_address)
            status = { 'loadbalancers': [{"id": loadbalancer_id,
                       "provisioning_status": constants.ACTIVE }]}
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

    def execute(self, loadbalancer, vthunder):
        loadbalancer_id = loadbalancer.id
        try:
            axapi_version = acos_client.AXAPI_21 if vthunder.axapi_version == 21 else acos_client.AXAPI_30
            c = acos_client.Client(vthunder.ip_address, axapi_version, vthunder.username,
                                       vthunder.password)
            r = c.slb.virtual_server.delete(loadbalancer_id)
            status = { 'loadbalancers': [{"id": loadbalancer_id,
                       "provisioning_status": constants.DELETED }]}
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

    def execute(self, vthunder, amphora):
        """Execute get_info routine for a vThunder until it responds."""
        try:
         
            LOG.info("Trying to connect vThunder after 180 sec")
            time.sleep(180)
            axapi_version = acos_client.AXAPI_21 if vthunder.axapi_version == 21 else acos_client.AXAPI_30
            c = acos_client.Client(vthunder.ip_address, axapi_version, vthunder.username,
                                       vthunder.password)
            amp_info = c.system.information()
            LOG.info(str(amp_info))
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

    def execute(self, loadbalancer, vthunder):
        """Execute get_info routine for a vThunder until it responds."""
        try:
            #import rpdb; rpdb.set_trace()
            axapi_version = acos_client.AXAPI_21 if vthunder.axapi_version == 21 else acos_client.AXAPI_30
            client = acos_client.Client(vthunder.ip_address, axapi_version, vthunder.username,
                                       vthunder.password)
            save_config = client.system.action.write_memory()
            amp_info = client.system.action.reload()
            LOG.info("Reloaded vThunder successfully!")
        except Exception as e:
            LOG.error("Unable to reload vthunder device")
            LOG.info(str(e))
            raise


class AmphoraePostMemberNetworkPlug(BaseVThunderTask):
    """"Task to reload and configure vThunder device"""

    def execute(self, added_ports, loadbalancer, vthunder):
        """Execute get_info routine for a vThunder until it responds."""
        try:
            amphora_id = loadbalancer.amphorae[0].id
            if len(added_ports[amphora_id]) > 0:
                axapi_version = acos_client.AXAPI_21 if vthunder.axapi_version == 21 else acos_client.AXAPI_30
                client = acos_client.Client(vthunder.ip_address, axapi_version, vthunder.username,
                                       vthunder.password)
                save_config = client.system.action.write_memory()
                amp_info = client.system.action.reload()
                LOG.info("Reloaded vThunder successfully!")
            else:
                LOG.info("vThunder reload is not required for member addition.")
        except Exception as e:
            LOG.error("Unable to reload vthunder device")
            LOG.info(str(e))
            raise

class EnableInterface(BaseVThunderTask):
    """"Task to configure vThunder ports"""

    def execute(self, vthunder):
        """Execute get_info routine for a vThunder until it responds."""
        try:
            LOG.info("Waiting 120 sec for vThunder to reload.")
            time.sleep(120)
            axapi_version = acos_client.AXAPI_21 if vthunder.axapi_version == 21 else acos_client.AXAPI_30
            c = acos_client.Client(vthunder.ip_address, axapi_version, vthunder.username,
                                       vthunder.password)
            amp_info = c.system.action.setInterface(1)
            LOG.info("Configured the devices")
        except Exception as e:
            LOG.error("Unable to configure vthunder interface")
            LOG.info(str(e))
            raise

class EnableInterfaceForMembers(BaseVThunderTask):
    """ Task to enable an interface associated with a member """
    
    def execute(self, added_ports, loadbalancer, vthunder):
        """ Enable specific interface of amphora """ 
        try:
            #TODO change if we go for active-passive infra
            amphora_id = loadbalancer.amphorae[0].id
            compute_id = loadbalancer.amphorae[0].compute_id
            network_driver = utils.get_network_driver()
            nics = network_driver.get_plugged_networks(compute_id)
            if len(added_ports[amphora_id]) > 0:
                LOG.info("Waiting 150 sec for vThunder to reload.")
                time.sleep(150)
                target_interface = len(nics)
                axapi_version = acos_client.AXAPI_21 if vthunder.axapi_version == 21 else acos_client.AXAPI_30
                c = acos_client.Client(vthunder.ip_address, axapi_version, vthunder.username,
                                       vthunder.password)
                amp_info = c.system.action.setInterface(target_interface-1)
                LOG.info("Configured the new interface required for member.")
            else:
                LOG.info("Configuration of new interface is not required for member.")            
        except Exception as e:
            LOG.error("Unable to configure vthunder interface")
            LOG.info(str(e))
            raise


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


class PoolCreate(BaseVThunderTask):
    """Task to update amphora with all specified listeners' configurations."""

    def execute(self, pool, vthunder):
        """Execute create pool for an amphora."""
        try:
            axapi_version = acos_client.AXAPI_21 if vthunder.axapi_version == 21 else acos_client.AXAPI_30
            c = acos_client.Client(vthunder.ip_address, axapi_version, vthunder.username,
                                       vthunder.password)
            #need to put algorithm logic
            out = c.slb.service_group.create(pool.id, pool.protocol)
            LOG.info("Pool created successfully.")
        except Exception as e:
            print(str(e))
            LOG.info("Error occurred")

class PoolDelete(BaseVThunderTask):
    """Task to update amphora with all specified listeners' configurations."""

    def execute(self, pool, vthunder):
        """Execute create pool for an amphora."""
        try:
            axapi_version = acos_client.AXAPI_21 if vthunder.axapi_version == 21 else acos_client.AXAPI_30
            c = acos_client.Client(vthunder.ip_address, axapi_version, vthunder.username,
                                   vthunder.password)
            #need to put algorithm logic
            out = c.slb.service_group.delete(pool.id)
            LOG.info("Pool deleted successfully.")
        except Exception as e:
            print(str(e))
            LOG.info("Error occurred")


class MemberCreate(BaseVThunderTask):
    """Task to update amphora with all specified member configurations."""

    def execute(self, member, vthunder, pool):
        """Execute create member for an amphora."""
        try:
            axapi_version = acos_client.AXAPI_21 if vthunder.axapi_version == 21 else acos_client.AXAPI_30
            c = acos_client.Client(vthunder.ip_address, axapi_version, vthunder.username,
                                   vthunder.password)
            out = c.slb.server.create(member.id, member.ip_address)
            LOG.info("Member created successfully.")
        except Exception as e:
            print(str(e))
        try:
            axapi_version = acos_client.AXAPI_21 if vthunder.axapi_version == 21 else acos_client.AXAPI_30
            c = acos_client.Client(vthunder.ip_address, axapi_version, vthunder.username,
                                   vthunder.password)
            out = c.slb.service_group.member.create(pool.id, member.id, member.protocol_port)
            LOG.info("Member associated to pool successfully.")
        except Exception as e:
            print(str(e))
            LOG.info("Error occurred")

class MemberDelete(BaseVThunderTask):
    """Task to update amphora with all specified member configurations."""

    def execute(self, member, vthunder, pool):
        """Execute delete member for an amphora."""
        axapi_version = acos_client.AXAPI_21 if vthunder.axapi_version == 21 else acos_client.AXAPI_30
        try:
            c = acos_client.Client(vthunder.ip_address, axapi_version, vthunder.username,
                                       vthunder.password)
            out = c.slb.service_group.member.delete(pool.id, member.id, member.protocol_port)
            LOG.info("Member de-associated to pool successfully.")
        except Exception as e:
            print(str(e))
        try:
            c = acos_client.Client(vthunder.ip_address, axapi_version, vthunder.username,
                                       vthunder.password)
            out = c.slb.server.delete(member.id)
            LOG.info("Member deleted successfully.")
        except Exception as e:
            print(str(e))
            LOG.info("Error occurred")

class CreateAndAssociateHealthMonitor(BaseVThunderTask):
    """ Task to create a healthmonitor and associate it with provided pool. """

    def execute(self, health_mon, vthunder):
        """ Execute create health monitor for amphora """  
        # TODO : Length of name of healthmonitor for older vThunder devices 
        axapi_version = acos_client.AXAPI_21 if vthunder.axapi_version == 21 else acos_client.AXAPI_30
        try:
            method = None
            url = None
            expect_code = None
            port = None
            if health_mon.type in ['HTTP', 'HTTPS']:
                method = health_mon.http_method
                url = health_mon.url_path
                expect_code = health_mon.expected_codes
            client = acos_client.Client(vthunder.ip_address, axapi_version, vthunder.username,
                                       vthunder.password)
            out = client.slb.hm.create(health_mon.id[0:5], openstack_mappings.hm_type(client, health_mon.type), 
                                         health_mon.delay, health_mon.timeout, health_mon.rise_threshold,
                                         method=method, url=url, expect_code=expect_code, port=port
                                         ) 
            LOG.info("Heath Monitor created successfully.")
        except Exception as e:
            print(str(e))
        try:
            client = acos_client.Client(vthunder.ip_address, axapi_version, vthunder.username,
                                       vthunder.password)
            out = client.slb.service_group.update(health_mon.pool_id,
                                                    health_monitor=health_mon.id[0:5],
                                                    health_check_disable=0) 
            LOG.info("Heath Monitor associated to pool successfully.")
        except Exception as e:
            print(str(e))
            LOG.info("Error occurred")
 
class DeleteHealthMonitor(BaseVThunderTask):
    """ Task to create a healthmonitor and associate it with provided pool. """

    def execute(self, health_mon, vthunder):
        """ Execute create health monitor for amphora """   
        axapi_version = acos_client.AXAPI_21 if vthunder.axapi_version == 21 else acos_client.AXAPI_30
        try:
            c = acos_client.Client(vthunder.ip_address, axapi_version, vthunder.username,
                                       vthunder.password)
            out = c.slb.service_group.update(health_mon.pool_id,
                                                    health_monitor="",
                                                    health_check_disable=False) 
            LOG.info("Heath Monitor disassociated to pool successfully.")
        except Exception as e:
            print(str(e))
            LOG.info("Error occurred")
        try:
            c = acos_client.Client(vthunder.ip_address, axapi_version, vthunder.username,
                                       vthunder.password)
            out = c.slb.hm.delete(health_mon.id)
            LOG.info("Heath Monitor deleted successfully.")
        except Exception as e:
            print(str(e))


class CreateL7Policy(BaseVThunderTask):
    """ Task to create a healthmonitor and associate it with provided pool. """

    def execute(self, l7policy, listeners, vthunder):
        """ Execute create health monitor for amphora """   
        axapi_version = acos_client.AXAPI_21 if vthunder.axapi_version == 21 else acos_client.AXAPI_30
        try:
            filename = l7policy.id
            action = "import"
            p = PolicyUtil()
            script = p.createPolicy(l7policy)
            size = len(script.encode('utf-8'))
            c = acos_client.Client(vthunder.ip_address, axapi_version, vthunder.username,
                                       vthunder.password)
            out = c.slb.aflex_policy.create(file=filename, script=script, size=size, action=action)
            LOG.info("aFlex policy created successfully.")
        except Exception as e:
            print(str(e))
            LOG.info("Error occurred")
        try:
            # get SLB vPort 
            listener = listeners[0]
            
            new_listener = listeners[0]
            c = acos_client.Client(vthunder.ip_address, axapi_version, vthunder.username,
                                       vthunder.password)
            get_listener = c.slb.virtual_server.vport.get(listener.load_balancer_id, listener.name,
                                                listener.protocol, listener.protocol_port)
            
            aflex_scripts = []
            if 'aflex-scripts' in get_listener['port']:
                aflex_scripts = get_listener['port']['aflex-scripts']
                aflex_scripts.append({"aflex": filename})
            else:
                aflex_scripts = [{"aflex": filename}]
            
            persistence = persist.PersistHandler(
            c, listener.default_pool)

            s_pers = persistence.s_persistence()
            c_pers = persistence.c_persistence()
            kargs = {}
            kargs["aflex-scripts"] = aflex_scripts

            update_listener = c.slb.virtual_server.vport.update(listener.load_balancer_id, listener.name,
                                                                listener.protocol, listener.protocol_port, listener.default_pool_id,
                                                                s_pers, c_pers, 1, **kargs)
            LOG.info("Listener updated successfully.")
        except Exception as e:
            print(str(e))
            LOG.info("Error occurred")

class DeleteL7Policy(BaseVThunderTask):
    """ Task to create a healthmonitor and associate it with provided pool. """

    def execute(self, l7policy, vthunder):
        """ Execute create health monitor for amphora """   
        axapi_version = acos_client.AXAPI_21 if vthunder.axapi_version == 21 else acos_client.AXAPI_30
        try:
            listener = l7policy.listener
            old_listener = l7policy.listener
            c = acos_client.Client(vthunder.ip_address, axapi_version, vthunder.username,
                                       vthunder.password)
            get_listener = c.slb.virtual_server.vport.get(old_listener.load_balancer_id,
                                                                 old_listener.name,
                                                                 old_listener.protocol,
                                                                 old_listener.protocol_port)
            # removing listener attachment
            new_aflex_scripts = []
            if 'aflex-scripts' in get_listener['port']:
                aflex_scripts = get_listener['port']['aflex-scripts']
                for aflex in aflex_scripts:
                    if aflex['aflex'] != l7policy.id:
                        new_aflex_scripts.append(aflex)
            
            persistence = persist.PersistHandler(
            c, listener.default_pool)

            s_pers = persistence.s_persistence()
            c_pers = persistence.c_persistence()

            kargs = {}
            kargs["aflex-scripts"] = new_aflex_scripts

            update_listener = c.slb.virtual_server.vport.update(listener.load_balancer_id, listener.name,
                                                                listener.protocol, listener.protocol_port, listener.default_pool_id,
                                                                s_pers, c_pers, 1, **kargs)
            
            LOG.info("aFlex policy detached from port successfully.")
        except Exception as e:
            print(str(e))
            LOG.info("Error occurred")  

        try:
            c = acos_client.Client(vthunder.ip_address, axapi_version, vthunder.username,
                                       vthunder.password)
            out = c.slb.aflex_policy.delete(l7policy.id)
            LOG.info("aFlex policy deleted successfully.")
        except Exception as e:
            print(str(e))
            LOG.info("Error occurred")       

class CreateL7Rule(BaseVThunderTask):
    """ Task to create a healthmonitor and associate it with provided pool. """

    def execute(self, l7rule, listeners, vthunder):
        """ Execute create health monitor for amphora """
        axapi_version = acos_client.AXAPI_21 if vthunder.axapi_version == 21 else acos_client.AXAPI_30
        try:
            l7policy = l7rule.l7policy
            filename = l7policy.id
            action = "import"
            p = PolicyUtil()
            script = p.createPolicy(l7policy)
            size = len(script.encode('utf-8'))
            c = acos_client.Client(vthunder.ip_address, axapi_version, vthunder.username,
                                       vthunder.password)
            out = c.slb.aflex_policy.create(file=filename, script=script, size=size, action=action)
            LOG.info("aFlex policy created successfully.")
        except Exception as e:
            print(str(e))
            LOG.info("Error occurred")
        try:
            # get SLB vPort
            listener = listeners[0]

            new_listener = listeners[0]
            c = acos_client.Client(vthunder.ip_address, axapi_version, vthunder.username,
                                       vthunder.password)
            get_listener = c.slb.virtual_server.vport.get(listener.load_balancer_id, listener.name,
                                                listener.protocol, listener.protocol_port)

            aflex_scripts = []
            if 'aflex-scripts' in get_listener['port']:
                aflex_scripts = get_listener['port']['aflex-scripts']
                aflex_scripts.append({"aflex": filename})
            else:
                aflex_scripts = [{"aflex": filename}]

            persistence = persist.PersistHandler(
            c, listener.default_pool)

            s_pers = persistence.s_persistence()
            c_pers = persistence.c_persistence()

            kargs = {}
            kargs["aflex-scripts"] = aflex_scripts

            update_listener = c.slb.virtual_server.vport.update(listener.load_balancer_id, listener.name,
                                                                listener.protocol, listener.protocol_port, listener.default_pool_id,
                                                                s_pers, c_pers, 1, **kargs)
            LOG.info("Listener updated successfully.")
        except Exception as e:
            print(str(e))
            LOG.info("Error occurred")


class DeleteL7Rule(BaseVThunderTask):
    """ Task to delete a l7rule and associate it with provided pool. """

    def execute(self, l7rule, listeners, vthunder):
        """ Execute create health monitor for amphora """
        axapi_version = acos_client.AXAPI_21 if vthunder.axapi_version == 21 else acos_client.AXAPI_30
        policy = l7rule.l7policy
        rules = policy.l7rules

        for index, rule in enumerate(rules):
                if rule.id == l7rule.id:
                    del rules[index]
                    break
        policy.rules = rules
        l7rule.l7policy = policy
        try:
            l7pol = l7rule.l7policy
            filename = l7pol.id
            action = "import"
            p = PolicyUtil()
            script = p.createPolicy(l7pol)
            size = len(script.encode('utf-8'))
            c = acos_client.Client(vthunder.ip_address, axapi_version, vthunder.username,
                                       vthunder.password)
            out = c.slb.aflex_policy.create(file=filename, script=script, size=size, action=action)
            LOG.info("aFlex policy created successfully.")
        except Exception as e:
            print(str(e))
            LOG.info("Error occurred")
        try:
            # get SLB vPort
            listener = listeners[0]

            new_listener = listeners[0]
            c = acos_client.Client(vthunder.ip_address, axapi_version, vthunder.username,
                                       vthunder.password)
            get_listener = c.slb.virtual_server.vport.get(listener.load_balancer_id, listener.name,
                                                listener.protocol, listener.protocol_port)

            aflex_scripts = []
            if 'aflex-scripts' in get_listener['port']:
                aflex_scripts = get_listener['port']['aflex-scripts']
                aflex_scripts.append({"aflex": filename})
            else:
                aflex_scripts = [{"aflex": filename}]

            persistence = persist.PersistHandler(
            c, listener.default_pool)

            s_pers = persistence.s_persistence()
            c_pers = persistence.c_persistence()

            kargs = {}
            kargs["aflex-scripts"] = aflex_scripts

            update_listener = c.slb.virtual_server.vport.update(listener.load_balancer_id, listener.name,
                                                                listener.protocol, listener.protocol_port, listener.default_pool_id,
                                                                s_pers, c_pers, 1, **kargs)
            LOG.info("Listener updated successfully.")
        except Exception as e:
            print(str(e))
            LOG.info("Error occurred")

