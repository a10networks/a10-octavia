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


from taskflow import task

from octavia.controller.worker import task_utils as task_utilities
from octavia.common import constants
import acos_client
from acos_client.errors import ACOSException
from octavia.amphorae.driver_exceptions import exceptions as driver_except
import time
from requests.exceptions import ConnectionError
from requests.exceptions import ReadTimeout
from httplib import BadStatusLine
from octavia.db import api as db_apis
from oslo_log import log as logging
from oslo_config import cfg
from octavia.common import utils
from a10_octavia.common import a10constants, openstack_mappings
from a10_octavia.controller.worker.tasks.policy import PolicyUtil
from a10_octavia.controller.worker.tasks import persist
from a10_octavia.controller.worker.tasks.common import BaseVThunderTask



CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class CreateVitualServerTask(BaseVThunderTask):
    """Task to create a virtual server in vthunder device."""

    def execute(self, loadbalancer_id, loadbalancer, vthunder):
        try:
            c = self.client_factory(vthunder)
            r = c.slb.virtual_server.create(loadbalancer_id, loadbalancer.vip.ip_address)
            status = {'loadbalancers': [{"id": loadbalancer_id,
                                         "provisioning_status": constants.ACTIVE}]}
        except Exception as e:
            r = str(e)
            LOG.info(r)
            status = {'loadbalancers': [{"id": loadbalancer_id,
                                         "provisioning_status": constants.ERROR}]}
        LOG.info(str(status))
        return status

    def revert(self, loadbalancer_id, *args, **kwargs):
        pass


class DeleteVitualServerTask(BaseVThunderTask):
    """Task to delete a virtual server in vthunder device."""

    def execute(self, loadbalancer, vthunder):
        loadbalancer_id = loadbalancer.id
        try:
            c = self.client_factory(vthunder)
            r = c.slb.virtual_server.delete(loadbalancer_id)
            status = {'loadbalancers': [{"id": loadbalancer_id,
                                         "provisioning_status": constants.DELETED}]}
        except Exception as e:
            r = str(e)
            LOG.info(r)
            status = {'loadbalancers': [{"id": loadbalancer_id,
                                         "provisioning_status": constants.ERROR}]}
        LOG.info(str(status))
        return status

    def revert(self, loadbalancer, *args, **kwargs):
        pass


class VThunderComputeConnectivityWait(BaseVThunderTask):
    """"Task to wait for the compute instance to be up."""

    def execute(self, vthunder, amphora):
        """Execute get_info routine for a vThunder until it responds."""
        try:

            LOG.info("Attempting to connect vThunder device for connection.")
            attempts = 20
            while attempts >= 0:
                try:
                    attempts = attempts - 1
                    c = self.client_factory(vthunder)
                    amp_info = c.system.information()
                    LOG.info(str(amp_info))
                    break
                except (ConnectionError, ACOSException, BadStatusLine, ReadTimeout):
                    attemptid = 21 - attempts
                    time.sleep(20)
                    LOG.info("VThunder connection attempt - " + str(attemptid))
                    pass
            if attempts < 0:
               LOG.error("Failed to connect vThunder in expected amount of boot time.")
               raise ConnectionError
            
        except driver_except.TimeOutException:
            LOG.error("Amphora compute instance failed to become reachable. "
                      "This either means the compute driver failed to fully "
                      "boot the instance inside the timeout interval or the "
                      "instance is not reachable via the lb-mgmt-net.")
            self.amphora_repo.update(db_apis.get_session(), amphora.id,
                                     status=constants.ERROR)
            raise


class AmphoraePostVIPPlug(BaseVThunderTask):
    """"Task to reboot and configure vThunder device"""

    def execute(self, loadbalancer, vthunder):
        """Execute get_info routine for a vThunder until it responds."""
        try:
            c = self.client_factory(vthunder)
            save_config = c.system.action.write_memory()
            amp_info = c.system.action.reboot()
            LOG.info("Waiting for 30 seconds to trigger vThunder reboot.")
            time.sleep(30)
            LOG.info("Rebooted vThunder successfully!")
        except Exception as e:
            LOG.error("Unable to reboot vthunder device")
            LOG.info(str(e))
            raise


