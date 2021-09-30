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


import acos_client
from acos_client import errors as acos_errors
import datetime
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
from a10_octavia.common import exceptions
from a10_octavia.common import openstack_mappings
from a10_octavia.common import utils as a10_utils
from a10_octavia.controller.worker.tasks.decorators import activate_partition
from a10_octavia.controller.worker.tasks.decorators import axapi_client_decorator
from a10_octavia.controller.worker.tasks.decorators import axapi_client_decorator_for_revert
from a10_octavia.controller.worker.tasks.decorators import device_context_switch_decorator
from a10_octavia.controller.worker.tasks import utils as a10_task_utils
from a10_octavia.db import repositories as a10_repo


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class VThunderBaseTask(task.Task):

    def __init__(self, **kwargs):
        super(VThunderBaseTask, self).__init__(**kwargs)
        self._network_driver = None
        self.vthunder_repo = a10_repo.VThunderRepository()
        self.loadbalancer_repo = a10_repo.LoadBalancerRepository()

    @property
    def network_driver(self):
        if self._network_driver is None:
            self._network_driver = a10_utils.get_network_driver()
        return self._network_driver


class VThunderComputeConnectivityWait(VThunderBaseTask):
    """Task to wait for the compute instance to be up"""

    def execute(self, vthunder, amphora):
        """Execute get_info routine for a vThunder until it responds."""
        try:
            if vthunder:
                axapi_client = a10_utils.get_axapi_client(vthunder)
                LOG.info("Attempting to connect vThunder device for connection.")
                attempts = CONF.a10_controller_worker.amp_active_retries
                while attempts >= 0:
                    try:
                        attempts = attempts - 1
                        axapi_client.system.information()
                        break
                    except a10_task_utils.thunder_busy_exceptions():
                        # acos-client already wait default_axapi_timeout for these exceptions.
                        axapi_timeout = CONF.vthunder.default_axapi_timeout
                        attempt_wait = CONF.a10_controller_worker.amp_active_wait_sec
                        if axapi_timeout > attempt_wait:
                            attempts = attempts - (axapi_timeout / attempt_wait - 1)
                        LOG.debug("VThunder connection retry cnt:" + str(attempts))
                    except (acos_errors.ACOSException, http_client.BadStatusLine):
                        time.sleep(CONF.a10_controller_worker.amp_active_wait_sec)
                        LOG.debug("VThunder connection retry cnt:" + str(attempts))
                if attempts < 0:
                    LOG.error("Failed to connect vThunder in expected amount of boot time: %s",
                              vthunder.id)
                    raise req_exceptions.ConnectionError

        except driver_except.TimeOutException as e:
            LOG.exception("Amphora compute instance failed to become reachable. "
                          "This either means the compute driver failed to fully "
                          "boot the instance inside the timeout interval or the "
                          "instance is not reachable via the lb-mgmt-net.")
            self.amphora_repo.update(db_apis.get_session(), amphora.id,
                                     status=constants.ERROR)
            raise e


class AmphoraePostVIPPlug(VThunderBaseTask):
    """Task to reboot and configure vThunder device"""

    @axapi_client_decorator
    def execute(self, loadbalancer, vthunder, added_ports):
        """Execute get_info routine for a vThunder until it responds."""
        amphora_id = loadbalancer.amphorae[0].id
        if added_ports and amphora_id in added_ports and len(added_ports[amphora_id]) > 0:
            try:
                self.axapi_client.system.action.write_memory()
                self.axapi_client.system.action.reload_reboot_for_interface_attachment(
                    vthunder.acos_version)
                LOG.debug("Waiting for 30 seconds to trigger vThunder reload.")
                time.sleep(30)
                LOG.debug("Successfully reloaded/rebooted vThunder: %s", vthunder.id)
            except (acos_errors.ACOSException, req_exceptions.ConnectionError) as e:
                LOG.exception("Failed to save configuration and reboot on vThunder "
                              "for amphora id: %s", vthunder.amphora_id)
                raise e


class AllowL2DSR(VThunderBaseTask):
    """Task to add wildcat address in allowed_address_pair for L2DSR"""

    def execute(self, subnet, amphora, lb_count_flavor, flavor_data=None):
        if CONF.vthunder.l2dsr_support:
            for amp in amphora:
                self.network_driver.allow_use_any_source_ip_on_egress(subnet.network_id, amp)

        if flavor_data:
            deployment = flavor_data.get('deployment')
            if deployment and 'dsr_type' in deployment:
                if deployment['dsr_type'] == "l2dsr_transparent":
                    for amp in amphora:
                        self.network_driver.allow_use_any_source_ip_on_egress(
                            subnet.network_id, amp)

    def revert(self, subnet, amphora, lb_count_flavor, flavor_data=None, *args, **kwargs):
        if lb_count_flavor > 1:
            return

        if flavor_data:
            deployment = flavor_data.get('deployment')
            if deployment and 'dsr_type' in deployment:
                if deployment['dsr_type'] == "l2dsr_transparent":
                    for amp in amphora:
                        self.network_driver.remove_any_source_ip_on_egress(subnet.network_id, amp)


class DeleteL2DSR(VThunderBaseTask):
    """Task to delete wildcat address in allowed_address_pair for L2DSR"""

    def execute(self, subnet, amphora, lb_count_flavor, lb_count_subnet, flavor_data=None):
        if CONF.vthunder.l2dsr_support:
            if lb_count_subnet <= 1:
                for amp in amphora:
                    self.network_driver.remove_any_source_ip_on_egress(subnet.network_id, amp)
        else:
            if lb_count_flavor <= 1 and flavor_data:
                deployment = flavor_data.get('deployment')
                if deployment and 'dsr_type' in deployment:
                    if deployment['dsr_type'] == "l2dsr_transparent":
                        for amp in amphora:
                            self.network_driver.remove_any_source_ip_on_egress(
                                subnet.network_id, amp)


class UpdateL2DSR(VThunderBaseTask):
    """Task to update wildcat address in allowed_address_pair for L2DSR"""

    def execute(self, subnet, amphora, member_count, l2dsr_flavor):
        if CONF.vthunder.l2dsr_support:
            for amp in amphora:
                self.network_driver.allow_use_any_source_ip_on_egress(subnet.network_id, amp)
        else:
            if not l2dsr_flavor:
                if (CONF.vthunder.slb_no_snat_support and member_count < 1) or \
                        (not CONF.vthunder.slb_no_snat_support):
                    for amp in amphora:
                        self.network_driver.remove_any_source_ip_on_egress(subnet.network_id, amp)


