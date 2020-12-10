# Copyright 2019 A10 Networks
# All Rights Reserved.
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

"""A10 Octavia Helper Module

"""
import acos_client
import netaddr
import socket
import struct

from oslo_config import cfg
from oslo_log import log as logging

from keystoneauth1.exceptions import http as keystone_exception
from keystoneclient.v3 import client as keystone_client
from octavia.common import keystone
from stevedore import driver as stevedore_driver

from a10_octavia.common import data_models
from a10_octavia.common import exceptions

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


def validate_ipv4(address):
    """Validate for IP4 address format"""
    if not netaddr.valid_ipv4(address, netaddr.core.INET_PTON):
        raise cfg.ConfigFileValueError(
            'Invalid IPAddress value given in configuration: {0}'.format(address))


def validate_partial_ipv4(address):
    """Validate the partial IPv4 suffix provided"""
    partial_ip = address.lstrip('.')
    octets = partial_ip.split('.')
    for idx in range(4 - len(octets)):
        octets.insert(0, '0')
    if not netaddr.valid_ipv4('.'.join(octets), netaddr.core.INET_PTON):
        raise cfg.ConfigFileValueError('Invalid partial IPAddress value given'
                                       ' in configuration: {0}'.format(address))
    return address


def validate_partition(hardware_device):
    partition_name = hardware_device.get('partition_name', '')
    if len(partition_name) > 14:
        raise ValueError("Supplied partition value '%s' exceeds maximum length 14" %
                         (partition_name))


def validate_params(hardware_info):
    """Check for all the required parameters for hardware configurations."""
    if all(k in hardware_info for k in ('project_id', 'ip_address',
                                        'username', 'password', 'device_name')):
        if all(hardware_info[x] is not None for x in ('project_id', 'ip_address',
                                                      'username', 'password', 'device_name')):
            validate_ipv4(hardware_info['ip_address'])
            validate_partition(hardware_info)
            return hardware_info
    raise cfg.ConfigFileValueError('Please check your configuration. The params `project_id`, '
                                   '`ip_address`, `username`, `password` and `device_name` '
                                   'under [hardware_thunder] section cannot be None ')


def check_duplicate_entries(hardware_dict):
    hardware_count_dict = {}
    for hardware_device in hardware_dict.values():
        if hardware_device.hierarchical_multitenancy != "enable":
            candidate = '{}:{}'.format(hardware_device.ip_address, hardware_device.partition_name)
            hardware_count_dict[candidate] = hardware_count_dict.get(candidate, 0) + 1
    return [k for k, v in hardware_count_dict.items() if v > 1]


def convert_to_hardware_thunder_conf(hardware_list):
    """Validate for all vthunder nouns for hardware devices configurations."""
    hardware_dict = {}
    for hardware_device in hardware_list:
        hardware_device = validate_params(hardware_device)
        project_id = hardware_device['project_id']
        if hardware_dict.get(project_id):
            raise cfg.ConfigFileValueError('Supplied duplicate project_id {} '
                                           ' in [hardware_thunder] section'.format(project_id))
        hardware_device['undercloud'] = True
        if hardware_device.get('interface_vlan_map'):
            hardware_device['device_network_map'] = validate_interface_vlan_map(hardware_device)
            del hardware_device['interface_vlan_map']
        hierarchical_mt = hardware_device.get('hierarchical_multitenancy')
        if hierarchical_mt == "enable":
            hardware_device["partition_name"] = project_id[0:14]
        if hierarchical_mt and hierarchical_mt not in ('enable', 'disable'):
            raise cfg.ConfigFileValueError('Option `hierarchical_multitenancy` specified '
                                           'under project id {} only accepts "enable" and '
                                           '"disable"'.format(project_id))
        vthunder_conf = data_models.HardwareThunder(**hardware_device)
        hardware_dict[project_id] = vthunder_conf
        duplicates = check_duplicate_entries(hardware_dict)
        if duplicates:
            raise cfg.ConfigFileValueError('Duplicates found for the following '
                                           '\'ip_address:partition_name\' entries: {}'
                                           .format(list(duplicates)))
    return hardware_dict