class AmphoraePostMemberNetworkPlug(BaseVThunderTask):
    """"Task to reboot and configure vThunder device"""

    def execute(self, added_ports, loadbalancer, vthunder):
        """Execute get_info routine for a vThunder until it responds."""
        try:
            amphora_id = loadbalancer.amphorae[0].id
            if len(added_ports[amphora_id]) > 0:
                c = self.client_factory(vthunder)
                save_config = c.system.action.write_memory()
                amp_info = c.system.action.reboot()
                time.sleep(30)
                LOG.info("Rebooted vThunder successfully!")
            else:
                LOG.info("vThunder reboot is not required for member addition.")
        except Exception as e:
            LOG.error("Unable to reload vthunder device")
            LOG.info(str(e))
            raise


class EnableInterface(BaseVThunderTask):
    """"Task to configure vThunder ports"""

    def execute(self, vthunder):
        """Execute get_info routine for a vThunder until it responds."""
        try:
            c = self.client_factory(vthunder)
            amp_info = c.system.action.setInterface(1)
            LOG.info("Configured the devices")
        except Exception as e:
            LOG.error("Unable to configure vthunder interface")
            LOG.info(str(e))
            # raise


class EnableInterfaceForMembers(BaseVThunderTask):
    """ Task to enable an interface associated with a member """

    def execute(self, added_ports, loadbalancer, vthunder):
        """ Enable specific interface of amphora """
        try:
            amphora_id = loadbalancer.amphorae[0].id
            compute_id = loadbalancer.amphorae[0].compute_id
            network_driver = utils.get_network_driver()
            nics = network_driver.get_plugged_networks(compute_id)
            if len(added_ports[amphora_id]) > 0:
                configured_interface = False
                attempts = 5
                while attempts > 0 and configured_interface is False:
                    try:
                        target_interface = len(nics)
                        c = self.client_factory(vthunder)
                        amp_info = c.system.action.setInterface(target_interface - 1)
                        configured_interface = True
                        LOG.info("Configured the new interface required for member.")
                    except (ConnectionError, ACOSException, BadStatusLine, ReadTimeout):
                        attempts = attempts - 1
            else:
                LOG.info("Configuration of new interface is not required for member.")
        except Exception as e:
            LOG.error("Unable to configure vthunder interface")
            LOG.info(str(e))
            raise


class ConfigureVRRP(BaseVThunderTask):
    """"Task to configure vThunder VRRP """

    def execute(self, vthunder, backup_vthunder):
        """Execute to configure vrrp in two vThunder devices."""
        c = self.client_factory(vthunder)
        status = c.system.action.check_vrrp_status()
        if not status:
            try:
                c = self.client_factory(vthunder)
                amp_info = c.system.action.configureVRRP(1,1)
                LOG.info("Configured the master vThunder for VRRP")
            except Exception as e:
                LOG.error("Unable to configure master vThunder VRRP")
                LOG.info(str(e))
                raise
        
            try:
                c = self.client_factory(backup_vthunder)
                amp_info = c.system.action.configureVRRP(2,1)
                LOG.info("Configured the backup vThunder for VRRP")
            except Exception as e:
                LOG.error("Unable to configure backup vThunder VRRP")
                LOG.info(str(e))
                #raise
        return status     


class ConfigureVRID(BaseVThunderTask):
    """"Task to configure vThunder VRRP """

    def execute(self, vthunder, backup_vthunder, vrrp_status ):
        """Execute to configure vrrp in two vThunder devices."""
        if not vrrp_status:
            try:
                c = self.client_factory(vthunder)
                amp_info = c.system.action.configureVRID(1)
                LOG.info("Configured the master vThunder for VRID")
            except Exception as e:
                LOG.error("Unable to configure master vThunder VRRP")
                LOG.info(str(e))
                raise
        
            try:
                c = self.client_factory(backup_vthunder)
                amp_info = c.system.action.configureVRID(1)
                LOG.info("Configured the backup vThunder for VRID")
            except Exception as e:
                LOG.error("Unable to configure backup vThunder VRRP")
                LOG.info(str(e))
                #raise


class ConfigureVRRPSync(BaseVThunderTask):
    """"Task to sync vThunder VRRP """

    def execute(self, vthunder, backup_vthunder, vrrp_status):
        """Execute to sync up vrrp in two vThunder devices."""
        if not vrrp_status:
            try:
                c = self.client_factory(vthunder)
                amp_info = c.system.action.configSynch(backup_vthunder.ip_address, backup_vthunder.username,
                                                       backup_vthunder.password)
                LOG.info("Waiting 30 seconds for config synch.")
                time.sleep(30)
                LOG.info("Sync up for vThunder master")
            except Exception as e:
                LOG.error("Unable to sync master vThunder VRRP")
                LOG.info(str(e))
                #raise