class AllowLoadbalancerForwardWithAnySource(VThunderBaseTask):
    """Task to add wildcat address in allowed_address_pair to allow any SNAT"""

    def execute(self, member, amphora):
        if member.subnet_id:
            subnet = self.network_driver.get_subnet(member.subnet_id)
            if CONF.vthunder.slb_no_snat_support:
                for amp in amphora:
                    self.network_driver.allow_use_any_source_ip_on_egress(subnet.network_id, amp)


class UpdateLoadbalancerForwardWithAnySource(VThunderBaseTask):
    """Task to update wildcat address in allowed_address_pair to allow any SNAT"""

    def execute(self, subnet, amphora, lb_count_subnet, l2dsr_flavor):
        if CONF.vthunder.slb_no_snat_support:
            for amp in amphora:
                self.network_driver.allow_use_any_source_ip_on_egress(subnet.network_id, amp)
        else:
            if not l2dsr_flavor:
                if (CONF.vthunder.l2dsr_support and lb_count_subnet < 1) or \
                        not CONF.vthunder.l2dsr_support:
                    for amp in amphora:
                        self.network_driver.remove_any_source_ip_on_egress(subnet.network_id, amp)


class AmphoraePostMemberNetworkPlug(VThunderBaseTask):
    """Task to reboot and configure vThunder device"""

    @axapi_client_decorator
    def execute(self, added_ports, loadbalancer, vthunder):
        """Execute get_info routine for a vThunder until it responds."""
        try:
            amphora_id = loadbalancer.amphorae[0].id
            if added_ports and amphora_id in added_ports and len(added_ports[amphora_id]) > 0:
                self.axapi_client.system.action.write_memory()
                self.axapi_client.system.action.reload_reboot_for_interface_attachment(
                    vthunder.acos_version)
                LOG.debug("Waiting for 30 seconds to trigger vThunder reload/reboot.")
                time.sleep(30)
                LOG.debug("Successfully rebooted/reloaded vThunder: %s", vthunder.id)
            else:
                LOG.debug("vThunder reboot/relaod is not required for member addition.")
        except (acos_errors.ACOSException, req_exceptions.ConnectionError) as e:
            LOG.exception("Failed to reboot/reload vthunder device: %s", str(e))
            raise e


class EnableInterface(VThunderBaseTask):
    """Task to configure vThunder ports"""

    @axapi_client_decorator
    def execute(self, vthunder, loadbalancer, added_ports, ifnum_master=None, ifnum_backup=None):
        topology = CONF.a10_controller_worker.loadbalancer_topology
        amphora_id = loadbalancer.amphorae[0].id
        compute_id = loadbalancer.amphorae[0].compute_id
        network_driver = utils.get_network_driver()
        nics = network_driver.get_plugged_networks(compute_id)
        lb_exists_flag = self.loadbalancer_repo.check_lb_exists_in_project(
            db_apis.get_session(),
            loadbalancer.project_id)

        if not lb_exists_flag:
            added_ports[amphora_id] = []
            added_ports[amphora_id].append(nics[1])

        try:
            if added_ports and amphora_id in added_ports and len(added_ports[amphora_id]) > 0:
                if (not lb_exists_flag and topology == "ACTIVE_STANDBY") or topology == "SINGLE":
                    interfaces = self.axapi_client.interface.get_list()
                    for i in range(len(interfaces['interface']['ethernet-list'])):
                        if interfaces['interface']['ethernet-list'][i]['action'] == "disable":
                            ifnum = interfaces['interface']['ethernet-list'][i]['ifnum']
                            self.axapi_client.system.action.setInterface(ifnum)
                    LOG.debug("Configured the ethernet interface for vThunder: %s", vthunder.id)
                else:
                    if ifnum_master:
                        for i in range(len(ifnum_master)):
                            self.axapi_client.system.action.setInterface(ifnum_master[i])
                            LOG.debug("Configured the ethernet interface for "
                                      "master vThunder: %s", vthunder.id)
                    elif ifnum_backup:
                        for i in range(len(ifnum_backup)):
                            self.axapi_client.system.action.setInterface(ifnum_backup[i])
                            LOG.debug("Configured the ethernet interface for "
                                      "backup vThunder: %s", vthunder.id)
        except(acos_errors.ACOSException, req_exceptions.ConnectionError) as e:
            LOG.exception("Failed to configure ethernet interface vThunder: %s", str(e))
            raise e


class EnableInterfaceForMembers(VThunderBaseTask):
    """Task to enable an interface associated with a member"""

    @axapi_client_decorator
    def execute(self, added_ports, loadbalancer, vthunder):
        """Enable specific interface of amphora"""
        try:
            amphora_id = loadbalancer.amphorae[0].id
            compute_id = loadbalancer.amphorae[0].compute_id
            network_driver = utils.get_network_driver()
            nics = network_driver.get_plugged_networks(compute_id)
            if added_ports and amphora_id in added_ports and len(added_ports[amphora_id]) > 0:
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
        except (acos_errors.ACOSException, req_exceptions.ConnectionError) as e:
            LOG.exception("Failed to configure vthunder interface: %s", str(e))
            raise e


class ConfigureVRRPMaster(VThunderBaseTask):
    """Task to configure Master vThunder VRRP"""

    @axapi_client_decorator
    def execute(self, vthunder, set_id=1):
        try:
            self.axapi_client.system.action.configureVRRP(1, set_id)
            LOG.debug("Successfully configured VRRP for vThunder: %s", vthunder.id)
        except (acos_errors.ACOSException, req_exceptions.ConnectionError) as e:
            LOG.exception("Failed to configure master vThunder VRRP: %s", str(e))
            raise e


class ConfigureVRRPBackup(VThunderBaseTask):
    """Task to configure backup vThunder VRRP"""

    @axapi_client_decorator
    def execute(self, vthunder, set_id=1):
        try:
            self.axapi_client.system.action.configureVRRP(2, set_id)
            LOG.debug("Successfully configured VRRP for vThunder: %s", vthunder.id)
        except (acos_errors.ACOSException, req_exceptions.ConnectionError) as e:
            LOG.exception("Failed to configure backup vThunder VRRP: %s", str(e))
            raise e


