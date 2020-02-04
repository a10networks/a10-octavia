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


class VThunderComputeConnectivityWait(BaseVThunderTask):
    """"Task to wait for the compute instance to be up."""

    def execute(self, vthunder, amphora):
        """Execute get_info routine for a vThunder until it responds."""
        try:

            LOG.info("Attempting to connect vThunder device for connection.")
            attempts = 30
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
                amp_info = c.system.action.configureVRRP(1, 1)
                LOG.info("Configured the master vThunder for VRRP")
            except Exception as e:
                LOG.error("Unable to configure master vThunder VRRP")
                LOG.info(str(e))
                raise

            try:
                c = self.client_factory(backup_vthunder)
                amp_info = c.system.action.configureVRRP(2, 1)
                LOG.info("Configured the backup vThunder for VRRP")
            except Exception as e:
                LOG.error("Unable to configure backup vThunder VRRP")
                LOG.info(str(e))
                # TODO raise - To be handled in exception handling task
        return status


class ConfigureVRID(BaseVThunderTask):
    """"Task to configure vThunder VRRP """

    def execute(self, vthunder, backup_vthunder, vrrp_status):
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
                # raise


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
                # raise


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
                out = c.slb.virtual_server.vport.create(loadbalancer.id, name, listener.protocol,
                                                        listener.protocol_port, listener.default_pool_id,
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


class CreateHealthMonitorOnVThunder(BaseVThunderTask):
    """ Task to create a healthmonitor and associate it with provided pool. """

    def execute(self, vthunder):
        """ Execute create health monitor for master vthunder """
        # TODO : Length of name of healthmonitor for older vThunder devices
        try:
            method = None
            url = None
            expect_code = None
            name = a10constants.VTHUNDER_UDP_HEARTBEAT
            interval = CONF.a10_health_manager.heartbeat_interval
            timeout = 3
            max_retries = 5
            port = CONF.a10_health_manager.bind_port
            ipv4 = CONF.a10_health_manager.bind_ip
            c = self.client_factory(vthunder)
            if interval < timeout:
                LOG.warning(
                    "Interval should be greater than or equal to timeout(3 seconds). Reverting to default(10 seconds).")
                interval = 10
            out = c.slb.hm.create(name, openstack_mappings.hm_type(c, 'UDP'),
                                  interval, timeout, max_retries, method, url, expect_code,
                                  port, ipv4)
            LOG.info("Health Monitor created successfully.")
            try:
                c = self.client_factory(vthunder)
                name = a10constants.HM_SERVER
                ip_address = CONF.a10_health_manager.udp_server_ip_address
                health_check = a10constants.VTHUNDER_UDP_HEARTBEAT
                out = c.slb.server.create(name, ip_address, health_check=health_check)
                LOG.info("Server created successfully. Enabled health check for health monitor.")
            except Exception as e:
                LOG.info(str(e))
        except Exception as e:
            LOG.info(str(e))


class CheckVRRPStatus(BaseVThunderTask):
    """"Task to check VRRP status"""

    def execute(self, vthunder):
        """Execute to configure vrrp in two vThunder devices."""
        c = self.client_factory(vthunder)
        status = c.system.action.check_vrrp_status()
        return status