def get_parent_project_list():
    parent_project_list = []
    for project_id in CONF.hardware_thunder.devices:
        parent_project_id = get_parent_project(project_id)
        if parent_project_id != 'default':
            parent_project_list.append(parent_project_id)
    return parent_project_list


def get_parent_project(project_id):
    key_session = keystone.KeystoneSession().get_session()
    key_client = keystone_client.Client(session=key_session)
    try:
        project = key_client.projects.get(project_id)
        return project.parent_id
    except keystone_exception.NotFound:
        return None


def get_axapi_client(vthunder):
    api_ver = acos_client.AXAPI_21 if vthunder.axapi_version == 21 else acos_client.AXAPI_30
    axapi_client = acos_client.Client(vthunder.ip_address, api_ver,
                                      vthunder.username, vthunder.password,
                                      timeout=30)
    return axapi_client


def get_net_info_from_cidr(cidr):
    subnet_ip, mask = cidr.split('/')
    avail_hosts = (1 << 32 - int(mask))
    netmask = socket.inet_ntoa(struct.pack('>I', (1 << 32) - avail_hosts))
    return subnet_ip, netmask


def check_ip_in_subnet_range(ip, subnet, netmask):
    if ip is None or subnet is None or netmask is None:
        return False
    int_ip = struct.unpack('>L', socket.inet_aton(ip))[0]
    int_subnet = struct.unpack('>L', socket.inet_aton(subnet))[0]
    int_netmask = struct.unpack('>L', socket.inet_aton(netmask))[0]
    return int_ip & int_netmask == int_subnet


def merge_host_and_network_ip(cidr, host_ip):
    network_ip, mask = cidr.split('/')
    host_bits = struct.pack('>L', ((1 << (32 - int(mask))) - 1))
    int_host_bits = struct.unpack('>L', host_bits)[0]
    int_host_ip = struct.unpack('>L', socket.inet_aton(host_ip))[0]
    int_net_ip = struct.unpack('>L', socket.inet_aton(network_ip))[0]
    full_ip_packed = struct.pack('>L', int_net_ip | (int_host_ip & int_host_bits))
    return socket.inet_ntoa(full_ip_packed)


def get_network_driver():
    CONF.import_group('a10_controller_worker', 'a10_octavia.common.config_options')
    network_driver = stevedore_driver.DriverManager(
        namespace='octavia.network.drivers',
        name=CONF.a10_controller_worker.network_driver,
        invoke_on_load=True
    ).driver
    return network_driver


def get_patched_ip_address(ip, cidr):
    net_ip, netmask = get_net_info_from_cidr(cidr)
    octets = ip.lstrip('.').split('.')

    if len(octets) == 4:
        validate_ipv4(ip)
        if check_ip_in_subnet_range(ip, net_ip, netmask):
            return ip
        else:
            raise exceptions.VRIDIPNotInSubentRangeError(ip, cidr)

    for i in range(4 - len(octets)):
        octets.insert(0, '0')
    host_ip = '.'.join(octets)

    try:
        int_host_ip = struct.unpack('>L', socket.inet_aton(host_ip))[0]
    except socket.error:
        raise exceptions.VRIDIPNotInSubentRangeError(host_ip, cidr)

    int_net_ip = struct.unpack('>L', socket.inet_aton(net_ip))[0]
    int_netmask = struct.unpack('>L', socket.inet_aton(netmask))[0]

    # Create a set of test bits to find partial netmask octet
    # ie 1.1.1.1 & 255.255.254.0 -> 1.1.0.0
    test_bits = (1 << 24 | 1 << 16 | 1 << 8 | 1)
    test_bits = (int_netmask & test_bits)

    # Then shift 8 bits (1 -> 256) and subtract by 1 in each octet to get 255
    test_bits = (test_bits << 8) - test_bits

    # Use truncated mask to fill in any missing octets of partial IP
    canidate_ip = (test_bits & int_net_ip) | int_host_ip

    if (canidate_ip & int_netmask) != (int_net_ip & int_netmask):
        raise exceptions.VRIDIPNotInSubentRangeError(host_ip, cidr)

    return socket.inet_ntoa(struct.pack('>L', canidate_ip))


