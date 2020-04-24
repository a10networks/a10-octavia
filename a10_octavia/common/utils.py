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


def validate_params(rack_info):
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
        validation_flag = validate_params(rack_device)
        if validation_flag:
            if rack_dict.get(rack_device['project_id']):
                raise ConfigFileValueError('Supplied duplicate project_id ' +
                                           rack_device['project_id'] +
                                           ' in [rack_vthunder] section')
            rack_device['undercloud'] = True
            partition_name = rack_device.get('partition')
            if not partition_name:
                rack_device['partition'] = a10constants.SHARED_PARTITION
            elif len(partition_name) > 14:
                raise ConfigFileValueError('Supplied partition name `' + partition_name +
                                           '` should not be greater than 14 characters')
            vthunder_conf = data_models.VThunder(**rack_device)
            rack_dict[rack_device['project_id']] = vthunder_conf

    duplicates_list = check_duplicate_entries(rack_dict)
    if len(duplicates_list) != 0:
        raise ConfigFileValueError('Duplicates found for the following '
                                   '\'ip_address:partition\' entries: {}'
                                   .format(list(duplicates_list)))
    return rack_dict