class ConfigureVRID(VThunderBaseTask):
    """Task to configure vThunder VRID"""

    @axapi_client_decorator
    def execute(self, vthunder):
        try:
            vrid = CONF.a10_global.vrid
            if not self.axapi_client.vrrpa.exists(vrid):
                self.axapi_client.system.action.configureVRID(vrid)
            LOG.debug("Configured the master vThunder for VRID")
        except (acos_errors.ACOSException, req_exceptions.ConnectionError) as e:
            LOG.exception("Failed to configure VRID on vthunder: %s", str(e))
            raise e


def configure_avcs(axapi_client, device_id, device_priority, floating_ip, floating_ip_mask):
    axapi_client.system.action.set_vcs_device(device_id, device_priority)
    axapi_client.system.action.set_vcs_para(floating_ip, floating_ip_mask)
    axapi_client.system.action.vcs_enable()
    axapi_client.system.action.write_memory()
    axapi_client.system.action.vcs_reload()


class ConfigureaVCSMaster(VThunderBaseTask):
    """Task to configure aVCS on master vThunder"""

    @axapi_client_decorator
    def execute(self, vthunder, device_id=1, device_priority=200,
                floating_ip="192.168.0.100", floating_ip_mask="255.255.255.0"):
        """Execute to configure aVCS in master vThunder"""
        try:
            configure_avcs(self.axapi_client, device_id, device_priority,
                           floating_ip, floating_ip_mask)
            LOG.debug("Configured the master vThunder for aVCS: %s", vthunder.id)
        except (acos_errors.ACOSException, req_exceptions.ConnectionError) as e:
            LOG.exception("Failed to configure master vThunder aVCS: %s", str(e))
            raise e


class ConfigureaVCSBackup(VThunderBaseTask):
    """Task to configure aVCS on backup vThunder"""

    @axapi_client_decorator
    def execute(self, vthunder, device_id=2, device_priority=100,
                floating_ip="192.168.0.100", floating_ip_mask="255.255.255.0"):
        try:
            attempts = CONF.a10_controller_worker.amp_vcs_retries
            while attempts >= 0:
                try:
                    attempts = attempts - 1
                    configure_avcs(self.axapi_client, device_id, device_priority,
                                   floating_ip, floating_ip_mask)
                    attempts = 0
                    LOG.debug("Configured the backup vThunder for aVCS: %s", vthunder.id)
                    break
                except a10_task_utils.thunder_busy_exceptions() as e:
                    # acos-client already wait default_axapi_timeout for these exceptions.
                    axapi_timeout = CONF.vthunder.default_axapi_timeout
                    attempt_wait = CONF.a10_controller_worker.amp_vcs_wait_sec
                    if axapi_timeout > attempt_wait:
                        attempts = attempts - (axapi_timeout / attempt_wait - 1)
                    if attempts < 0:
                        raise e
                except Exception as e:
                    if attempts < 0:
                        raise e
                    time.sleep(CONF.a10_controller_worker.amp_vcs_wait_sec)
        except (acos_errors.ACOSException, req_exceptions.ConnectionError) as e:
            LOG.exception("Failed to configure backup vThunder aVCS: %s", str(e))
            raise e


class CreateHealthMonitorOnVThunder(VThunderBaseTask):
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
        except (acos_errors.ACOSException, req_exceptions.ConnectionError) as e:
            LOG.exception("Failed to create health monitor: %s", str(e))
            raise e

        if result:
            ip_address = CONF.a10_health_manager.udp_server_ip_address
            health_check = a10constants.OCTAVIA_HEALTH_MONITOR
            try:
                self.axapi_client.slb.server.create(name, ip_address, health_check=health_check)
                LOG.debug("Server created successfully. Enabled health check for health monitor.")
            except (acos_errors.ACOSException, req_exceptions.ConnectionError) as e:
                LOG.exception("Failed to create health monitor server: %s", str(e))
                raise e


class CheckVRRPStatus(VThunderBaseTask):
    """Task to check VRRP status"""

    @axapi_client_decorator
    def execute(self, vthunder):
        try:
            vrrp_status = self.axapi_client.system.action.check_vrrp_status()
            if vrrp_status:
                return True
            else:
                return False
        except (acos_errors.ACOSException, req_exceptions.ConnectionError) as e:
            LOG.exception("Failed to get VRRP status for vThunder %s due to: %s",
                          vthunder.ip_address, str(e))
            raise e


class ConfirmVRRPStatus(VThunderBaseTask):
    """Task to confirm master and backup VRRP status"""

    def execute(self, master_vrrp_status, backup_vrrp_status):
        if master_vrrp_status and backup_vrrp_status:
            return True
        else:
            return False


class HandleACOSPartitionChange(VThunderBaseTask):
    """Task to switch to specified partition"""

    def _get_hmt_partition_name(self, loadbalancer):
        partition_name = loadbalancer.project_id[:14]
        if CONF.a10_global.use_parent_partition:
            parent_project_id = a10_utils.get_parent_project(loadbalancer.project_id)
            if parent_project_id:
                if parent_project_id != 'default':
                    partition_name = parent_project_id[:14]
            else:
                LOG.error(
                    "The parent project for project %s does not exist. ",
                    loadbalancer.project_id)
                raise exceptions.ParentProjectNotFound(loadbalancer.project_id)
        else:
            LOG.warning(
                "Hierarchical multitenancy is disabled, use_parent_partition "
                "configuration will not be applied for loadbalancer: %s",
                loadbalancer.id)
        return partition_name

    def execute(self, loadbalancer, vthunder_config):
        axapi_client = a10_utils.get_axapi_client(vthunder_config)

        partition_name = vthunder_config.partition_name
        hierarchical_mt = vthunder_config.hierarchical_multitenancy
        if hierarchical_mt == 'enable':
            partition_name = self._get_hmt_partition_name(loadbalancer)

        try:
            partition = axapi_client.system.partition.get(partition_name)
            partition_name = partition['partition-name']
        except acos_errors.NotFound:
            partition = None

        # Check if partition is using old n-lbaas length
        if partition is None and hierarchical_mt == 'enable':
            try:
                partition = axapi_client.system.partition.get(partition_name[:13])
                partition_name = partition['partition-name']
            except acos_errors.NotFound:
                partition = None

        if partition is None:
            try:
                axapi_client.system.partition.create(partition_name)
                axapi_client.system.action.write_memory(partition="shared")
                LOG.info("Partition %s created", partition_name)
            except (acos_errors.ACOSException, req_exceptions.ConnectionError) as e:
                LOG.exception("Failed to create parition on vThunder: %s", str(e))
                raise e
        elif partition.get("status") == "Not-Active":
            raise exceptions.PartitionNotActiveError(partition, vthunder_config.ip_address)

        vthunder_config.partition_name = partition_name
        return vthunder_config


