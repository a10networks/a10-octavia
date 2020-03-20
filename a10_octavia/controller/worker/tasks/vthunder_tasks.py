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

try:
    from http.client import BadStatusLine
except ImportError:
    from httplib import BadStatusLine
from requests.exceptions import ConnectionError
from requests.exceptions import ReadTimeout
from taskflow import task
import time

from oslo_config import cfg
from oslo_log import log as logging

from octavia.amphorae.driver_exceptions import exceptions as driver_except
from octavia.common import constants
from octavia.common import utils
from octavia.db import api as db_apis

from acos_client.errors import ACOSException

from a10_octavia.common import a10constants
from a10_octavia.common import openstack_mappings
from a10_octavia.controller.worker.tasks.decorators import axapi_client_decorator


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
                    self.axapi_client.system.information()
                    break
                except (ConnectionError, ACOSException, BadStatusLine, ReadTimeout):
                    attemptid = 21 - attempts
                    time.sleep(20)
                    LOG.debug("VThunder connection attempt - " + str(attemptid))
                    pass
            if attempts < 0:
                LOG.error("Failed to connect vThunder in expected amount of boot time: %s",
                          vthunder.id)
                raise ConnectionError

        except driver_except.TimeOutException:
            LOG.exception("Amphora compute instance failed to become reachable. "
                          "This either means the compute driver failed to fully "
                          "boot the instance inside the timeout interval or the "
                          "instance is not reachable via the lb-mgmt-net.")
            self.amphora_repo.update(db_apis.get_session(), amphora.id,
                                     status=constants.ERROR)
            raise


class AmphoraePostVIPPlug(task.Task):

    """Task to reboot and configure vThunder device"""

    @axapi_client_decorator
    def execute(self, loadbalancer, vthunder):
        """Execute get_info routine for a vThunder until it responds."""
        try:
            self.axapi_client.system.action.write_memory()
            self.axapi_client.system.action.reboot()
            LOG.debug("Waiting for 30 seconds to trigger vThunder reboot.")
            time.sleep(30)
            LOG.debug("vThunder rebooted successfully: %s", vthunder.id)
        except Exception as e:
            LOG.exception("Failed to reboot vthunder device: %s", str(e))
            raise


class AmphoraePostMemberNetworkPlug(task.Task):

    """Task to reboot and configure vThunder device"""

    @axapi_client_decorator
    def execute(self, added_ports, loadbalancer, vthunder):
        """Execute get_info routine for a vThunder until it responds."""
        try:
            amphora_id = loadbalancer.amphorae[0].id
            if len(added_ports[amphora_id]) > 0:
                self.axapi_client.system.action.write_memory()
                self.axapi_client.system.action.reboot()
                time.sleep(30)
                LOG.debug("vThunder rebooted successfully: %s", vthunder.id)
            else:
                LOG.debug("vThunder reboot is not required for member addition.")
        except Exception as e:
            LOG.exception("Failed to reboot vthunder device: %s", str(e))
            raise


class EnableInterface(task.Task):

    """Task to configure vThunder ports"""

    @axapi_client_decorator
    def execute(self, vthunder):
        try:
            self.axapi_client.system.action.setInterface(1)
            LOG.debug("Configured the mgmt interface for vThunder: %s", vthunder.id)
        except Exception as e:
            LOG.exception("Failed to configure  mgmt interface vThunder: %s", str(e))
            raise


class EnableInterfaceForMembers(task.Task):

    """Task to enable an interface associated with a member"""

    @axapi_client_decorator
    def execute(self, added_ports, loadbalancer, vthunder):
        """Enable specific interface of amphora"""
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
                        self.axapi_client.system.action.setInterface(target_interface - 1)
                        configured_interface = True
                        LOG.debug("Configured the new interface required for member.")
                    except (ConnectionError, ACOSException, BadStatusLine, ReadTimeout):
                        attempts = attempts - 1
            else:
                LOG.debug("Configuration of new interface is not required for member.")
        except Exception as e:
            LOG.exception("Failed to configure vthunder interface: %s", str(e))
            raise


class ConfigureVRRPMaster(task.Task):

    """Task to configure Master vThunder VRRP"""

    @axapi_client_decorator
    def execute(self, vthunder):
        try:
            self.axapi_client.system.action.configureVRRP(1, 1)
            LOG.debug("Successfully configured VRRP for vThunder: %s", vthunder.id)
        except Exception as e:
            LOG.exception("Failed to configure master vThunder VRRP: %s", str(e))
            raise


class ConfigureVRRPBackup(task.Task):

    """Task to configure Master vThunder VRRP"""

    @axapi_client_decorator
    def execute(self, vthunder):
        try:
            self.axapi_client.system.action.configureVRRP(2, 1)
            LOG.debug("Successfully configured VRRP for vThunder: %s", vthunder.id)
        except Exception as e:
            LOG.exception("Failed to configure backup vThunder VRRP: %s", str(e))
            raise


