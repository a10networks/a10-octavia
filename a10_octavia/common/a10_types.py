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

"""Type conversion and validation classes for configuration options.
Use these classes as values for the `type` argument to
:class:`oslo_config.cfg.Opt` and its subclasses.
.. versionadded:: 1.3
"""
import json
import netaddr

from oslo_config import cfg
from oslo_config.types import ConfigType, String

from a10_octavia.common import data_models


class ListOfDictOpt(cfg.Opt):
     def __init__(self, name, item_type=None, bounds=None, **kwargs):
        super(ListOfDictOpt, self).__init__(name, type=ListOfObjects(item_type=item_type,
                                                      bounds=bounds), **kwargs)


class ListOfObjects(ConfigType):
    def __init__(self, item_type=None, bounds=False, type_name='list of dict values'):
        super(ListOfObjects, self).__init__(type_name=type_name)

        if item_type is None:
            item_type = String()

        if not callable(item_type):
            raise TypeError('item_type must be callable')
        self.item_type = item_type
        self.bounds = bounds

    def __call__(self, value):
        result = []
        if isinstance(value, (list, tuple)):
            return list(six.moves.map(self.item_type, value))

        s = value.strip().rstrip(',')
        if self.bounds:
            if not s.startswith('['):
                raise ValueError('Value should start with "["')
            if not s.endswith(']'):
                raise ValueError('Value should end with "]"')
            s = s[1:-1]

        s = s.replace(" ","").replace("\n", "") ## need to think of other way to remove space without affecting value part of dict
        if s:
            s = s.split('},{')
        final_list = []
        for ss in s:
            ss = ss.lstrip('{').rstrip('}')
            ss = '{' + ss + '}'
            ss = ss.replace("\'", "\"")
            single_dict = json.loads(ss)
            if validate_params(single_dict):
                final_list.append(single_dict)
             
        return convert_to_rack_vthunder_conf(final_list)    


    def _formatter(self, value):
        fmtstr = '[{}]' if self.bounds else '{}'
        if isinstance(value, six.string_types):
            return fmtstr.format(value)
        if isinstance(value, list):
            value = [
                self.item_type._formatter(v)
                for v in value
            ]
            return fmtstr.format(','.join(value))
        return fmtstr.format(self.item_type._formatter(value))

     
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
                LOG.warning('Invalid definition of rack device for'
                            'project ' + project_id)

    except KeyError as e:
        LOG.error("Invalid definition of rack device in A10 config file."
                   "The Loadbalancer you create shall boot as overcloud."
                   "Check attribute: " + str(e))
    return rack_dict


def validate_params(rack_info):
    if all (k in rack_info for k in ('project_id', 'ip_address', 'username', 'password')):
        if rack_info['ip_address'] is not None:
            if check_ipv4(rack_info['ip_address']):
                if all(rack_info[x] is not None for x in ('project_id', 'username', 'password')):
                    return True
                return False
        
	
def check_ipv4(address):
    if not netaddr.valid_ipv4(address, netaddr.core.INET_PTON):
        return False
    return True


