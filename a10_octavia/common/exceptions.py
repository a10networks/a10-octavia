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

from oslo_config import cfg

from octavia.common import exceptions
from octavia.i18n import _
from octavia.network import base


class NoDatabaseURL(exceptions.OctaviaException):
    message = _("Must set db connection url in configuration file.")


class PortCreationFailedException(base.NetworkException):
    pass


class DeallocateTrunkException(base.NetworkException):
    pass


class AllocateTrunkException(base.NetworkException):
    pass


class VRIDIPNotInSubentRangeError(base.NetworkException):
    pass


class MissingVlanIDConfigError(cfg.ConfigFileValueError):

    def __init__(self, interface_num):
        msg = ('Missing `vlan_id` attribute for `interface_num` {0} ' +
               ' in `interface_vlan_map` under ' +
               '[hardware_thunder] section.').format(interface_num)
        super(MissingVlanIDConfigError, self).__init__(msg=msg)


class DuplicateVlanTagsConfigError(cfg.ConfigFileValueError):

    def __init__(self, interface_num, vlan_id):
        msg = ('Duplicate `vlan_tags` entry of `vlan_id` {0} ' +
               'found for `interface_num` {1} in `interface_vlan_map` under ' +
               '[hardware_thunder] section.').format(vlan_id, interface_num)
        super(DuplicateVlanTagsConfigError, self).__init__(msg=msg)


class MissingInterfaceNumConfigError(cfg.ConfigFileValueError):

    def __init__(self):
        msg = ('Missing `interface_num` in `interface_vlan_map` under [hardware_thunder] section.')
        super(MissingInterfaceNumConfigError, self).__init__(msg=msg)


class VirtEthCollisionConfigError(cfg.ConfigFileValueError):

    def __init__(self, interface_num, vlan_id):
        msg = ('Check settings for `vlan_id` {0} of `interface_num` {1}. ' +
               'Please set `use_dhcp` to False ' +
               'before setting the `ve_ip`').format(vlan_id, interface_num)
        super(VirtEthCollisionConfigError, self).__init__(msg=msg)


class VirtEthMissingConfigError(cfg.ConfigFileValueError):

    def __init__(self, interface_num, vlan_id):
        msg = ('Check settings for `vlan_id` {0} of `interface_num` {1}. ' +
               'Missing `use_dhcp` and `ve_ip` in config. ' +
               'Please provide either.').format(vlan_id, interface_num)
        super(VirtEthMissingConfigError, self).__init__(msg=msg)
