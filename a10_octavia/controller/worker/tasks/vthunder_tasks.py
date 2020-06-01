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


from acos_client import errors as acos_errors
try:
    import http.client as http_client
except ImportError:
    import httplib as http_client
from requests import exceptions as req_exceptions
from taskflow import task
import time

from oslo_config import cfg
from oslo_log import log as logging

from octavia.amphorae.driver_exceptions import exceptions as driver_except
from octavia.common import constants
from octavia.common import utils
from octavia.db import api as db_apis

from a10_octavia.common import a10constants
from a10_octavia.common import openstack_mappings
from a10_octavia.common import utils as a10_utils
from a10_octavia.controller.worker.tasks.decorators import axapi_client_decorator
from a10_octavia.controller.worker.tasks import utils as a10_task_utils


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class VThunderComputeConnectivityWait(task.Task):

    """Task to wait for the compute instance to be up"""

    def execute(self, vthunder, amphora):
        """Execute get_info routine for a vThunder until it responds."""
        try:
            axapi_client = a10_utils.get_axapi_client(vthunder)
            LOG.info("Attempting to connect vThunder device for connection.")
            attempts = 30
            while attempts >= 0:
                try:
                    attempts = attempts - 1
                    axapi_client.system.information()
                    break
                except (req_exceptions.ConnectionError, acos_errors.ACOSException,
                        http_client.BadStatusLine, req_exceptions.ReadTimeout):
                    attemptid = 21 - attempts
                    time.sleep(20)
                    LOG.debug("VThunder connection attempt - " + str(attemptid))
                    pass
            if attempts < 0:
                LOG.error("Failed to connect vThunder in expected amount of boot time: %s",
                          vthunder.id)
                raise req_exceptions.ConnectionError

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
                    except (req_exceptions.ConnectionError, acos_errors.ACOSException,
                            http_client.BadStatusLine, req_exceptions.ReadTimeout):
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
                except (req_exceptions.ConnectionError, acos_errors.ACOSException,
                        http_client.BadStatusLine, req_exceptions.ReadTimeout):
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


class HandleACOSPartitionChange(task.Task):
    """Task to switch to specified partition"""

    def execute(self, vthunder):
        try:
            axapi_client = a10_utils.get_axapi_client(vthunder)
            if not axapi_client.system.partition.exists(vthunder.partition_name):
                axapi_client.system.partition.create(vthunder.partition_name)
                LOG.info("Partition %s created", vthunder.partition_name)
        except acos_errors.Exists:
            pass
        except Exception as e:
            LOG.exception("Failed to create parition on vThunder: %s", str(e))
            raise

    def revert(self, vthunder, *args, **kwargs):
        try:
            axapi_client = a10_utils.get_axapi_client(vthunder)
            axapi_client.system.partition.delete(vthunder.partition_name)
        except Exception as e:
            LOG.exception("Failed to revert partition create : %s", str(e))
            raise