class SetupDeviceNetworkMap(VThunderBaseTask):
    """Task to setup device_network_map in vthunder to contain only vcs devices with known
       states and have Master device object at index 0.
    """

    default_provides = a10constants.VTHUNDER

    @axapi_client_decorator
    def execute(self, vthunder):
        if not vthunder:
            return
        device_name = ''.join([a10constants.DEVICE_KEY_PREFIX,
                               vthunder.device_name]) if vthunder.device_name else ''
        vthunder_conf = None
        if isinstance(CONF.hardware_thunder.devices, dict):
            vthunder_conf = (CONF.hardware_thunder.devices.get(device_name) or
                             CONF.hardware_thunder.devices.get(vthunder.project_id))
        if vthunder_conf is not None:
            device_network_map = vthunder_conf.device_network_map

            # Case when device network map is not provided/length is 0
            if not device_network_map:
                return vthunder

            try:
                resp = self.axapi_client.system.action.get_vcs_summary_oper()
            except (acos_errors.ACOSException, req_exceptions.ConnectionError) as e:
                LOG.exception("Failed to get vcs summary oper: %s", str(e))
                raise e

            if resp and 'vcs-summary' in resp and 'oper' in resp['vcs-summary']:
                oper = resp['vcs-summary']['oper']
                if oper.get('vcs-enabled') != 'Yes':
                    if len(device_network_map) == 1:
                        device_network_map[0].state = 'Master'
                        vthunder.device_network_map.append(device_network_map[0])
                        return vthunder
                    else:
                        raise exceptions.InvalidVCSDeviceCount(len(device_network_map))
                devices = {}
                for device in device_network_map:
                    devices[device.vcs_device_id] = device
                for member in oper.get('member-list'):
                    if member.get('id') not in devices:
                        continue
                    device = devices[member.get('id')]
                    del devices[member.get('id')]
                    if 'vMaster' in member.get('state'):
                        device.state = 'Master'
                        vthunder.device_network_map.insert(0, device)
                    elif 'vBlade' in member.get('state'):
                        device.state = 'vBlade'
                        vthunder.device_network_map.append(device)
                    elif 'Unknown' in member.get('state'):
                        LOG.warning("Not configuring VE VLAN for device id:%s state:Unknown",
                                    str(member.get('id')))
                if len(devices.keys()) > 0:
                    device_ids = ''
                    for key in devices:
                        device_ids = device_ids.join(str(key))
                        device_ids = device_ids.join(' ')
                    raise exceptions.MissingVCSDeviceConfig(device_ids)
        return vthunder


