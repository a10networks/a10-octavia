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
import netaddr
from oslo_config.cfg import ConfigFileValueError
from oslo_log import log as logging

from a10_octavia.common import a10constants
from a10_octavia.common import data_models

LOG = logging.getLogger(__name__)


def validate_ipv4(address):
    """Validates for IP4 address format"""
    return netaddr.valid_ipv4(address, netaddr.core.INET_PTON)


def validate_mandatory_params(rack_info):
    """Check for all the required parameters for rack configurations.
    """
    if all(k in rack_info for k in ('project_id', 'ip_address',
                                    'username', 'password', 'device_name')):
        if all(rack_info[x] is not None for x in ('project_id', 'ip_address',
                                                  'username', 'password', 'device_name')):
            if validate_ipv4(rack_info['ip_address']):
                return True
            raise ConfigFileValueError('Invalid IPAddress value given ' + rack_info['ip_address'])
    raise ConfigFileValueError('Please check your configuration. The params `project_id`, '
                               '`ip_address`, `username`, `password` and `device_name` '
                               'under [rack_vthunder] section cannot be None ')
    return False


def validate_interface_vlan_map(rack_device):
    if 'interface_vlan_map' not in rack_device:
        return True

    ivmap = rack_device['interface_vlan_map']
    for ifnum in ivmap:
        if_info = ivmap[ifnum]
        for vlan_id in if_info:
            ve_info = if_info[vlan_id]
            if 'use_dhcp' in ve_info and ve_info['use_dhcp']:
                if 'ip_last_octets' in ve_info and ve_info['ip_last_octets'] != '':
                    raise ConfigFileValueError('Check settings for vlan ' + vlan_id +
                                               '. Please do not set ip_last_octets in '
                                               'interface_vlan_map when use_dhcp is True')
            if 'use_dhcp' not in ve_info or not ve_info['use_dhcp']:
                if 'ip_last_octets' not in ve_info or ve_info['ip_last_octets'] == '':
                    raise ConfigFileValueError('Check settings for vlan ' + vlan_id +
                                               '. Please set valid ip_last_octets in '
                                               'interface_vlan_map when use_dhcp is False')
                octets = ve_info['ip_last_octets'].split('.')
                if len(octets) == 0 or len(octets) > 4:
                    raise ConfigFileValueError('Improper ip_last_octets for vlan ' + vlan_id
                                               + 'in interface_vlan_map')
                for octet in octets:
                    if not 0 <= int(octet) <= 255:
                        raise ConfigFileValueError('Improper ip_last_octets for vlan ' +
                                                   vlan_id + 'in interface_vlan_map')
    return True


def check_duplicate_entries(rack_dict):
    rack_count_dict = {}
    for rack_key, rack_value in rack_dict.items():
        candidate = '{}:{}'.format(rack_value.ip_address, rack_value.partition)
        rack_count_dict[candidate] = rack_count_dict.get(candidate, 0) + 1
    return [k for k, v in rack_count_dict.items() if v > 1]


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