class TagEthernetBaseTask(task.Task):

    def __init__(self, **kwargs):
        super(TagEthernetBaseTask, self).__init__(**kwargs)
        self._network_driver = None
        self._subnet = None
        self._subnet_ip = None
        self._subnet_mask = None

    @property
    def network_driver(self):
        if self._network_driver is None:
            self._network_driver = a10_task_utils.get_a10_network_driver()
        return self._network_driver

    def reserve_ve_ip_with_neutron(self, vlan_id, subnet_id):
        ve_ip = self._get_ve_ip(vlan_id)
        if ve_ip is None:
            return

        if not a10_utils.check_ip_in_subnet_range(ve_ip, self._subnet_ip, self._subnet_mask):
            LOG.warning("Not creating neutron port, VE IP %s is out of range, subnet_ip %s,"
                        "subnet_mask %s, subnet_id %s", ve_ip, self._subnet_ip,
                        self._subnet_mask, subnet_id)
            return

        self.network_driver.create_port(self._subnet.network_id, fixed_ip=ve_ip)
        return

    def release_ve_ip_from_neutron(self, vlan_id, subnet_id):
        ve_ip = self._get_ve_ip(vlan_id)
        if ve_ip is None:
            return

        port_id = self.network_driver.get_port_id(ve_ip)
        if port_id is None:
            return

        self.network_driver.delete_port(port_id)
        return

    def _get_ve_ip(self, vlan_id):
        try:
            resp = self.axapi_client.interface.ve.get_oper(vlan_id)
            ve = resp.get('ve')
            if ve and ve.get('oper') and ve['oper'].get('ipv4_list'):
                ipv4_list = ve['oper']['ipv4_list']
                if ipv4_list:
                    return ipv4_list[0]['addr']
        except Exception as e:
            LOG.exception("Failed to get ve ip from vThunder: %s", str(e))
        return None

    def get_subnet_and_mask(self, subnet_id):
        self._subnet = self.network_driver.get_subnet(subnet_id)
        subnet_ip, subnet_mask = a10_utils.get_net_info_from_cidr(self._subnet.cidr)
        self._subnet_ip = subnet_ip
        self._subnet_mask = subnet_mask

    def _get_patched_ve_ip(self, ve_ip):
        ve_ip = ve_ip.lstrip('.')
        octets = ve_ip.split('.')
        for idx in range(4 - len(octets)):
            octets.insert(0, '0')
        ve_ip = '.'.join(octets)
        return a10_utils.merge_host_and_network_ip(self._subnet.cidr, ve_ip)

    def tag_interface(self, vlan_id, ifnum, ve_info, vlan_subnet_id_dict):
        if vlan_id not in vlan_subnet_id_dict:
            LOG.warning("vlan_id %s not in vlan_subnet_id_dict %s", vlan_id,
                        vlan_subnet_id_dict)
            return

        self.get_subnet_and_mask(vlan_subnet_id_dict[vlan_id])

        if not self.axapi_client.interface.ethernet.exists(ifnum):
            LOG.error("ethernet interface %s does not exist", ifnum)
            raise

        eth = self.axapi_client.interface.ethernet.get(ifnum)
        if 'action' not in eth or not eth['action'] == 'disable':
            LOG.warning("ethernet interface %s not enabled, enabling it", ifnum)
            self.axapi_client.interface.ethernet.update(ifnum, enable=True)

        if not self.axapi_client.vlan.exists(vlan_id):
            self.axapi_client.vlan.create(vlan_id, tagged_eths=[ifnum], veth=True)
            LOG.debug("Tagged ethernet interface %s with VLAN with id %s", ifnum, vlan_id)
        else:
            self.release_ve_ip_from_neutron(vlan_id, vlan_subnet_id_dict[vlan_id])

        if ve_info is None or 'use_dhcp' in ve_info and ve_info['use_dhcp']:
            self.axapi_client.interface.ve.update(vlan_id, dhcp=True, enable=True)
        else:
            patched_ip = self._get_patched_ve_ip(ve_info['ve_ip_address'])
            self.axapi_client.interface.ve.update(vlan_id, ip_address=patched_ip,
                                                  ip_netmask=self._subnet_mask, enable=True)
        self.reserve_ve_ip_with_neutron(vlan_id, vlan_subnet_id_dict[vlan_id])
        return

    def tag_all_interfaces(self, project_id):
        if project_id in CONF.hardware_thunder.devices:
            vthunder_conf = CONF.hardware_thunder.devices[project_id]
            if vthunder_conf.interface_vlan_map:
                network_list = self.network_driver.list_networks()
                vlan_subnet_id_dict = {}
                for network in network_list:
                    vlan_id = network.provider_segmentation_id
                    vlan_subnet_id_dict[str(vlan_id)] = network.subnets[0]
                interface_vlan_map = vthunder_conf.interface_vlan_map
                for ifnum in interface_vlan_map:
                    vlan_dict = interface_vlan_map[ifnum]
                    for vlan_id in vlan_dict:
                        self.tag_interface(vlan_id, ifnum, vlan_dict[vlan_id],
                                           vlan_subnet_id_dict)

    def get_vlan_id(self, subnet_id, is_revert):
        if self._subnet is None:
            self._subnet = self.network_driver.get_subnet(subnet_id)
        network_id = self._subnet.network_id
        network = self.network_driver.get_network(network_id)
        if network.provider_network_type != 'vlan' and not is_revert:
            raise
        return network.provider_segmentation_id

    def is_vlan_deletable(self):
        vs_list = self.axapi_client.slb.virtual_server.get(name="")
        server_list = self.axapi_client.slb.server.get(name="")

        if vs_list:
            for vs in vs_list["virtual-server-list"]:
                if a10_utils.check_ip_in_subnet_range(vs["ip-address"], self._subnet_ip,
                                                      self._subnet_mask):
                    return False

        if server_list:
            for server in server_list["server-list"]:
                if a10_utils.check_ip_in_subnet_range(server["host"], self._subnet_ip,
                                                      self._subnet_mask):
                    return False

        return True


