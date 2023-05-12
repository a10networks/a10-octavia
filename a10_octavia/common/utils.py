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
import ipaddress
import json
import netaddr
import socket
import struct

from ipaddress import ip_address
from ipaddress import IPv4Address
from ipaddress import IPv6Address
from oslo_config import cfg
from oslo_log import log as logging

from keystoneauth1.exceptions import http as keystone_exception
from keystoneclient.v3 import client as keystone_client
from octavia.common import keystone
from octavia.db import api as db_apis
from octavia.db import repositories as repo
from stevedore import driver as stevedore_driver

from a10_octavia.common import a10constants
from a10_octavia.common import data_models
from a10_octavia.common import exceptions

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


def validate_ipv4(address):
    """Validate for IP4 address format"""
    if not netaddr.valid_ipv4(address, netaddr.core.INET_PTON):
        raise cfg.ConfigFileValueError(
            'Invalid IPAddress value given in configuration: {0}'.format(address))


def validate_ipv6(IP: str):
    try:
        ipaddress.ip_address(IP)
        LOG.debug("Valid IP address")
    except ValueError:
        raise cfg.ConfigFileValueError(
            'Invalid IPAddress value given in configuration: {0}'.format(IP))


def validate_partial_ipv6(IP: str):
    try:
        ipaddress.ip_address(IP)
        LOG.debug("Valid IP address")
        return True
    except ValueError:
        return False


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
    if all(k in hardware_info for k in ('ip_address', 'username', 'password', 'device_name')):
        if all(hardware_info[x] is not None for x in ('ip_address',
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
        if (hardware_device.hierarchical_multitenancy != "enable" and
                hardware_device.device_name_as_key is not True):
            candidate = '{}:{}'.format(hardware_device.ip_address, hardware_device.partition_name)
            hardware_count_dict[candidate] = hardware_count_dict.get(candidate, 0) + 1
    return [k for k, v in hardware_count_dict.items() if v > 1]


def convert_to_hardware_thunder_conf(hardware_list):
    """Validate for all vthunder nouns for hardware devices configurations."""
    hardware_dict = {}
    for hardware_device in hardware_list:
        hardware_device = validate_params(hardware_device)
        hardware_device['undercloud'] = True
        if hardware_device.get('interface_vlan_map'):
            hardware_device['device_network_map'] = validate_interface_vlan_map(hardware_device)
            del hardware_device['interface_vlan_map']

        # Add dict entries with project_id as key
        if 'project_id' in hardware_device:
            project_id = hardware_device['project_id']
            if hardware_dict.get(project_id):
                raise cfg.ConfigFileValueError('Supplied duplicate project_id {} '
                                               ' in [hardware_thunder] section'.format(project_id))
            hierarchical_mt = hardware_device.get('hierarchical_multitenancy')
            if hierarchical_mt == "enable":
                hardware_device["partition_name"] = project_id[0:14]
            if hierarchical_mt and hierarchical_mt not in ('enable', 'disable'):
                raise cfg.ConfigFileValueError('Option `hierarchical_multitenancy` specified '
                                               'under project id {} only accepts "enable" and '
                                               '"disable"'.format(project_id))
            vthunder_conf = data_models.HardwareThunder(**hardware_device)
            hardware_dict[project_id] = vthunder_conf

        # Add dict entries with dev_name as key
        device_name = hardware_device['device_name']
        if hardware_dict.get(a10constants.DEVICE_KEY_PREFIX + device_name):
            raise cfg.ConfigFileValueError('Supplied duplicate device_name {} '
                                           ' in [hardware_thunder] section'.format(device_name))
        vthunder_conf = data_models.HardwareThunder(**hardware_device)
        vthunder_conf.device_name_as_key = True
        hardware_dict[(a10constants.DEVICE_KEY_PREFIX + device_name)] = vthunder_conf

        duplicates = check_duplicate_entries(hardware_dict)
        if duplicates:
            raise cfg.ConfigFileValueError('Duplicates found for the following '
                                           '\'ip_address:partition_name\' entries: {}'
                                           .format(list(duplicates)))
    return hardware_dict


def get_vip_security_group_name(port_id):
    if port_id:
        return a10constants.VIP_SEC_GROUP_PREFIX + port_id
    return None


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
                                      timeout=CONF.vthunder.default_axapi_timeout)
    return axapi_client


def get_net_info_from_cidr(cidr, ip_version):
    if ip_version == 4:
        subnet_ip, mask = cidr.split('/')
        avail_hosts = (1 << 32 - int(mask))
        netmask = socket.inet_ntoa(struct.pack('>I', (1 << 32) - avail_hosts))
        return subnet_ip, netmask
    else:
        ipv6_ip, ipv6_mask = ipaddress.IPv6Interface(cidr).with_netmask.split('/')
        return ipv6_ip, ipv6_mask


def check_ip_in_subnet_range(ip, subnet, netmask, ip_version, subnet_cidr):
    if ip_version == 4:
        if ip is None or subnet is None or netmask is None:
            return False
        int_ip = struct.unpack('>L', socket.inet_aton(ip))[0]
        int_subnet = struct.unpack('>L', socket.inet_aton(subnet))[0]
        int_netmask = struct.unpack('>L', socket.inet_aton(netmask))[0]
        return int_ip & int_netmask == int_subnet
    else:
        if ip is None or subnet_cidr is None:
            return False
        return ipaddress.IPv6Address(ip) in ipaddress.IPv6Network(subnet_cidr)


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


def get_patched_ip_address(ip, cidr, ip_version):
    net_ip, netmask = get_net_info_from_cidr(cidr, ip_version)
    if ip_version == 6:
        ip = ip.replace('.', "")
        is_valid_ip = validate_partial_ipv6(ip)
        if not is_valid_ip:
            ip = str(ipaddress.IPv6Address(net_ip)) + str(ip.replace(':', ""))
        if check_ip_in_subnet_range(ip, net_ip, netmask, ip_version, cidr):
            return ip
        else:
            raise exceptions.VRIDIPNotInSubentRangeError(ip, cidr)
    else:
        octets = ip.lstrip('.').split('.')

        if len(octets) == 4:
            validate_ipv4(ip)
            if check_ip_in_subnet_range(ip, net_ip, netmask, 4, None):
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
    vrid_fp = None
    if CONF.hardware_thunder.devices:
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


def get_natpool_addr_list(nat_flavor):
    addr_list = []
    if type(ip_address(nat_flavor['start_address'])) is IPv6Address:
        sh, sl = struct.unpack(">QQ",
                               socket.inet_pton(socket.AF_INET6, nat_flavor['start_address']))
        eh, el = struct.unpack(">QQ",
                               socket.inet_pton(socket.AF_INET6, nat_flavor['end_address']))
        while sl <= el:
            addr_list.append(socket.inet_ntop(socket.AF_INET6, struct.pack(">QQ", sh, sl)))
            sl += 1
    else:
        start = (struct.unpack(">L", socket.inet_aton(nat_flavor['start_address'])))[0]
        end = (struct.unpack(">L", socket.inet_aton(nat_flavor['end_address'])))[0]
        while start <= end:
            addr_list.append(socket.inet_ntoa(struct.pack(">L", start)))
            start += 1
    return addr_list


def get_loadbalancer_flavor(loadbalancer):
    flavor_repo = repo.FlavorRepository()
    flavor_profile_repo = repo.FlavorProfileRepository()
    flavor = {}
    flavor_id = loadbalancer.flavor_id
    if flavor_id:
        flavor = flavor_repo.get(db_apis.get_session(), id=flavor_id)
        if flavor and flavor.flavor_profile_id:
            flavor_profile = flavor_profile_repo.get(db_apis.get_session(),
                                                     id=flavor.flavor_profile_id)
            flavor_data = json.loads(flavor_profile.flavor_data)
            return flavor_data


def network_with_ipv6_subnet(network):
    network_driver = get_network_driver()
    for subnet_id in network.subnets:
        subnet = network_driver.get_subnet(subnet_id)
        if subnet.ip_version == 6:
            return True
    return False


def get_ipv6_address_from_conf(address_list, subnet_id, amp_network=False):
    final_address_list = []
    for address in address_list:
        address = json.loads(address)
        for key in address:
            if key == subnet_id:
                final_address_list.append({'ipv6-addr': address[key]})
    if amp_network:
        return final_address_list

    return final_address_list


def get_network_ipv6_address_from_conf(address_list, network):
    addr_list = []
    network_driver = get_network_driver()

    addr_list = get_ipv6_address_from_conf(address_list, network.id, True)
    if addr_list:
        return addr_list

    for subnet_id in network.subnets:
        subnet = network_driver.get_subnet(subnet_id)
        if subnet.ip_version == 6:
            new_addr_list = get_ipv6_address_from_conf(address_list, subnet_id, True)
            addr_list.extend(new_addr_list)
    return addr_list


def is_ipv6_subnet_in_conf(address_list, subnet_id):
    for address in address_list:
        address = json.loads(address)
        if address.get(subnet_id):
            return True
    return False


def get_ipv6_address(ifnum_oper, nics, address_list, loadbalancers_list):
    final_address_list = []
    has_v6_addr = False
    has_v4_addr = False
    opt_addr_only = CONF.a10_global.use_subnet_ipv6_addresses_only
    network_driver = get_network_driver()
    acos_mac_address = ifnum_oper['ethernet']['oper']['mac'].replace(".", "")
    for nic in nics:
        network = network_driver.get_network(nic.network_id)
        if network_with_ipv6_subnet(network) is False:
            continue

        neutron_port = network_driver.get_port(nic.port_id)
        port_mac_address = neutron_port.mac_address.replace(":", "")
        LOG.debug("[IPv6 Addr] get_ipv6_address get addr for mac:%s", port_mac_address)
        if port_mac_address == acos_mac_address:
            final_address_list = get_network_ipv6_address_from_conf(address_list, network)
            if final_address_list:
                has_v6_addr = True
            for fixed_ip in neutron_port.fixed_ips:
                if type(ip_address(fixed_ip.ip_address)) is IPv6Address:
                    if opt_addr_only and is_ipv6_subnet_in_conf(address_list, fixed_ip.subnet_id):
                        continue
                    addr_subnet = network_driver.get_subnet(fixed_ip.subnet_id)
                    subnet_prefix, subnet_mask = addr_subnet.cidr.split('/')
                    final_addr = fixed_ip.ip_address + '/' + subnet_mask
                    final_address_list.append({'ipv6-addr': final_addr})
                    LOG.debug("[IPv6 Addr] got: %s for mac: %s", final_addr, port_mac_address)
                    has_v6_addr = True
                if not has_v4_addr and type(ip_address(fixed_ip.ip_address)) is IPv4Address:
                    has_v4_addr = True
            break
    return final_address_list, (has_v6_addr and has_v4_addr)


def set_dual_stack(ifnum_address, ifnum):
    ifnum_address[(ifnum + a10constants.DUAL_STACK_MASK)] = True


def is_dual_stack(ifnum_address, ifnum):
    if (ifnum + a10constants.DUAL_STACK_MASK) in ifnum_address:
        return True
    return False


def get_acos_parameter_for_vrid(ip_version, partition):
    if ip_version == 6 and partition == "shared":
        IP_address = a10constants.IPV6_ADDRESS
        IP_address_cfg = a10constants.IPV6_ADDRESS_CFG
    elif ip_version == 6 and partition != "shared":
        IP_address = a10constants.IPV6_ADDRESS_PARTITION
        IP_address_cfg = a10constants.IPV6_ADDRESS_PARTITION_CFG
    elif ip_version == 4 and partition == "shared":
        IP_address = a10constants.IP_ADDRESS
        IP_address_cfg = a10constants.IP_ADDRESS_CFG
    else:
        IP_address = a10constants.IP_ADDRESS_PARTITION
        IP_address_cfg = a10constants.IP_ADDRESS_PARTITION_CFG
    return IP_address, IP_address_cfg
