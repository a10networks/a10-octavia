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

from keystone import exception as keystone_exceptions
from oslo_config import cfg

from octavia.common import exceptions
from octavia.i18n import _
from octavia.network import base

import acos_client.errors as acos_errors


class NoDatabaseURL(exceptions.OctaviaException):
    message = _("Must set db connection url in configuration file.")


class PortCreationFailedException(base.NetworkException):
    pass


class DeallocateTrunkException(base.NetworkException):
    pass


class AllocateTrunkException(base.NetworkException):
    pass


class VRIDIPNotInSubentRangeError(base.NetworkException):
    def __init__(self, vrid_ip, subnet):
        msg = ('Invalid VRID floating IP specified. ' +
               'VRID IP {0} out of range ' +
               'for subnet {1}.').format(vrid_ip, subnet)
        super(VRIDIPNotInSubentRangeError, self).__init__(msg)


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
        msg = (
            'Missing `interface_num` in `interface_vlan_map` under [hardware_thunder] section.')
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


class InvalidInterfaceNumberConfigError(cfg.ConfigFileValueError):

    def __init__(self, interface_num):
        msg = ('Invalid value given for setting `interface_num` as \"{0}\". ' +
               'Please provide Integer values only.').format(interface_num)
        super(InvalidInterfaceNumberConfigError, self).__init__(msg=msg)


class InvalidVlanIdConfigError(cfg.ConfigFileValueError):

    def __init__(self, vlan_id):
        msg = ('Invalid value given for setting `vlan_id` as \"{0}\". ' +
               'Please provide Integer values only.').format(vlan_id)
        super(InvalidVlanIdConfigError, self).__init__(msg=msg)


class InvalidUseDhcpConfigError(cfg.ConfigFileValueError):

    def __init__(self, use_dhcp):
        msg = ('Invalid value given for setting `use_dhcp` as {0}. ' +
               'Please provide either "True" or "False" only.').format(use_dhcp)
        super(InvalidUseDhcpConfigError, self).__init__(msg=msg)


class VcsDevicesNumberExceedsConfigError(cfg.ConfigFileValueError):

    def __init__(self, num_devices):
        msg = ('Number of vcs devices {0} exceeds the maximum allowed value 2. ' +
               'Please reduce the devices in cluster.').format(num_devices)
        super(VcsDevicesNumberExceedsConfigError, self).__init__(msg=msg)


class InvalidVcsDeviceIdConfigError(cfg.ConfigFileValueError):

    def __init__(self, vcs_device_id):
        msg = ('Invalid `vcs_device_id` {0}, it should be in the range 1-2. ' +
               'Please provide the proper `vcs_device_id`.').format(vcs_device_id)
        super(InvalidVcsDeviceIdConfigError, self).__init__(msg=msg)


class MissingMgmtIpConfigError(cfg.ConfigFileValueError):

    def __init__(self, vcs_device_id):
        msg = ('Missing `mgmt_ip_address` for vcs device with id {0}. ' +
               'Please provide management IP address').format(vcs_device_id)
        super(MissingMgmtIpConfigError, self).__init__(msg=msg)


class InvalidVCSDeviceCount(cfg.ConfigFileValueError):

    def __init__(self, device_count):
        msg = ('Number of devices in config should be 1 when VCS is not enabled, ' +
               'provided {0}').format(device_count)
        super(InvalidVCSDeviceCount, self).__init__(msg=msg)


class ThunderInUseByExistingProjectError(cfg.ConfigFileValueError):

    def __init__(self, config_ip_part, existing_ip_part, project_id):
        msg = ('Given IPAddress:Partition `{0}` in a10-octavia.conf is invalid. '
               'The project `{2}` is using IPAddress:Partition `{1}` already.').format(
            config_ip_part, existing_ip_part, project_id)
        super(ThunderInUseByExistingProjectError, self).__init__(msg=msg)


class ProjectInUseByExistingThunderError(cfg.ConfigFileValueError):

    def __init__(self, config_ip_part, existing_project_id, project_id):
        msg = ('Given project_id `{2}` in a10-octavia.conf is invalid. '
               'The given IPAddress:Partition `{0}` is getting used for project {1} '
               'already.').format(config_ip_part, existing_project_id, project_id)
        super(ProjectInUseByExistingThunderError, self).__init__(msg=msg)


class MissingVCSDeviceConfig(base.NetworkException):
    def __init__(self, device_ids):
        msg = ('Device ids {0} provided in config are not present in VCS' +
               'cluster.').format(device_ids)
        super(MissingVCSDeviceConfig, self).__init__(msg=msg)


class SNATConfigurationError(acos_errors.ACOSException):
    def __init__(self):
        msg = ('SNAT configuration does not work in DSR mode on Thunder '
               ' `autosnat` and `no_dest_nat` both are set True under `[listener]` '
               'section in a10-octavia.conf. ')
        super(SNATConfigurationError, self).__init__(msg=msg)


class PartitionNotActiveError(acos_errors.ACOSException):
    """ Occurs when the partition has been unloaded, but not deleted """

    def __init__(self, partition_name, device_ip):
        msg = ('Partition {0} on device {1} is set to Not-Active').format(partition_name,
                                                                          device_ip)
        super(PartitionNotActiveError, self).__init__(msg=msg)


class ParentProjectNotFound(keystone_exceptions.Error):
    """Occurs if no parent project found."""

    def __init__(self, project_id):
        msg = ('The project {0} does not have a parent or has default project'
               ' as parent. ').format(project_id)
        super(ParentProjectNotFound, self).__init__(message=msg)


class SharedPartitionTemplateNotSupported(acos_errors.FeatureNotSupported):
    """ Occurs when shared partition lookup for templates is not supported on acos client"""

    def __init__(self, resource, template_key):
        msg = ('Shared partition template lookup for [{0}] is not supported'
               ' on template `{1}`').format(resource, template_key)
        super(SharedPartitionTemplateNotSupported, self).__init__(code=505, msg=msg)


class PortIdMissing(keystone_exceptions.Error):
    """Occurs if no port_id when creating nat_pool table entry"""

    def __init__(self):
        msg = ('Unexpected condition, port_id is missing while creating '
               'entry for nat_pool table. ')
        super(PortIdMissing, self).__init__(message=msg)
