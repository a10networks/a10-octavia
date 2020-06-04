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

from keystoneclient.v3 import client as keystone_client
from octavia.common import keystone
from stevedore import driver as stevedore_driver

from a10_octavia.common import a10constants
from a10_octavia.common import data_models

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


def validate_partition(hardware_device):
    partition_name = hardware_device.get('partition_name')
    if not partition_name:
        hardware_device['partition_name'] = a10constants.SHARED_PARTITION
    elif len(partition_name) > 14:
        raise ValueError("Supplied partition value '%s' exceeds maximum length 14" %
                         (partition_name))
    return hardware_device


def validate_params(hardware_info):
    """Check for all the required parameters for hardware configurations."""
    if all(k in hardware_info for k in ('project_id', 'ip_address',
                                        'username', 'password', 'device_name')):
        if all(hardware_info[x] is not None for x in ('project_id', 'ip_address',
                                                      'username', 'password', 'device_name')):
            validate_ipv4(hardware_info['ip_address'])
            hardware_info = validate_partition(hardware_info)
            if 'vrid_floating_ip' in hardware_info:
                if hardware_info['vrid_floating_ip'].lower() != 'dhcp':
                    validate_ipv4(hardware_info['vrid_floating_ip'])
            return hardware_info
    raise cfg.ConfigFileValueError('Please check your configuration. The params `project_id`, '
                                   '`ip_address`, `username`, `password` and `device_name` '
                                   'under [hardware_thunder] section cannot be None ')


def check_duplicate_entries(hardware_dict):
    hardware_count_dict = {}
    for hardware_device in hardware_dict.values():
        candidate = '{}:{}'.format(hardware_device.ip_address, hardware_device.partition_name)
        hardware_count_dict[candidate] = hardware_count_dict.get(candidate, 0) + 1
    return [k for k, v in hardware_count_dict.items() if v > 1]


def get_parent_project(project_id):
    key_session = keystone.KeystoneSession().get_session()
    key_client = keystone_client.Client(session=key_session)
    project = key_client.projects.get(project_id)
    if project.parent_id != 'default':
        return project.parent_id


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
    host_ip = ip.lstrip('.')
    octets = host_ip.split('.')
    if len(octets) == 4:
        validate_ipv4(ip)
        return ip
    for idx in range(4 - len(octets)):
        octets.insert(0, '0')
    host_ip = '.'.join(octets)
    return merge_host_and_network_ip(cidr, host_ip)


def get_vrid_floating_ip_for_project(project_id):
    device_info = CONF.hardware_thunder.devices.get(project_id)
    if device_info:
        vrid_fp = device_info.vrid_floating_ip
        return CONF.a10_global.vrid_floating_ip if not vrid_fp else vrid_fp


def validate_interface_vlan_map(hardware_device):
    if 'interface_vlan_map' not in hardware_device:
        return True

    ivmap = hardware_device.get('interface_vlan_map')
    for ifnum in ivmap:
        if_info = ivmap[ifnum]
        for vlan_id in if_info:
            ve_info = if_info[vlan_id]
            if ve_info.get('use_dhcp') and ve_info.get('ve_ip_address'):
                raise cfg.ConfigFileValueError('Check settings for vlan ' + vlan_id +
                                               '. Please do not set ve_ip_address in '
                                               'interface_vlan_map when use_dhcp is True')
                if not ve_info.get('use_dhcp'):
                    if not ve_info.get('ve_ip_address'):
                        raise cfg.ConfigFileValueError('Check settings for vlan ' + vlan_id +
                                                       '. Please set valid ve_ip_address in '
                                                       'interface_vlan_map when use_dhcp is False')
                    validate_partial_ipv4(ve_info['ve_ip_address'])
    return True


def convert_to_rack_vthunder_conf(rack_list):
    """ Validates for all vthunder nouns for rack devices
        configurations.
    """
    rack_dict = {}
    validation_flag = False
    for rack_device in rack_list:
        validation_flag = validate_mandatory_params(rack_device)
        if validation_flag:
            if rack_dict.get(rack_device['project_id']):
                raise ConfigFileValueError('Supplied duplicate project_id ' +
                                           rack_device['project_id'] +
                                           ' in [rack_vthunder] section')
            rack_device['undercloud'] = True
            if not rack_device.get('partition'):
                rack_device['partition'] = a10constants.SHARED_PARTITION
            vthunder_conf = data_models.VThunder(**rack_device)
            rack_dict[rack_device['project_id']] = vthunder_conf
            validate_interface_vlan_map(rack_device)

    duplicates_list = check_duplicate_entries(rack_dict)
    if len(duplicates_list) != 0:
        raise ConfigFileValueError('Duplicates found for the following '
                                   '\'ip_address:partition\' entries: {}'
                                   .format(list(duplicates_list)))
    return rack_dict


def get_parent_project(project_id):
    key_session = keystone.KeystoneSession().get_session()
    key_client = keystone_client.Client(session=key_session)
    project = key_client.projects.get(project_id)
    if project.parent_id != 'default':
        return project.parent_id


def get_axapi_client(vthunder):
    api_ver = acos_client.AXAPI_21 if vthunder.axapi_version == 21 else acos_client.AXAPI_30
    axapi_client = acos_client.Client(vthunder.ip_address, api_ver,
                                      vthunder.username, vthunder.password,
                                      timeout=30)
    return axapi_client


""" TODO(ssrinivasan10) use this changes from STACK-1215"""


def get_net_info_from_cidr(cidr):
    subnet_ip, mask = cidr.split('/')
    avail_hosts = (1 << 32 - int(mask))
    netmask = socket.inet_ntoa(struct.pack('>I', (1 << 32) - avail_hosts))
    return subnet_ip, netmask


def check_ip_in_subnet_range(ip, subnet, netmask):
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