class TagInterfaceBaseTask(VThunderBaseTask):

    def __init__(self, **kwargs):
        super(TagInterfaceBaseTask, self).__init__(**kwargs)
        self._network_driver = None
        self._subnet = None
        self._subnet_ip = None
        self._subnet_mask = None

    def reserve_ve_ip_with_neutron(self, vlan_id, subnet_id, vthunder, device_id=None):
        ve_ip = self._get_ve_ip(vlan_id, vthunder, device_id)
        if ve_ip is None:
            LOG.warning("Failed to reserve port from neutron for device %s", str(device_id))
            return None

        if not a10_utils.check_ip_in_subnet_range(ve_ip, self._subnet_ip, self._subnet_mask):
            LOG.warning("Not creating neutron port, VE IP %s is out of range, subnet_ip %s,"
                        "subnet_mask %s, subnet_id %s", ve_ip, self._subnet_ip,
                        self._subnet_mask, subnet_id)
            return None

        self.network_driver.create_port(self._subnet.network_id, fixed_ip=ve_ip)

    def release_ve_ip_from_neutron(self, vlan_id, subnet_id, vthunder, device_id=None):
        ve_ip = self._get_ve_ip(vlan_id, vthunder, device_id)
        port_id = self.network_driver.get_port_id_from_ip(ve_ip)
        if ve_ip and port_id:
            self.network_driver.delete_port(port_id)
        else:
            LOG.warning("Failed to release ve port from neutron for device %s", str(device_id))

    def _get_ve_ip(self, vlan_id, vthunder, device_id=None):
        master_device_id = vthunder.device_network_map[0].vcs_device_id
        if master_device_id != device_id:
            api_ver = acos_client.AXAPI_21 if vthunder.axapi_version == 21 else acos_client.AXAPI_30
            device_obj = vthunder.device_network_map[1]
            client = acos_client.Client(device_obj.mgmt_ip_address, api_ver,
                                        vthunder.username, vthunder.password,
                                        timeout=CONF.vthunder.default_axapi_timeout)
            if vthunder.partition_name != "shared":
                activate_partition(client, vthunder.partition_name)
            close_axapi_client = True
        else:
            client = self.axapi_client
            close_axapi_client = False
        try:
            resp = client.interface.ve.get_oper(vlan_id)
            if close_axapi_client:
                client.session.close()
            ve = resp.get('ve')
            if ve and ve.get('oper') and ve['oper'].get('ipv4_list'):
                ipv4_list = ve['oper']['ipv4_list']
                if ipv4_list:
                    return ipv4_list[0]['addr']
        except (acos_errors.ACOSException, req_exceptions.ConnectionError) as e:
            LOG.warning("Failed to get ve ip from device id %s: %s", str(device_id), str(e))

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

    @device_context_switch_decorator
    def check_ve_ip_exists(self, vlan_id, config_ve_ip):
        if self.axapi_client.vlan.exists(vlan_id):
            try:
                ve = self.axapi_client.interface.ve.get(vlan_id)
            except Exception:
                return False
            ve_ip = ve['ve'].get('ip') if ve['ve'].get('ip') else None
            if config_ve_ip == 'dhcp':
                if ve_ip and ve_ip.get('dhcp'):
                    return True
            else:
                if ve_ip and ve_ip.get('address-list'):
                    existing_ve_ip = ve_ip.get('address-list')[0].get('ipv4-address')
                    if self._get_patched_ve_ip(config_ve_ip) == existing_ve_ip:
                        return True
            return False

    @device_context_switch_decorator
    def delete_device_vlan(self, vlan_id, subnet_id, vthunder, device_id=None,
                           master_device_id=None):
        if self.axapi_client.vlan.exists(vlan_id):
            LOG.debug("Delete VLAN with id %s", vlan_id)
            self.release_ve_ip_from_neutron(vlan_id, subnet_id, vthunder, device_id)
            self.axapi_client.vlan.delete(vlan_id)

    def tag_interface(self, is_trunk, create_vlan_id, vlan_id, ifnum, ve_info,
                      vlan_subnet_id_dict, vthunder, device_id=None, master_device_id=None):
        if vlan_id not in vlan_subnet_id_dict:
            LOG.warning("vlan_id %s not in vlan_subnet_id_dict %s", vlan_id,
                        vlan_subnet_id_dict)
            return None

        self.get_subnet_and_mask(vlan_subnet_id_dict[vlan_id])

        if not is_trunk:
            current_partition = self.axapi_client.current_partition
            if current_partition != "shared":
                self.axapi_client.system.partition.active("shared")
            if not self.axapi_client.interface.ethernet.exists(ifnum):
                LOG.error("ethernet interface %s does not exist", ifnum)
            eth = self.axapi_client.interface.ethernet.get(ifnum)
            if ('ethernet' in eth and ('action' not in eth['ethernet'] or
                                       eth['ethernet']['action'] == 'disable')):
                LOG.warning("ethernet interface %s not enabled, enabling it", ifnum)
                self.axapi_client.interface.ethernet.update(ifnum, enable=True)
            self.axapi_client.system.partition.active(current_partition)

        vlan_exists = self.axapi_client.vlan.exists(vlan_id)
        if not vlan_exists and str(create_vlan_id) != vlan_id:
            return None
        if not vlan_exists:
            if is_trunk:
                self.axapi_client.vlan.create(vlan_id, tagged_trunks=[ifnum], veth=True)
                LOG.debug("Tagged ethernet interface %s with VLAN with id %s", ifnum, vlan_id)
            else:
                self.axapi_client.vlan.create(vlan_id, tagged_eths=[ifnum], veth=True)
                LOG.debug("Tagged trunk interface %s with VLAN with id %s", ifnum, vlan_id)
        else:
            self.release_ve_ip_from_neutron(vlan_id, vlan_subnet_id_dict[vlan_id], vthunder,
                                            device_id)

        ve_ip_exist = self.check_ve_ip_exists(vlan_id, ve_info)
        if not ve_ip_exist:
            self.axapi_client.interface.ve.delete(vlan_id)
            if ve_info == 'dhcp':
                self.axapi_client.interface.ve.create(vlan_id, dhcp=True, enable=True)
            else:
                patched_ip = self._get_patched_ve_ip(ve_info)
                self.axapi_client.interface.ve.create(vlan_id, ip_address=patched_ip,
                                                      ip_netmask=self._subnet_mask, enable=True)
        self.reserve_ve_ip_with_neutron(vlan_id, vlan_subnet_id_dict[vlan_id], vthunder,
                                        device_id)

    @device_context_switch_decorator
    def tag_device_interfaces(self, create_vlan_id, vlan_subnet_id_dict, device_obj,
                              vthunder, device_id=None, master_device_id=None):
        all_vlan_ids = []
        for eth_interface in device_obj.ethernet_interfaces:
            ifnum = str(eth_interface.interface_num)
            assert len(eth_interface.tags) == len(eth_interface.ve_ips)
            for i in range(len(eth_interface.tags)):
                tag = str(eth_interface.tags[i])
                all_vlan_ids.append(tag)
                ve_ip = eth_interface.ve_ips[i]
                self.tag_interface(False, create_vlan_id, tag, ifnum, ve_ip,
                                   vlan_subnet_id_dict, vthunder, device_id=device_id)
        for trunk_interface in device_obj.trunk_interfaces:
            ifnum = str(trunk_interface.interface_num)
            assert len(trunk_interface.tags) == len(trunk_interface.ve_ips)
            for i in range(len(trunk_interface.tags)):
                tag = str(trunk_interface.tags[i])
                all_vlan_ids.append(tag)
                ve_ip = trunk_interface.ve_ips[i]
                self.tag_interface(True, create_vlan_id, tag, ifnum, ve_ip,
                                   vlan_subnet_id_dict, vthunder, device_id=device_id)
        if str(create_vlan_id) not in all_vlan_ids:
            LOG.warning('Settings for vlan id %s is not present in `a10-octavia.conf`',
                        str(create_vlan_id))

    def tag_interfaces(self, vthunder, create_vlan_id):
        if vthunder and vthunder.device_network_map:
            network_list = self.network_driver.list_networks()
            vlan_subnet_id_dict = {}
            for network in network_list:
                vlan_id = network.provider_segmentation_id
                vlan_subnet_id_dict[str(vlan_id)] = network.subnets[0]
            master_device_id = vthunder.device_network_map[0].vcs_device_id
            for device_obj in vthunder.device_network_map:
                try:
                    self.tag_device_interfaces(create_vlan_id, vlan_subnet_id_dict, device_obj,
                                               vthunder, device_id=device_obj.vcs_device_id,
                                               master_device_id=master_device_id)
                except (acos_errors.ACOSException, req_exceptions.ConnectionError) as e:
                    if master_device_id != device_obj.vcs_device_id:
                        LOG.warning("Failed to tag interfaces of device id %s: %s",
                                    str(device_obj.vcs_device_id), str(e))
                    else:
                        raise e

    def get_vlan_id(self, subnet_id, is_revert):
        self.get_subnet_and_mask(subnet_id)
        network_id = self._subnet.network_id
        network = self.network_driver.get_network(network_id)
        if network.provider_network_type != 'vlan' and not is_revert:
            LOG.warning('provider_network_type not set to vlan for openstack network: %s',
                        network_id)
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


