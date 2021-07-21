#    Copyright 2019, A10 Networks
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

from neutronclient.common import exceptions as neutron_client_exceptions
from oslo_config import cfg
from oslo_log import log as logging
from stevedore import driver as stevedore_driver

from octavia.common import constants
from octavia.i18n import _
from octavia.network import base
from octavia.network import data_models as n_data_models
from octavia.network.drivers.neutron import allowed_address_pairs as aap
from octavia.network.drivers.neutron import utils

from a10_octavia.common import a10constants
from a10_octavia.common import exceptions
from a10_octavia.network import data_models

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class A10OctaviaNeutronDriver(aap.AllowedAddressPairsDriver):

    def __init__(self):
        super(aap.AllowedAddressPairsDriver, self).__init__()
        self.compute = stevedore_driver.DriverManager(
            namespace='octavia.compute.drivers',
            name=CONF.controller_worker.compute_driver,
            invoke_on_load=True
        ).driver

    def _port_to_parent_port(self, port):
        fixed_ips = [n_data_models.FixedIP(subnet_id=fixed_ip.get('subnet_id'),
                                           ip_address=fixed_ip.get('ip_address'))
                     for fixed_ip in port.get('fixed_ips', [])]

        trunk_id = port['trunk_details']['trunk_id'] if port.get('trunk_details') else None
        subports = port['trunk_details']['sub_ports'] if port.get('trunk_details') else None
        subport_list = []
        if subports:
            subport_list = [data_models.Subport(segmentation_id=subport['segmentation_id'],
                                                port_id=subport['port_id'],
                                                segmentation_type=subport['segmentation_type'],
                                                mac_address=subport['mac_address'])
                            for subport in subports]
        return data_models.ParentPort(id=port.get('id'),
                                      name=port.get('name'),
                                      device_id=port.get('device_id'),
                                      device_owner=port.get('device_owner'),
                                      mac_address=port.get('mac_address'),
                                      network_id=port.get('network_id'),
                                      status=port.get('status'),
                                      project_id=port.get('project_id'),
                                      admin_state_up=port.get('admin_state_up'),
                                      fixed_ips=fixed_ips,
                                      qos_policy_id=port.get('qos_policy_id'),
                                      trunk_id=trunk_id, subports=subport_list)

    def _subport_model_to_dict(self, subport):
        return {'port_id': subport.port_id,
                'segmentation_type': subport.segmentation_type,
                'segmentation_id': subport.segmentation_id}

    def allocate_trunk(self, parent_port_id):
        payload = {"trunk": {"port_id": parent_port_id,
                             "admin_state_up": "true"}}
        try:
            new_trunk = self.neutron_client.create_trunk(payload)
        except Exception:
            message = "Error creating trunk on port "
            "{port_id}".format(
                port_id=parent_port_id)
            LOG.exception(message)
            raise exceptions.AllocateTrunkException(message)

        return new_trunk

    def deallocate_trunk(self, trunk_id):
        try:
            self.neutron_client.delete_trunk(trunk_id)
        except Exception:
            message = 'Trunk {0} already deleted.Skipping'.format(trunk_id)
            LOG.exception(message)
            raise exceptions.DeallocateTrunkException(message)

    def _build_subport_payload(self, subports):
        payload = {'sub_ports': []}
        for subport in subports:
            payload['sub_ports'].append(self._subport_model_to_dict(subport))
        return payload

    def plug_trunk_subports(self, trunk_id, subports):
        payload = self._build_subport_payload(subports)
        updated_trunk = None
        try:
            updated_trunk = self.neutron_client.trunk_add_subports(trunk_id, payload)
        except Exception:
            message = "Error adding subports"
            LOG.exception(message)

        return updated_trunk

    def unplug_trunk_subports(self, trunk_id, subports):
        payload = self._build_subport_payload(subports)

        try:
            self.neutron_client.trunk_remove_subports(trunk_id, payload)
        except Exception:
            message = "Error deleting subports"
            LOG.exception(message)

    def _add_security_group_to_port(self, sec_grp_id, port_id):
        port = self.neutron_client.show_port(port_id)
        port['port']['security_groups'].append(sec_grp_id)
        sec_grp_list = port['port']['security_groups']
        payload = {'port': {'security_groups': sec_grp_list}}
        # Note: Neutron accepts the SG even if it already exists
        try:
            self.neutron_client.update_port(port_id, payload)
        except neutron_client_exceptions.PortNotFoundClient as e:
            raise base.PortNotFound(str(e))
        except Exception as e:
            raise base.NetworkException(str(e))

    def _remove_security_group(self, port, sec_grp_id):
        port['security_groups'].remove(sec_grp_id)
        payload = {'port': {'security_groups': port['security_groups']}}
        try:
            self.neutron_client.update_port(port['id'], payload)
        except neutron_client_exceptions.PortNotFoundClient as e:
            raise base.PortNotFound(str(e))
        except Exception as e:
            raise base.NetworkException(str(e))

    def _cleanup_port(self, vip_port_id, port):
        try:
            self.neutron_client.delete_port(port['id'])
        except (neutron_client_exceptions.NotFound,
                neutron_client_exceptions.PortNotFoundClient):
            if port['id'] == vip_port_id:
                LOG.debug('VIP port %s already deleted. Skipping.', port['id'])
            else:
                LOG.warning("Can't deallocate instance port {0} because it "
                            "cannot be found in neutron. "
                            "Continuing cleanup.".format(port['id']))
        except Exception:
            message = _('Error deleting VIP port_id {port_id} from '
                        'neutron').format(port_id=port['id'])
            LOG.exception(message)
            raise base.DeallocateVIPException(message)

    def _get_instance_ports_by_subnet(self, compute_id, subnet_id):
        amp_ports = self.neutron_client.list_ports(device_id=compute_id)

        filtered_ports = []
        for port in amp_ports.get('ports', []):
            for fixed_ips in port.get('fixed_ips', []):
                if (fixed_ips.get('subnet_id') == subnet_id and
                        port.get('device_owner') == a10constants.OCTAVIA_OWNER):
                    filtered_ports.append(port)
        return filtered_ports

    def _get_ports_by_security_group(self, sec_grp_id):
        all_ports = self.neutron_client.list_ports()
        filtered_ports = []
        for port in all_ports.get('ports', []):
            if sec_grp_id in port.get('security_groups', []):
                filtered_ports.append(port)
        return filtered_ports

    def deallocate_vip(self, loadbalancer, lb_count_subnet):
        """Delete the vrrp_port (instance port) in case nova didn't
        This can happen if a failover has occurred.
        """
        ports = []
        sec_grp = None
        vip_port_id = loadbalancer.vip.port_id
        fixed_subnets = CONF.a10_controller_worker.amp_boot_network_list[:]
        subnet = self.get_subnet(loadbalancer.vip.subnet_id)
        if subnet.network_id in fixed_subnets and lb_count_subnet != 0:
            lb_count_subnet = lb_count_subnet + 1

        if self.sec_grp_enabled:
            sec_grp = self._get_lb_security_group(loadbalancer.id)
            if sec_grp:
                ports = self._get_ports_by_security_group(sec_grp['id'])

        if not self.sec_grp_enabled or not ports:
            ports.append(self.neutron_client.show_port(vip_port_id))
            for amphora in loadbalancer.amphorae:
                ports.extend(self._get_instance_ports_by_subnet(
                    amphora.compute_id, loadbalancer.vip.subnet_id))

        for port in ports:
            port = port.get('port', port)
            """If lb_count_subnet is greater then 1 then
            vNIC port is in use by other lbs. Only delete VIP port.
            In-case of deleting lb(ERROR state),
            vthunder returned value from database is "None" then
            lb_count_subnet is equal to 0, in this case delete only vip port."""
            if lb_count_subnet != 1:
                if sec_grp:
                    self._remove_security_group(port, sec_grp['id'])
                if port['id'] == vip_port_id:
                    self._cleanup_port(vip_port_id, port)
            else:  # This is the only lb using vNIC ports
                self._cleanup_port(vip_port_id, port)

        if sec_grp:
            self._delete_vip_security_group(sec_grp['id'])

        for amphora in filter(
                lambda amp: amp.status == constants.AMPHORA_ALLOCATED,
                loadbalancer.amphorae):
            interface = self._get_plugged_interface(
                amphora.compute_id, subnet.network_id, amphora.lb_network_ip)
            if interface is not None:
                self._remove_allowed_address_pair_from_port(
                    interface.port_id, loadbalancer.vip.ip_address)

    def get_plugged_parent_port(self, vip):
        parent_port = None
        try:
            port = self.neutron_client.show_port(vip.port_id)
            parent_port = self._port_to_parent_port(port.get("port"))
        except Exception:
            LOG.debug('Couldn\'t retrieve port with id: {}'.format(vip.port_id))

        return parent_port

    def create_port(self, network_id, subnet_id=None, fixed_ip=None):
        new_port = None
        if not subnet_id:
            subnet_id = self.get_network(network_id).subnets[0]
        try:
            port = {'port': {'name': 'octavia-port-' + network_id,
                             'network_id': network_id,
                             'admin_state_up': True,
                             'device_owner': a10constants.OCTAVIA_OWNER,
                             'fixed_ips': [{'subnet_id': subnet_id}]}}
            if fixed_ip:
                port['port']['fixed_ips'][0]['ip_address'] = fixed_ip
            new_port = self.neutron_client.create_port(port)
        except Exception:
            message = "Error creating port in network: {0}".format(network_id)
            LOG.exception(message)
            raise exceptions.PortCreationFailedException(message)
        return new_port

    def delete_port(self, port_id):
        try:
            self.neutron_client.delete_port(port_id)
        except neutron_client_exceptions.PortNotFoundClient:
            pass
        except Exception:
            message = "Error deleting port: {0}".format(port_id)
            LOG.exception(message)

    def reserve_subnet_addresses(self, subnet_id, addr_list, amphorae):
        subnet = self.get_subnet(subnet_id)
        try:
            port = {'port': {'name': 'octavia-port-' + subnet.network_id,
                             'network_id': subnet.network_id,
                             'admin_state_up': True,
                             'device_owner': a10constants.OCTAVIA_OWNER,
                             'fixed_ips': []}}
            for addr in addr_list:
                fixed_ip = {'subnet_id': subnet_id, 'ip_address': addr}
                port['port']['fixed_ips'].append(fixed_ip)
            new_port = self.neutron_client.create_port(port)
            new_port = utils.convert_port_dict_to_model(new_port)
            if amphorae is not None:
                for amphora in filter(
                        lambda amp: amp.status == constants.AMPHORA_ALLOCATED,
                        amphorae):
                    interface = self._get_plugged_interface(
                        amphora.compute_id, subnet.network_id, amphora.lb_network_ip)
                    self._add_allowed_address_pair_to_port(interface.port_id, addr_list)
        except Exception as e:
            LOG.exception(str(e))
            raise e
        return new_port

    def release_subnet_addresses(self, subnet_id, addr_list, amphorae):
        try:
            subnet = self.get_subnet(subnet_id)
            for amphora in filter(
                    lambda amp: amp.status == constants.AMPHORA_ALLOCATED,
                    amphorae):
                interface = self._get_plugged_interface(
                    amphora.compute_id, subnet.network_id, amphora.lb_network_ip)
                if interface is not None:
                    self._remove_allowed_address_pair_from_port(interface.port_id, addr_list)
        except Exception as e:
            LOG.exception(str(e))
            raise e

    def get_port_id_from_ip(self, ip):
        try:
            ports = self.neutron_client.list_ports(device_owner=a10constants.OCTAVIA_OWNER)
            if not ports or not ports.get('ports'):
                return None
            for port in ports['ports']:
                if port.get('fixed_ips'):
                    fixed_ips = port['fixed_ips']
                    for ipaddr in fixed_ips:
                        if ipaddr.get('ip_address') == ip:
                            return port['id']
        except (neutron_client_exceptions.NotFound,
                neutron_client_exceptions.PortNotFoundClient):
            pass
        except Exception:
            message = _('Error listing ports, ip {} ').format(ip)
            LOG.exception(message)
            pass
        return None

    def list_networks(self):
        network_list = self.neutron_client.list_networks()
        network_list_datamodel = []

        for network in network_list.get('networks'):
            network_list_datamodel.append(n_data_models.Network(
                id=network.get('id'),
                name=network.get('name'),
                subnets=network.get('subnets'),
                project_id=network.get('project_id'),
                admin_state_up=network.get('admin_state_up'),
                mtu=network.get('mtu'),
                provider_network_type=network.get('provider:network_type'),
                provider_physical_network=network.get('provider:physical_network'),
                provider_segmentation_id=network.get('provider:segmentation_id'),
                router_external=network.get('router:external')))
        return network_list_datamodel

    def _add_allowed_address_pair_to_port(self, port_id, ip_address):
        port = self.neutron_client.show_port(port_id)
        aap_ips = port['port']['allowed_address_pairs']
        if isinstance(ip_address, list):
            for ip in ip_address:
                aap_ips.append({'ip_address': ip})
        else:
            aap_ips.append({'ip_address': ip_address})
        aap = {
            'port': {
                'allowed_address_pairs': aap_ips
            }
        }
        self.neutron_client.update_port(port_id, aap)

    def allocate_vrid_fip(self, vrid, network_id, amphorae, fixed_ip=None):

        fixed_ip_json = {}
        if vrid.subnet_id:
            fixed_ip_json['subnet_id'] = vrid.subnet_id
        if fixed_ip:
            fixed_ip_json['ip_address'] = fixed_ip

        # Make sure we are backward compatible with older neutron
        if self._check_extension_enabled(aap.PROJECT_ID_ALIAS):
            project_id_key = 'project_id'
        else:
            project_id_key = 'tenant_id'

        # It can be assumed that network_id exists
        port = {'port': {'name': 'octavia-vrid-fip-' + vrid.id,
                         'network_id': network_id,
                         'admin_state_up': False,
                         'device_id': 'vrid-{0}'.format(vrid.id),
                         'device_owner': aap.OCTAVIA_OWNER,
                         project_id_key: vrid.owner}}
        if fixed_ip_json:
            port['port']['fixed_ips'] = [fixed_ip_json]

        try:
            new_port = self.neutron_client.create_port(port)
        except Exception as e:
            message = _('Error creating neutron port on network '
                        '{network_id}.').format(
                network_id=network_id)
            LOG.exception(message)
            raise base.AllocateVIPException(
                message,
                orig_msg=getattr(e, 'message', None),
                orig_code=getattr(e, 'status_code', None),
            )
        new_port = utils.convert_port_dict_to_model(new_port)

        fixed_ip = new_port.fixed_ips[0].ip_address
        for amphora in filter(
            lambda amp: amp.status == constants.AMPHORA_ALLOCATED,
                amphorae):
            interface = self._get_plugged_interface(
                amphora.compute_id, network_id, amphora.lb_network_ip)
            self._add_allowed_address_pair_to_port(interface.port_id, fixed_ip)

        return new_port

    def allow_use_any_source_ip_on_egress(self, network_id, amphora):
        interface = self._get_plugged_interface(
            amphora.compute_id, network_id, amphora.lb_network_ip)
        if interface:
            port = self.neutron_client.show_port(interface.port_id)
            aap_ips = port['port']['allowed_address_pairs']
            for aap_ip in aap_ips:
                if aap_ip['ip_address'] == '0.0.0.0/0':
                    break
            else:
                self._add_allowed_address_pair_to_port(interface.port_id, '0.0.0.0/0')
        else:
            raise exceptions.InterfaceNotFound(amphora.compute_id, network_id)

    def remove_any_source_ip_on_egress(self, network_id, amphora):
        interface = self._get_plugged_interface(
            amphora.compute_id, network_id, amphora.lb_network_ip)
        if interface is not None:
            self._remove_allowed_address_pair_from_port(interface.port_id, '0.0.0.0/0')

    def _remove_allowed_address_pair_from_port(self, port_id, ip_address):
        try:
            port = self.neutron_client.show_port(port_id)
        except neutron_client_exceptions.PortNotFoundClient:
            LOG.warning("Can't deallocate AAP from instance port {0} because it "
                        "cannot be found in neutron. "
                        "Continuing cleanup.".format(port_id))
            return

        aap_ips = port['port']['allowed_address_pairs']
        if isinstance(ip_address, list):
            updated_aap_ips = aap_ips
            for ip in ip_address:
                updated_aap_ips = [aap_ip for aap_ip in updated_aap_ips
                                   if aap_ip['ip_address'] != ip]
        else:
            updated_aap_ips = [aap_ip for aap_ip in aap_ips if aap_ip['ip_address'] != ip_address]
        if len(aap_ips) != len(updated_aap_ips):
            aap = {
                'port': {
                    'allowed_address_pairs': updated_aap_ips,
                }
            }
            self.neutron_client.update_port(port_id, aap)

    def deallocate_vrid_fip(self, vrid, subnet, amphorae):
        self.delete_port(vrid.vrid_port_id)
        for amphora in filter(
            lambda amp: amp.status == constants.AMPHORA_ALLOCATED,
                amphorae):
            interface = self._get_plugged_interface(
                amphora.compute_id, subnet.network_id,
                amphora.lb_network_ip)
            if interface is not None:
                self._remove_allowed_address_pair_from_port(
                    interface.port_id, vrid.vrid_floating_ip)

    def unplug_vip_revert(self, load_balancer, vip):
        "This method is called by revert flow of PlugVip"

        try:
            subnet = self.get_subnet(vip.subnet_id)
        except base.SubnetNotFound:
            msg = ("Can't unplug vip because vip subnet {0} was not "
                   "found").format(vip.subnet_id)
            LOG.exception(msg)
            raise base.PluggedVIPNotFound(msg)
        for amphora in filter(
                lambda amp: amp.status == constants.AMPHORA_ALLOCATED,
                load_balancer.amphorae):
            self.unplug_aap_port_revert(vip, amphora, subnet)

    def unplug_aap_port_revert(self, vip, amphora, subnet):
        interface = self._get_plugged_interface(
            amphora.compute_id, subnet.network_id, amphora.lb_network_ip)
        if not interface:
            # Thought about raising PluggedVIPNotFound exception but
            # then that wouldn't evaluate all amphorae, so just continue
            LOG.debug('Cannot get amphora %s interface, skipped',
                      amphora.compute_id)
            return
        try:
            self._remove_allowed_address_pair_from_port(interface.port_id, vip.ip_address)
        except Exception:
            message = _('Error unplugging VIP. Could not clear '
                        'allowed address pairs from port '
                        '{port_id}.').format(port_id=vip.port_id)
            LOG.exception(message)
            raise base.UnplugVIPException(message)

        # Delete the VRRP port if we created it
        try:
            port = self.get_port(amphora.vrrp_port_id)
            if port.name.startswith('octavia-lb-vrrp-'):
                self.neutron_client.delete_port(amphora.vrrp_port_id)
        except (neutron_client_exceptions.NotFound,
                neutron_client_exceptions.PortNotFoundClient):
            pass
        except Exception as e:
            LOG.error('Failed to delete port.  Resources may still be in '
                      'use for port: %(port)s due to error: %(except)s',
                      {constants.PORT: amphora.vrrp_port_id, 'except': str(e)})
