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
from a10_octavia.controller.worker.tasks.decorators import axapi_client_decorator
from a10_octavia.controller.worker.tasks.policy import PolicyUtil
from a10_octavia.controller.worker.tasks.common import BaseVThunderTask



CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class VThunderComputeConnectivityWait(task.Task):
    """Task to wait for the compute instance to be up"""

    @axapi_client_decorator
    def execute(self, vthunder, amphora):
        """Execute get_info routine for a vThunder until it responds."""
        try:

            LOG.info("Attempting to connect vThunder device for connection.")
            attempts = 30
            while attempts >= 0:
                try:
                    attempts = attempts - 1
                    amp_info = self.axapi_client.system.information()
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


class AmphoraePostVIPPlug(task.Task):
    """"Task to reboot and configure vThunder device"""

    @axapi_client_decorator
    def execute(self, loadbalancer, vthunder):
        """Execute get_info routine for a vThunder until it responds."""
        try:
            save_config = self.axapi_client.system.action.write_memory()
            amp_info = self.axapi_client.system.action.reboot()
            LOG.info("Waiting for 30 seconds to trigger vThunder reboot.")
            time.sleep(30)
            LOG.info("Rebooted vThunder successfully!")
        except Exception as e:
            LOG.error("Unable to reboot vthunder device")
            LOG.info(str(e))
            raise


class AmphoraePostMemberNetworkPlug(task.Task):
    """"Task to reboot and configure vThunder device"""

    @axapi_client_decorator
    def execute(self, added_ports, loadbalancer, vthunder):
        """Execute get_info routine for a vThunder until it responds."""
        try:
            amphora_id = loadbalancer.amphorae[0].id
            if len(added_ports[amphora_id]) > 0:
                save_config = self.axapi_client.system.action.write_memory()
                amp_info = self.axapi_client.system.action.reboot()
                time.sleep(30)
                LOG.info("Rebooted vThunder successfully!")
            else:
                LOG.info("vThunder reboot is not required for member addition.")
        except Exception as e:
            LOG.error("Unable to reload vthunder device")
            LOG.info(str(e))
            raise


class EnableInterface(task.Task):
    """"Task to configure vThunder ports"""

    @axapi_client_decorator
    def execute(self, vthunder):
        """Execute get_info routine for a vThunder until it responds."""
        try:
            amp_info = self.axapi_client.system.action.setInterface(1)
            LOG.info("Configured the devices")
        except Exception as e:
            LOG.error("Unable to configure vthunder interface")
            LOG.info(str(e))


class EnableInterfaceForMembers(task.Task):
    """ Task to enable an interface associated with a member """

    @axapi_client_decorator
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
                        amp_info = self.axapi_client.system.action.setInterface(target_interface - 1)
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


class ConfigureVRRP(task.Task):
    """"Task to configure Master vThunder VRRP """

    @axapi_client_decorator
    def execute(self, vthunder, device_id, set_id):
        try:
            self.axapi_client.system.action.configureVRRP(device_id, set_id)
            LOG.debug("Successfully configured VRRP for vThunder: %s", vthunder.id)
        except Exception as e:
            LOG.exception("Failed to configure master vThunder VRRP: %s", str(e))
            raise


class ConfigureVRID(task.Task):
    """"Task to configure vThunder VRRP """

    @axapi_client_decorator
    def execute(self, vthunder, backup_vthunder, vrrp_status, vrid):
        """Execute to configure vrrp in two vThunder devices."""
        try:
            self.axapi_client.system.action.configureVRID(vrid)
            LOG.debug("Configured the master vThunder for VRID")
        except Exception as e:
            LOG.exception("Failed to configure VRRP on vthunder: %s", str(e))
            raise