class ConfigureaVCS(BaseVThunderTask):
    """"Task to configure aVCS """

    def execute(self, vthunder, backup_vthunder, vrrp_status):
        """Execute to configure aVCS in two vThunder devices."""
        if not vrrp_status:
            try:
                c = self.client_factory(vthunder)
                c.system.action.set_vcs_device(1, 200)
                c.system.action.set_vcs_para("192.168.0.100", "255.255.255.0")
                c.system.action.vcs_enable()
                c.system.action.vcs_reload()
                LOG.info("Configured the master vThunder for aVCS")
            except Exception as e:
                LOG.error("Unable to configure master vThunder aVCS")
                LOG.info(str(e))
                raise

            try:
                bc = self.client_factory(backup_vthunder)
                bc.system.action.set_vcs_device(2, 100)
                bc.system.action.set_vcs_para("192.168.0.100", "255.255.255.0")
                bc.system.action.vcs_enable()
                bc.system.action.vcs_reload()
                LOG.info("Configured the backup vThunder for aVCS")
            except Exception as e:
                LOG.error("Unable to configure backup vThunder aVCS")
                LOG.info(str(e))
                raise


class ListenersCreate(BaseVThunderTask):
    """Task to update amphora with all specified listeners' configurations."""

    def execute(self, loadbalancer, listeners, vthunder):
        """Execute updates per listener for an amphora."""
        axapi_version = acos_client.AXAPI_21 if vthunder.axapi_version == 21 else acos_client.AXAPI_30
        for listener in listeners:
            listener.load_balancer = loadbalancer
            try:
                c = self.client_factory(vthunder)
                name = loadbalancer.id + "_" + str(listener.protocol_port)
                out = c.slb.virtual_server.vport.create(
                    loadbalancer.id,
                    name,
                    listener.protocol,
                    listener.protocol_port,
                    listener.default_pool_id,
                    autosnat=True)
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
            try:
                c = self.client_factory(vthunder)
                name = loadbalancer.id + "_" + str(listener.protocol_port)
                out = c.slb.virtual_server.vport.update(
                    loadbalancer.id,
                    name,
                    listener.protocol,
                    listener.protocol_port,
                    listener.default_pool_id)
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


class PoolCreate(BaseVThunderTask):
    """Task to update amphora with all specified listeners' configurations."""

    def execute(self, pool, vthunder):
        """Execute create pool for an amphora."""
        try:
            c = self.client_factory(vthunder)
            # need to put algorithm logic
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
            c = self.client_factory(vthunder)
            # need to put algorithm logic
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
            c = self.client_factory(vthunder)
            out = c.slb.server.create(member.id, member.ip_address)
            LOG.info("Member created successfully.")
        except Exception as e:
            print(str(e))
        try:
            c = self.client_factory(vthunder)
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
            c = self.client_factory(vthunder)
            LOG.info("Member de-associated to pool successfully.")
        except Exception as e:
            print(str(e))
        try:
            c = self.client_factory(vthunder)
            out = c.slb.server.delete(member.id)
            LOG.info("Member deleted successfully.")
        except Exception as e:
            print(str(e))
            LOG.info("Error occurred")