class TagInterfaceForLB(TagInterfaceBaseTask):
    """Task to tag Ethernet/Trunk Interface on a vThunder device from lb subnet"""

    @axapi_client_decorator
    def execute(self, loadbalancer, vthunder):
        try:
            vlan_id = self.get_vlan_id(loadbalancer.vip.subnet_id, False)
            self.tag_interfaces(vthunder, vlan_id)
        except (acos_errors.ACOSException, req_exceptions.ConnectionError) as e:
            LOG.exception("Failed to TagInterfaceForLB: %s", str(e))
            raise e

    @axapi_client_decorator_for_revert
    def revert(self, loadbalancer, vthunder, *args, **kwargs):
        try:
            if vthunder and vthunder.device_network_map:
                vlan_id = self.get_vlan_id(loadbalancer.vip.subnet_id, False)
                if self.is_vlan_deletable():
                    LOG.warning("Revert TagInterfaceForLB with VLAN id %s", vlan_id)
                    master_device_id = vthunder.device_network_map[0].vcs_device_id
                    for device_obj in vthunder.device_network_map:
                        self.delete_device_vlan(vlan_id, loadbalancer.vip.subnet_id, vthunder,
                                                device_id=device_obj.vcs_device_id,
                                                master_device_id=master_device_id)
        except req_exceptions.ConnectionError:
            LOG.exception("Failed to connect A10 Thunder device: %s", vthunder.ip_address)
        except Exception as e:
            LOG.exception("Failed to revert VLAN %s delete on Thunder: %s", vlan_id, str(e))


class TagInterfaceForMember(TagInterfaceBaseTask):
    """Task to tag Ethernet/Trunk Interface on a vThunder device from member subnet"""

    @axapi_client_decorator
    def execute(self, member, vthunder):
        member_list = member if isinstance(member, list) else [member]
        subnet_list = []
        for member in member_list:
            if member.subnet_id not in subnet_list:
                if not member.subnet_id:
                    LOG.warning("Subnet id argument was not specified during "
                                "issuance of create command/API call for member %s. "
                                "Skipping TagInterfaceForMember task", member.id)
                    continue
                try:
                    vlan_id = self.get_vlan_id(member.subnet_id, False)
                    self.tag_interfaces(vthunder, vlan_id)
                    subnet_list.append(member.subnet_id)
                    LOG.debug("Successfully tagged interface with VLAN id %s for member %s",
                              str(vlan_id), member.id)
                except (acos_errors.ACOSException, req_exceptions.ConnectionError) as e:
                    LOG.exception("Failed to tag interface with VLAN id %s for member %s",
                                  str(vlan_id), member.id)
                    raise e

    @axapi_client_decorator_for_revert
    def revert(self, member, vthunder, *args, **kwargs):
        member_list = member if isinstance(member, list) else [member]
        for member in member_list:
            if not member.subnet_id:
                LOG.warning("Subnet id argument was not specified during "
                            "issuance of create command/API call for member %s. "
                            "Skipping TagInterfaceForMember task", member.id)
                continue
            try:
                if vthunder and vthunder.device_network_map:
                    vlan_id = self.get_vlan_id(member.subnet_id, False)
                    if self.is_vlan_deletable():
                        LOG.warning("Reverting tag interface for member with VLAN id %s", vlan_id)
                        master_device_id = vthunder.device_network_map[0].vcs_device_id
                        for device_obj in vthunder.device_network_map:
                            self.delete_device_vlan(vlan_id, member.subnet_id, vthunder,
                                                    device_id=device_obj.vcs_device_id,
                                                    master_device_id=master_device_id)
            except req_exceptions.ConnectionError:
                LOG.exception("Failed to connect A10 Thunder device: %s", vthunder.ip_address)
            except Exception as e:
                LOG.exception("Failed to delete VLAN %s due to %s", str(vlan_id), str(e))


class DeleteInterfaceTagIfNotInUseForLB(TagInterfaceBaseTask):
    """Task to untag Ethernet/Trunk Interface on a vThunder device from lb subnet"""

    @axapi_client_decorator
    def execute(self, loadbalancer, vthunder):
        try:
            if vthunder and vthunder.device_network_map:
                vlan_id = self.get_vlan_id(loadbalancer.vip.subnet_id, False)
                if self.is_vlan_deletable():
                    master_device_id = vthunder.device_network_map[0].vcs_device_id
                    for device_obj in vthunder.device_network_map:
                        self.delete_device_vlan(vlan_id, loadbalancer.vip.subnet_id, vthunder,
                                                device_id=device_obj.vcs_device_id,
                                                master_device_id=master_device_id)
        except (acos_errors.ACOSException, req_exceptions.ConnectionError) as e:
            LOG.exception("Failed to delete VLAN on vThunder: %s", str(e))
            raise e


class DeleteInterfaceTagIfNotInUseForMember(TagInterfaceBaseTask):
    """Task to untag Ethernet/Trunk Interface on a vThunder device from member subnet"""

    @axapi_client_decorator
    def execute(self, member, vthunder):
        if not member.subnet_id:
            LOG.warning("Subnet id argument was not specified during "
                        "issuance of create command/API call for member %s. "
                        "Skipping DeleteInterfaceTagIfNotInUseForMember task", member.id)
            return
        try:
            if vthunder and vthunder.device_network_map:
                vlan_id = self.get_vlan_id(member.subnet_id, False)
                if self.is_vlan_deletable():
                    master_device_id = vthunder.device_network_map[0].vcs_device_id
                    for device_obj in vthunder.device_network_map:
                        self.delete_device_vlan(vlan_id, member.subnet_id, vthunder,
                                                device_id=device_obj.vcs_device_id,
                                                master_device_id=master_device_id)
        except (acos_errors.ACOSException, req_exceptions.ConnectionError) as e:
            LOG.exception("Failed to delete VLAN on vThunder: %s", str(e))
            raise e


class WriteMemory(VThunderBaseTask):
    """Task to write memory of the Thunder device"""

    @axapi_client_decorator
    def execute(self, vthunder, write_mem_shared_part=False):
        if CONF.a10_house_keeping.use_periodic_write_memory == 'disable':
            try:
                if vthunder:
                    if vthunder.partition_name != "shared" and not write_mem_shared_part:
                        LOG.info("Performing write memory for thunder - {}:{}"
                                 .format(vthunder.ip_address, vthunder.partition_name))
                        self.axapi_client.system.action.write_memory(
                            partition="specified",
                            specified_partition=vthunder.partition_name)
                    else:
                        LOG.info("Performing write memory for thunder - {}:{}"
                                 .format(vthunder.ip_address, "shared"))
                        self.axapi_client.system.action.write_memory(partition="shared")
            except acos_errors.ACOSException:
                LOG.warning('Failed to write memory on thunder device: %s due to '
                            'ACOSException.... skipping', vthunder.ip_address)
            except req_exceptions.ConnectionError:
                LOG.warning('Failed to write memory on thunder device: %s due to '
                            'ConnectionError.... skipping', vthunder.ip_address)
            except Exception as e:
                LOG.warning('Failed to write memory on thunder device: {} due to {}'
                            .format(vthunder.ip_address, str(e)))