class ConfigureVRRPSync(task.Task):
    """"Task to sync vThunder VRRP """
   
    @axapi_client_decorator
    def execute(self, vthunder, backup_vthunder, vrrp_status):
        """Execute to sync up vrrp in two vThunder devices."""
        if not vrrp_status:
            try:
                self.axapi_client.system.action.configSynch(backup_vthunder.ip_address, backup_vthunder.username,
                                                            backup_vthunder.password)
                LOG.debug("Waiting 30 seconds for config synch.")
                time.sleep(30)
                LOG.debug("Sync up for vThunder master")
            except Exception as e:
                LOG.exception("Failed VRRP sync: %s", str(e))
                raise


class ConfigureaVCSMaster(task.Task):
    """"Task to configure aVCS """

    @axapi_client_decorator
    def execute(self, vthunder, vrrp_status):
        """Execute to configure aVCS in two vThunder devices."""
        if not vrrp_status:
            try:
                self.axapi_client.system.action.set_vcs_device(1, 200)
                self.axapi_client.system.action.set_vcs_para("192.168.0.100", "255.255.255.0")
                self.axapi_client.system.action.vcs_enable()
                self.axapi_client.system.action.vcs_reload()
                LOG.debug("Configured the master vThunder for aVCS")
            except Exception as e:
                LOG.exception("Failed to configure master vThunder aVCS: %s", str(e))
                raise


class ConfigureaVCSBackup(task.Task):

    @axapi_client_decorator
    def execute(self, backup_vthunder, vrrp_status):

            try:
                attempts = 10
                while attempts > 0:
                    # TODO: Need this loop to be moved in acos_client with
                    # proper exception handling with all other API call loops.
                    # Currently resolves "System is Busy" error
                    try:
                        self.axapi_client.system.action.set_vcs_device(2, 100)
                        self.axapi_client.system.action.set_vcs_para("192.168.0.100", "255.255.255.0")
                        self.axapi_client.system.action.vcs_enable()
                        self.axapi_client.system.action.vcs_reload()
                        attempts = 0
                        LOG.debug("Configured the backup vThunder for aVCS")
                    except (ConnectionError, ACOSException, BadStatusLine, ReadTimeout):
                        attempts = attempts - 1
            except Exception as e:
                LOG.exception("Failed to configure backup vThunder aVCS: %s", str(e))
                raise


class CreateHealthMonitorOnVThunder(BaseVThunderTask):
    """ Task to create a healthmonitor and associate it with provided pool. """

    def execute(self, vthunder):
        """ Execute create health monitor for master vthunder """
        method = None
        url = None
        expect_code = None
        name = a10constants.OCTAVIA_HEALTH_MANAGER_CONTROLLER
        health_check = a10constants.OCTAVIA_HEALTH_MONITOR
        interval = CONF.a10_health_manager.heartbeat_interval
        timeout = CONF.a10_health_manager.health_check_timeout
        max_retries = CONF.a10_health_manager.health_check_max_retries
        port = CONF.a10_health_manager.bind_port
        ipv4 = CONF.a10_health_manager.bind_ip
        c = self.client_factory(vthunder)
        if interval < timeout:
            LOG.warning(
                "Interval should be greater than or equal to timeout. Reverting to default values. "
                "Setting interval to 10 seconds and timeout to 3 seconds.")
            interval = 10
            timeout = 3

        result = None
        try:
            result = c.slb.hm.create(health_check, openstack_mappings.hm_type(c, 'UDP'),
                                     interval, timeout, max_retries, method, url, expect_code,
                                     port, ipv4)
            LOG.info("Health Monitor created successfully.")
        except Exception as e:
            LOG.info(str(e))

        if result:
            ip_address = CONF.a10_health_manager.udp_server_ip_address
            health_check = a10constants.OCTAVIA_HEALTH_MONITOR
            try:
                c.slb.server.create(name, ip_address, health_check=health_check)
                LOG.info("Server created successfully. Enabled health check for health monitor.")
            except Exception as e:
                LOG.info(str(e))


class CheckVRRPStatus(task.Task):
    """"Task to check VRRP status"""

    @axapi_client_decorator 
    def execute(self, vthunder):
        """Execute to configure vrrp in two vThunder devices."""
        status = self.axapi_client.system.action.check_vrrp_status()
        return status