class CreateHealthMonitorOnVthunder(BaseVThunderTask):
    """ Task to create a healthmonitor and associate it with provided pool. """

    def execute(self, vthunder):
        """ Execute create health monitor for master vthunder """
        # TODO : Length of name of healthmonitor for older vThunder devices
        axapi_version = acos_client.AXAPI_21 if vthunder.axapi_version == 21 else acos_client.AXAPI_30
        try:
            method = None
            url = None
            expect_code = None
            ##TODO : change this
            name = a10constants.VTHUNDER_UDP_HEARTBEAT 
            interval = CONF.health_manager.heartbeat_interval
            timeout = 3
            max_retries = 5
            port = CONF.health_manager.bind_port
            ipv4 = CONF.health_manager.bind_ip
            c = self.client_factory(vthunder)
            out = c.slb.hm.create(name, openstack_mappings.hm_type(c, 'UDP'),
                                interval, timeout, max_retries, method, url, expect_code,
                                port, ipv4)
            LOG.info("Heath Monitor created successfully.")
        except Exception as e:
            LOG.info(str(e))
        try:    
            c = self.client_factory(vthunder)
            name = a10constants.HM_SERVER
            ip_address = '172.17.20.52'
            health_check = a10constants.VTHUNDER_UDP_HEARTBEAT
            out = c.slb.server.create(name, ip_address, health_check=health_check)
            LOG.info("Server created successfully. Enabled health check for health monitor.")
        except Exception as e:
            LOG.info(str(e))


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
            c = self.client_factory(vthunder)
            out = c.slb.hm.create(health_mon.id[0:5],
                                  openstack_mappings.hm_type(c,
                                  health_mon.type),
                                  health_mon.delay,
                                  health_mon.timeout,
                                  health_mon.rise_threshold,
                                  method=method,
                                  url=url,
                                  expect_code=expect_code,
                                  port=port)
            LOG.info("Heath Monitor created successfully.")
        except Exception as e:
            print(str(e))
        try:
            c = self.client_factory(vthunder)
            out = c.slb.service_group.update(health_mon.pool_id,
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
            c = self.client_factory(vthunder)
            out = c.slb.service_group.update(health_mon.pool_id,
                                             health_monitor="",
                                             health_check_disable=False)
            LOG.info("Heath Monitor disassociated to pool successfully.")
        except Exception as e:
            print(str(e))
            LOG.info("Error occurred")
        try:
            c = self.client_factory(vthunder)
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
            c = self.client_factory(vthunder)
            out = c.slb.aflex_policy.create(file=filename, script=script, size=size, action=action)
            LOG.info("aFlex policy created successfully.")
        except Exception as e:
            print(str(e))
            LOG.info("Error occurred")
        try:
            # get SLB vPort
            listener = listeners[0]

            new_listener = listeners[0]
            c = self.client_factory(vthunder)
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

            update_listener = c.slb.virtual_server.vport.update(
                listener.load_balancer_id,
                listener.name,
                listener.protocol,
                listener.protocol_port,
                listener.default_pool_id,
                s_pers,
                c_pers,
                1,
                **kargs)
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
            c = self.client_factory(vthunder)
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

            update_listener = c.slb.virtual_server.vport.update(
                listener.load_balancer_id,
                listener.name,
                listener.protocol,
                listener.protocol_port,
                listener.default_pool_id,
                s_pers,
                c_pers,
                1,
                **kargs)

            LOG.info("aFlex policy detached from port successfully.")
        except Exception as e:
            print(str(e))
            LOG.info("Error occurred")

        try:
            c = self.client_factory(vthunder)
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
            c = self.client_factory(vthunder)
            out = c.slb.aflex_policy.create(file=filename, script=script, size=size, action=action)
            LOG.info("aFlex policy created successfully.")
        except Exception as e:
            print(str(e))
            LOG.info("Error occurred")
        try:
            # get SLB vPort
            listener = listeners[0]

            new_listener = listeners[0]
            c = self.client_factory(vthunder)
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

            update_listener = c.slb.virtual_server.vport.update(
                listener.load_balancer_id,
                listener.name,
                listener.protocol,
                listener.protocol_port,
                listener.default_pool_id,
                s_pers,
                c_pers,
                1,
                **kargs)
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
            c = self.client_factory(vthunder)
            out = c.slb.aflex_policy.create(file=filename, script=script, size=size, action=action)
            LOG.info("aFlex policy created successfully.")
        except Exception as e:
            print(str(e))
            LOG.info("Error occurred")
        try:
            # get SLB vPort
            listener = listeners[0]

            new_listener = listeners[0]
            c = self.client_factory(vthunder)
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

            update_listener = c.slb.virtual_server.vport.update(
                listener.load_balancer_id,
                listener.name,
                listener.protocol,
                listener.protocol_port,
                listener.default_pool_id,
                s_pers,
                c_pers,
                1,
                **kargs)
            LOG.info("Listener updated successfully.")
        except Exception as e:
            print(str(e))
            LOG.info("Error occurred")


class CheckVRRPStatus(BaseVThunderTask):
    """"Task to check VRRP status"""
    def execute(self, vthunder):
        """Execute to configure vrrp in two vThunder devices."""
        c = self.client_factory(vthunder)
        status = c.system.action.check_vrrp_status()
        return status