class ConfigureVRID(task.Task):

    """Task to configure vThunder VRID"""

    @axapi_client_decorator
    def execute(self, vthunder, vrid=1):
        try:
            self.axapi_client.system.action.configureVRID(vrid)
            LOG.debug("Configured the master vThunder for VRID")
        except Exception as e:
            LOG.exception("Failed to configure VRID on vthunder: %s", str(e))
            raise


class ConfigureVRRPSync(task.Task):

    """Task to sync vThunder VRRP"""

    @axapi_client_decorator
    def execute(self, vthunder, backup_vthunder):
        """Execute to sync up vrrp in two vThunder devices."""
        try:
            self.axapi_client.system.action.configSynch(backup_vthunder.ip_address,
                                                        backup_vthunder.username,
                                                        backup_vthunder.password)
            LOG.debug("Waiting 30 seconds for config synch.")
            time.sleep(30)
            LOG.debug("Sync up for vThunder master")
        except Exception as e:
            LOG.exception("Failed VRRP sync: %s", str(e))
            raise


def configure_avcs(axapi_client, device_id, device_priority, floating_ip, floating_ip_mask):
    axapi_client.system.action.set_vcs_device(device_id, device_priority)
    axapi_client.system.action.set_vcs_para(floating_ip, floating_ip_mask)
    axapi_client.system.action.vcs_enable()
    axapi_client.system.action.vcs_reload()


class ConfigureaVCSMaster(task.Task):

    """Task to configure aVCS"""

    @axapi_client_decorator
    def execute(self, vthunder, device_id=1, device_priority=200,
                floating_ip="192.168.0.100", floating_ip_mask="255.255.255.0"):
        """Execute to configure aVCS in master vThunder"""
        try:
            configure_avcs(self.axapi_client, device_id, device_priority,
                           floating_ip, floating_ip_mask)
            LOG.debug("Configured the master vThunder for aVCS: %s", vthunder.id)
        except Exception as e:
            LOG.exception("Failed to configure master vThunder aVCS: %s", str(e))
            raise


class ConfigureaVCSBackup(task.Task):

    @axapi_client_decorator
    def execute(self, vthunder, device_id=2, device_priority=100,
                floating_ip="192.168.0.100", floating_ip_mask="255.255.255.0"):
        try:
            attempts = 30
            while attempts > 0:
                # TODO(omkartelee01): Need this loop to be moved in acos_client with
                # proper exception handling with all other API call loops.
                # Currently resolves "System is Busy" error
                try:
                    configure_avcs(self.axapi_client, device_id, device_priority,
                                   floating_ip, floating_ip_mask)
                    attempts = 0
                    LOG.debug("Configured the backup vThunder for aVCS: %s", vthunder.id)
                except (ConnectionError, ACOSException, BadStatusLine, ReadTimeout):
                    attempts = attempts - 1
        except Exception as e:
            LOG.exception("Failed to configure backup vThunder aVCS: %s", str(e))
            raise


class CreateHealthMonitorOnVThunder(task.Task):

    """Task to create a Health Monitor and server for HM service"""

    @axapi_client_decorator
    def execute(self, vthunder):
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
        if interval < timeout:
            LOG.warning(
                "Interval should be greater than or equal to timeout. Reverting to default values. "
                "Setting interval to 10 seconds and timeout to 3 seconds.")
            interval = 10
            timeout = 3

        result = None
        try:
            result = self.axapi_client.slb.hm.create(health_check,
                                                     openstack_mappings.hm_type(
                                                         self.axapi_client, 'UDP'),
                                                     interval, timeout, max_retries, method, url,
                                                     expect_code, port, ipv4)
            LOG.debug("Successfully created health monitor for vThunder %s", vthunder.id)
        except Exception as e:
            LOG.debug("Failed to create health monitor: %s", str(e))

        if result:
            ip_address = CONF.a10_health_manager.udp_server_ip_address
            health_check = a10constants.OCTAVIA_HEALTH_MONITOR
            try:
                self.axapi_client.slb.server.create(name, ip_address, health_check=health_check)
                LOG.debug("Server created successfully. Enabled health check for health monitor.")
            except Exception as e:
                LOG.exception("Failed to create health monitor server: %s", str(e))


class CheckVRRPStatus(task.Task):

    """Task to check VRRP status"""

    @axapi_client_decorator
    def execute(self, vthunder):
        vrrp_status = self.axapi_client.system.action.check_vrrp_status()
        if vrrp_status:
            return True
        else:
            return False


class ConfirmVRRPStatus(task.Task):

    """Task to confirm master and backup VRRP status"""

    def execute(self, master_vrrp_status, backup_vrrp_status):
        if master_vrrp_status and master_vrrp_status:
            return True
        else:
            return False