class WriteMemoryHouseKeeper(VThunderBaseTask):
    """Task to write memory of the Thunder device using housekeeping"""

    @axapi_client_decorator
    def execute(self, vthunder, loadbalancers_list, write_mem_shared_part=False):
        try:
            if vthunder:
                if write_mem_shared_part:
                    LOG.info("Performing write memory for thunder - {}:{}"
                             .format(vthunder.ip_address, "shared"))
                    self.axapi_client.system.action.write_memory(partition="shared")
                else:
                    if vthunder.partition_name != "shared":
                        LOG.info("Performing write memory for thunder - {}:{}"
                                 .format(vthunder.ip_address, vthunder.partition_name))
                        self.axapi_client.system.action.write_memory(
                            partition="specified",
                            specified_partition=vthunder.partition_name)
        except acos_errors.ACOSException:
            LOG.warning('Failed to write memory on thunder device: {} due to ACOSException'
                        '.... skipping'.format(vthunder.ip_address))
            self._revert_lb_to_active(vthunder, loadbalancers_list)
            return False
        except req_exceptions.ConnectionError:
            LOG.warning('Failed to write memory on thunder device: {} due to ConnectionError'
                        '.... skipping'.format(vthunder.ip_address))
            self._revert_lb_to_active(vthunder, loadbalancers_list)
            return False
        except Exception as e:
            LOG.warning('Failed to write memory on thunder device: '
                        '{} due to {}...skipping'.format(vthunder.ip_address, str(e)))
            self._revert_lb_to_active(vthunder, loadbalancers_list)
            return False
        return True

    def _revert_lb_to_active(self, vthunder, loadbalancers_list):
        try:
            for lb in loadbalancers_list:
                self.loadbalancer_repo.update(
                    db_apis.get_session(),
                    lb.id,
                    provisioning_status='ACTIVE')
        except Exception as e:
            LOG.exception('Failed to set Loadbalancers to ACTIVE due to '
                          ': {}'.format(str(e)))


class WriteMemoryThunderStatusCheck(VThunderBaseTask):

    @axapi_client_decorator
    def execute(self, vthunder, loadbalancers_list):
        if not loadbalancers_list:
            return
        try:
            info = self.axapi_client.system.action.get_thunder_up_time()
            if ("miscellenious-alb" in info and "oper" in info['miscellenious-alb'] and
               "uptime" in info['miscellenious-alb']['oper']):
                uptime = info['miscellenious-alb']['oper']['uptime']
                uptime_delta = datetime.timedelta(seconds=uptime)
                reload_time = datetime.datetime.utcnow() - uptime_delta
                if reload_time > vthunder.updated_at:
                    self._mark_lb_as_error(vthunder, loadbalancers_list)
            else:
                LOG.warning("Write Memory flow failed to detect Thunder status")
                raise
        except Exception as e:
            # log warning but continue the write memory flow
            LOG.warning("Write Memory flow failed to detect Thunder status: %s ... skipping",
                        str(e))

    def _mark_lb_as_error(self, vthunder, loadbalancers_list):
        try:
            LOG.warning('Detect vThunder %s reload before write memory, '
                        'set loadbalancer status to ERROR', vthunder.id)
            for lb in loadbalancers_list:
                self.loadbalancer_repo.update(
                    db_apis.get_session(),
                    lb.id,
                    provisioning_status='ERROR')
        except Exception as e:
            LOG.exception('Failed to set Loadbalancers to ERROR due to '
                          ': {}'.format(str(e)))


class UpdateAcosVersionInVthunderEntry(VThunderBaseTask):

    @axapi_client_decorator
    def execute(self, vthunder, loadbalancer):
        existing_vthunder = self.vthunder_repo.get_vthunder_by_project_id(db_apis.get_session(),
                                                                          loadbalancer.project_id)
        if not existing_vthunder:
            try:
                acos_version_summary = self.axapi_client.system.action.get_acos_version()
                acos_version = acos_version_summary['version']['oper']['sw-version'].split(',')[0]
                self.vthunder_repo.update(db_apis.get_session(),
                                          vthunder.id,
                                          acos_version=acos_version)
            except Exception as e:
                LOG.exception('Failed to set acos_version in vthunders table '
                              ': {}'.format(str(e)))
        else:
            self.vthunder_repo.update(
                db_apis.get_session(),
                vthunder.id,
                acos_version=existing_vthunder.acos_version)


class AmphoraePostNetworkUnplug(VThunderBaseTask):
    """Task to reboot and configure vThunder device"""

    @axapi_client_decorator
    def execute(self, added_ports, loadbalancer, vthunder):
        """Execute get_info routine for a vThunder until it responds."""
        try:
            if loadbalancer.amphorae:
                amphora_id = loadbalancer.amphorae[0].id
                if added_ports and amphora_id in added_ports and len(added_ports[amphora_id]) > 0:
                    self.axapi_client.system.action.write_memory()
                    self.axapi_client.system.action.reload_reboot_for_interface_detachment(
                        vthunder.acos_version)
                    LOG.debug("Waiting for 30 seconds to trigger vThunder reload/reboot.")
                    time.sleep(30)
                    LOG.debug("Successfully rebooted/reloaded vThunder: %s", vthunder.id)
                else:
                    LOG.debug("vThunder reboot/relaod is not required for member addition.")
        except (acos_errors.ACOSException, req_exceptions.ConnectionError) as e:
            LOG.exception("Failed to reboot/reload vthunder device: %s", str(e))
            raise e


