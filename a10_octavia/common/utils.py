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

from oslo_config.cfg import ConfigFileValueError
from oslo_log import log as logging

from keystoneclient.v3 import client as keystone_client
from octavia.common import keystone

from a10_octavia.common import a10constants
from a10_octavia.common import data_models

LOG = logging.getLogger(__name__)


def validate_ipv4(address):
    """Validates for IP4 address format"""
    if not netaddr.valid_ipv4(address, netaddr.core.INET_PTON):
        raise ConfigFileValueError('Invalid IPAddress value given in configuration: ' + address)


def validate_partial_ipv4(address):
    """Validates the partial IPv4 suffix provided"""
    partial_ip = address.lstrip('.')
    octets = partial_ip.split('.')
    for idx in range(4 - len(octets)):
        octets.insert(0, '0')

    if not netaddr.valid_ipv4('.'.join(octets), netaddr.core.INET_PTON):
        raise ConfigFileValueError('Invalid partial IPAddress value given in configuration: '
                                   + address)


def validate_partition(hardware_device):
    partition_name = hardware_device.get('partition_name')
    if not partition_name:
        hardware_device['partition_name'] = a10constants.SHARED_PARTITION
    elif len(partition_name) > 14:
        raise ValueError("Supplied partition value '%s' exceeds maximum length 14" %
                         (partition_name))
    return hardware_device


def validate_params(hardware_info):
    """Check for all the required parameters for hardware configurations.
    """
    if all(k in hardware_info for k in ('project_id', 'ip_address',
                                        'username', 'password', 'device_name')):
        if all(hardware_info[x] is not None for x in ('project_id', 'ip_address',
                                                      'username', 'password', 'device_name')):
            validate_ipv4(hardware_info['ip_address'])
            hardware_info = validate_partition(hardware_info)
            return hardware_info
    raise ConfigFileValueError('Please check your configuration. The params `project_id`, '
                               '`ip_address`, `username`, `password` and `device_name` '
                               'under [hardware_thunder] section cannot be None ')


def check_duplicate_entries(hardware_dict):
    hardware_count_dict = {}
    for hardware_device in hardware_dict.values():
        candidate = '{}:{}'.format(hardware_device.ip_address, hardware_device.partition_name)
        hardware_count_dict[candidate] = hardware_count_dict.get(candidate, 0) + 1
    return [k for k, v in hardware_count_dict.items() if v > 1]


def convert_to_hardware_thunder_conf(hardware_list):
    """ Validates for all vthunder nouns for hardware devices
        configurations.
    """
    hardware_dict = {}
    for hardware_device in hardware_list:
        hardware_device = validate_params(hardware_device)
        if hardware_dict.get(hardware_device['project_id']):
            raise ConfigFileValueError('Supplied duplicate project_id ' +
                                       hardware_device['project_id'] +
                                       ' in [hardware_thunder] section')
        hardware_device['undercloud'] = True
        vthunder_conf = data_models.VThunder(**hardware_device)
        hardware_dict[hardware_device['project_id']] = vthunder_conf

    duplicates_list = check_duplicate_entries(hardware_dict)
    if duplicates_list:
        raise ConfigFileValueError('Duplicates found for the following '
                                   '\'ip_address:partition_name\' entries: {}'
                                   .format(list(duplicates_list)))
    return hardware_dict


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