class TagEthernetForLB(TagEthernetBaseTask):

    """Task to tag EthernetInterface on a vThunder device from lb subnet"""

    @axapi_client_decorator
    def execute(self, loadbalancer, vthunder):
        self.tag_all_interfaces(loadbalancer.project_id)

    @axapi_client_decorator
    def revert(self, loadbalancer, vthunder, *args, **kwargs):
        vlan_id = self.get_vlan_id(loadbalancer.vip.subnet_id, True)
        if self.axapi_client.vlan.exists(vlan_id):
            LOG.debug("Revert TagEthernetForLB with VLAN id %s", vlan_id)
            self.axapi_client.vlan.delete(vlan_id)
            self.release_ve_ip_from_neutron(vlan_id, loadbalancer.vip.subnet_id)


class TagEthernetForMember(TagEthernetBaseTask):

    """Task to tag EthernetInterface on a vThunder device from member subnet"""

    @axapi_client_decorator
    def execute(self, member, vthunder):
        self.tag_all_interfaces(member.project_id)

    @axapi_client_decorator
    def revert(self, member, vthunder, *args, **kwargs):
        vlan_id = self.get_vlan_id(member.subnet_id, True)
        if self.axapi_client.vlan.exists(vlan_id):
            LOG.debug("Revert TagEthernetForMember with VLAN id %s", vlan_id)
            self.axapi_client.vlan.delete(vlan_id)
            self.release_ve_ip_from_neutron(vlan_id, member.subnet_id)


class DeleteEthernetTagIfNotInUseForLB(TagEthernetBaseTask):

    """Task to untag EthernetInterface on a vThunder device from lb subnet"""

    @axapi_client_decorator
    def execute(self, loadbalancer, vthunder):
        try:
            if loadbalancer.project_id in CONF.hardware_thunder.devices:
                self.get_subnet_and_mask(loadbalancer.vip.subnet_id)
                if self.is_vlan_deletable():
                    vlan_id = self.get_vlan_id(loadbalancer.vip.subnet_id, False)
                    if self.axapi_client.vlan.exists(vlan_id):
                        LOG.debug("Delete VLAN with id %s", vlan_id)
                        self.release_ve_ip_from_neutron(vlan_id, loadbalancer.vip.subnet_id)
                        self.axapi_client.vlan.delete(vlan_id)
        except Exception as e:
            LOG.exception("Failed to delete VLAN on vThunder: %s", str(e))


class DeleteEthernetTagIfNotInUseForMember(TagEthernetBaseTask):

    """Task to untag EthernetInterface on a vThunder device from member subnet"""

    @axapi_client_decorator
    def execute(self, member, vthunder):
        try:
            if member.project_id in CONF.hardware_thunder.devices:
                self.get_subnet_and_mask(member.subnet_id)
                if self.is_vlan_deletable():
                    vlan_id = self.get_vlan_id(member.subnet_id, False)
                    if self.axapi_client.vlan.exists(vlan_id):
                        LOG.info("Delete VLAN with id %s", vlan_id)
                        self.release_ve_ip_from_neutron(vlan_id, member.subnet_id)
                        self.axapi_client.vlan.delete(vlan_id)
        except Exception as e:
            LOG.exception("Failed to delete VLAN on vThunder: %s", str(e))