def get_vrid_floating_ip_for_project(project_id):
    device_info = CONF.hardware_thunder.devices.get(project_id)
    if device_info:
        vrid_fp = device_info.vrid_floating_ip
        return CONF.a10_global.vrid_floating_ip if not vrid_fp else vrid_fp


def validate_vcs_device_info(device_network_map):
    num_devices = len(device_network_map)
    if num_devices > 2:
        raise exceptions.VcsDevicesNumberExceedsConfigError(num_devices)
    for device_obj in device_network_map:
        device_id = device_obj.vcs_device_id
        if ((num_devices > 1 and not device_id) or
            (device_id is not None and (not isinstance(device_id, int) or
                                        (device_id < 1 or device_id > 2)))):
            raise exceptions.InvalidVcsDeviceIdConfigError(device_id)
        if num_devices > 1:
            if not device_obj.mgmt_ip_address:
                raise exceptions.MissingMgmtIpConfigError(device_id)
            else:
                validate_ipv4(device_obj.mgmt_ip_address)


def convert_interface_to_data_model(interface_obj):
    vlan_map_list = interface_obj.get('vlan_map')
    interface_num = interface_obj.get('interface_num')
    interface_dm = data_models.Interface()
    if not interface_num:
        raise exceptions.MissingInterfaceNumConfigError()
    if not type(interface_num) == int:
        raise exceptions.InvalidInterfaceNumberConfigError(interface_num)
    if not vlan_map_list:
        LOG.warning("Empty vlan map provided in configuration file")
    for vlan_map in vlan_map_list:
        vlan_id = vlan_map.get('vlan_id')
        if not vlan_id:
            raise exceptions.MissingVlanIDConfigError(interface_num)
        if not type(vlan_id) == int:
            raise exceptions.InvalidVlanIdConfigError(vlan_id)
        if vlan_id in interface_dm.tags:
            raise exceptions.DuplicateVlanTagsConfigError(interface_num, vlan_id)
        if vlan_map.get('use_dhcp') and vlan_map.get('use_dhcp') not in ("True", "False"):
            raise exceptions.InvalidUseDhcpConfigError(vlan_map.get('use_dhcp'))
        if vlan_map.get('use_dhcp') == 'True':
            if vlan_map.get('ve_ip'):
                raise exceptions.VirtEthCollisionConfigError(interface_num, vlan_id)
            else:
                interface_dm.ve_ips.append('dhcp')
        if not vlan_map.get('use_dhcp') or vlan_map.get('use_dhcp') == 'False':
            if not vlan_map.get('ve_ip'):
                raise exceptions.VirtEthMissingConfigError(interface_num, vlan_id)
            interface_dm.ve_ips.append(validate_partial_ipv4(vlan_map.get('ve_ip')))
        interface_dm.tags.append(vlan_id)
    interface_dm.interface_num = interface_num

    return interface_dm


def validate_interface_vlan_map(hardware_device):
    device_network_map = []
    for device_id, device_obj in hardware_device.get('interface_vlan_map').items():
        device_map = data_models.DeviceNetworkMap(device_obj.get('vcs_device_id'))
        if device_obj.get('ethernet_interfaces'):
            for eth in device_obj.get('ethernet_interfaces'):
                device_map.ethernet_interfaces.append(convert_interface_to_data_model(eth))
        if device_obj.get('trunk_interfaces'):
            for trunk in device_obj.get('trunk_interfaces'):
                device_map.trunk_interfaces.append(convert_interface_to_data_model(trunk))
        if device_obj.get('mgmt_ip_address'):
            device_map.mgmt_ip_address = device_obj.get('mgmt_ip_address')
        device_network_map.append(device_map)
    validate_vcs_device_info(device_network_map)
    return device_network_map
