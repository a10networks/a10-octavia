# Copyright 2020 A10 Networks
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

import json
import netaddr
import six

from oslo_config import cfg
from oslo_config.types import List
from oslo_log import log as logging

from a10_octavia.common import data_models

LOG = logging.getLogger(__name__)


class ListOfDictOpt(cfg.Opt):
    def __init__(self, name, item_type=None, bounds=None, **kwargs):
        super(ListOfDictOpt, self).__init__(name, type=ListOfObjects(item_type, bounds), **kwargs)


class ListOfObjects(List):
    def __init__(self, bounds=False, type_name='list of dict values'):
        super(ListOfObjects, self).__init__(bounds=bounds, type_name=type_name)

    def __call__(self, value):
        if isinstance(value, (list, tuple)):
            return list(six.moves.map(self.item_type, value))

        value = value.strip().rstrip(',')
        if self.bounds:
            if not value.startswith('['):
                raise ValueError('Value should start with "["')
            if not value.endswith(']'):
                raise ValueError('Value should end with "]"')
            value = value[1:-1]
        # Warning - param device_name should not contain spaces
        value = value.replace(" ", "").replace("\n", "")
        if value:
            value = value.split('},{')
        final_list = []
        for item in value:
            item = '{' + item.lstrip('{').rstrip('}') + '}'
            item = item.replace("\'", "\"")
            single_dict = json.loads(item)
            final_list.append(single_dict)
        return convert_to_rack_vthunder_conf(final_list)


def convert_to_rack_vthunder_conf(rack_list):
    rack_dict = {}
    validation_flag = False
    try:
        for rack_device in rack_list:
            validation_flag = validate_params(rack_device)
            if validation_flag:
                rack_device['undercloud'] = True
                vthunder_conf = data_models.VThunder(**rack_device)
                rack_dict[rack_device['project_id']] = vthunder_conf
            else:
                LOG.warning('Invalid definition of rack device for '
                            'project ' + rack_device['project_id'])

    except KeyError as err:
        LOG.error("Invalid definition of rack device in configuration file."
                  "The Loadbalancer you create shall boot as overcloud."
                  "Check attribute: " + str(err))
    return rack_dict


def validate_params(rack_info):
    if all(k in rack_info for k in ('project_id', 'ip_address',
                                    'username', 'password', 'device_name')):
        if all(rack_info[x] is not None for x in ('project_id', 'ip_address',
                                                  'username', 'password', 'device_name')):
            if validate_ipv4(rack_info['ip_address']):
                return True
            LOG.error('Invalid IP address given ' + rack_info['ip_address'])
    LOG.error('Configuration of `devices` under [RACK_VTHUNDER] is invalid. '
              'Please check your configuration. The params `project_id`, '
              '`ip_address`, `username`, `password` and `device_name` cannot be None ')
    return False


def validate_ipv4(address):
    if not netaddr.valid_ipv4(address, netaddr.core.INET_PTON):
        return False
    return True