class GetVThunderInterface(VThunderBaseTask):
    """Task to get interface on master and backup vThunders"""

    @axapi_client_decorator
    def execute(self, vthunder):
        try:
            vcs_summary = {}
            ifnum = []
            ifnum_master = []
            ifnum_backup = []

            vcs_summary = self.axapi_client.system.action.get_vcs_summary_oper()
            vcs_member_list = vcs_summary['vcs-summary']['oper']['member-list']
            interfaces = self.axapi_client.interface.get_list()

            for i in range(len(interfaces['interface']['ethernet-list'])):
                if interfaces['interface']['ethernet-list'][i]['action'] == "disable":
                    ifnum = ifnum + [interfaces['interface']['ethernet-list'][i]['ifnum']]

            for i in range(len(vcs_member_list)):
                if vthunder.ip_address in vcs_member_list[i]['ip-list'][0]['ip']:
                    role = vcs_member_list[i]['state'].split('(')[0]
                    if role == "vMaster":
                        ifnum_master = ifnum
                        LOG.debug(
                            "Fetched the ethernet interface for Master vThunder: %s", vthunder.id)
                    if role == "vBlade":
                        ifnum_backup = ifnum
                        LOG.debug(
                            "Fetched the ethernet interface for Backup vThunder: %s", vthunder.id)
            return ifnum_master, ifnum_backup
        except (acos_errors.ACOSException, req_exceptions.ConnectionError) as e:
            LOG.exception("Failed to fetch ethernet interface Backup vThunder: %s", str(e))
            raise e


class VCSReload(VThunderBaseTask):
    """Task to perform VCS reload"""

    @axapi_client_decorator
    def execute(self, vthunder):
        """Execute get_info routine for a vThunder until it responds."""
        try:
            self.axapi_client.system.action.vcs_reload()
            time.sleep(30)
            LOG.debug("Performing VCS reload")
        except (acos_errors.ACOSException, req_exceptions.ConnectionError) as e:
            LOG.exception("Failed to reload VCS on vThunder "
                          "for amphora id: %s", vthunder.amphora_id)
            raise e


class VCSSyncWait(VThunderBaseTask):
    """Task to wait VCS reload, VCS negotiagtion or VCS configuration sync ready."""

    @axapi_client_decorator
    def execute(self, vthunder):
        if not vthunder or CONF.a10_controller_worker.loadbalancer_topology != "ACTIVE_STANDBY":
            return

        attempts = CONF.a10_controller_worker.amp_vcs_retries
        while attempts >= 0:
            vmaster_ready = False
            vblade_ready = False
            try:
                attempts = attempts - 1
                vcs_summary = {}
                vcs_summary = self.axapi_client.system.action.get_vcs_summary_oper()
                vcs_member_list = vcs_summary['vcs-summary']['oper']['member-list']
                for i in range(len(vcs_member_list)):
                    role = vcs_member_list[i]['state'].split('(')[0]
                    if role == "vMaster":
                        vmaster_ready = True
                    if role == "vBlade":
                        vblade_ready = True
                    if vmaster_ready is True and vblade_ready is True:
                        break
                else:
                    # TODO(ytsai) maybe reload the device and try again
                    if vmaster_ready:
                        raise acos_errors.AxapiJsonFormatError(
                            msg="vBlade not found in vcs-summary")
                    raise acos_errors.AxapiJsonFormatError(
                        msg="vMaster not found in vcs-summary")
                if vmaster_ready is True and vblade_ready is True:
                    break
            except a10_task_utils.thunder_busy_exceptions() as e:
                # acos-client already wait default_axapi_timeout for these exceptions.
                axapi_timeout = CONF.vthunder.default_axapi_timeout
                attempt_wait = CONF.a10_controller_worker.amp_vcs_wait_sec
                if axapi_timeout > attempt_wait:
                    attempts = attempts - (axapi_timeout / attempt_wait - 1)
                if attempts < 0:
                    LOG.exception("Failed to connect VCS device: %s", str(e))
                    raise e
            except Exception as e:
                if attempts < 0:
                    LOG.exception("VCS not ready after timeout: %s", str(e))
                    raise e
                time.sleep(CONF.a10_controller_worker.amp_vcs_wait_sec)


class GetMasterVThunder(VThunderBaseTask):
    """Task to get Master vThunder"""

    @axapi_client_decorator
    def execute(self, vthunder):
        if vthunder:
            attempts = CONF.a10_controller_worker.amp_vcs_retries
            while attempts >= 0:
                try:
                    attempts = attempts - 1
                    vcs_summary = {}
                    vcs_summary = self.axapi_client.system.action.get_vcs_summary_oper()
                    vcs_member_list = vcs_summary['vcs-summary']['oper']['member-list']
                    for i in range(len(vcs_member_list)):
                        role = vcs_member_list[i]['state'].split('(')[0]
                        if role == "vMaster":
                            vthunder.ip_address = vcs_member_list[i]['ip-list'][0]['ip']
                            break
                    else:
                        raise acos_errors.AxapiJsonFormatError(
                            msg="vMaster not found in vcs-summary")
                    return vthunder
                except a10_task_utils.thunder_busy_exceptions() as e:
                    # acos-client already wait default_axapi_timeout for these exceptions.
                    axapi_timeout = CONF.vthunder.default_axapi_timeout
                    attempt_wait = CONF.a10_controller_worker.amp_vcs_wait_sec
                    if axapi_timeout > attempt_wait:
                        attempts = attempts - (axapi_timeout / attempt_wait - 1)
                    if attempts < 0:
                        LOG.exception("Failed to get Master vThunder: %s", str(e))
                        raise e
                except Exception as e:
                    if attempts < 0:
                        LOG.exception("Failed to get Master vThunder: %s", str(e))
                        raise e
                    time.sleep(CONF.a10_controller_worker.amp_vcs_wait_sec)
        else:
            return None


class VthunderInstanceBusy(VThunderBaseTask):

    def execute(self, compute_busy=False):
        if compute_busy:
            raise Exception('vThunder instance is busy now, try again later.')


class GetVthunderConfByFlavor(VThunderBaseTask):

    def execute(self, loadbalancer, vthunder_config, device_config_dict, flavor_data=None):
        if flavor_data is None and vthunder_config is None:
            raise exceptions.ProjectDeviceNotFound()

        if flavor_data is not None:
            device_flavor = flavor_data.get('device_name', None)
            if device_flavor is not None:
                dev_key = a10constants.DEVICE_KEY_PREFIX + device_flavor
                if dev_key in device_config_dict:
                    vthunder_config = device_config_dict[dev_key]
                    vthunder_config.project_id = loadbalancer.project_id
                    if vthunder_config.hierarchical_multitenancy == "enable":
                        vthunder_config.partition_name = loadbalancer.project_id[0:14]
                    return vthunder_config, True
                else:
                    raise exceptions.FlavorDeviceNotFound(device_flavor)

        return vthunder_config, False
