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

from octavia.network import data_models as n_data_models
from octavia.network.drivers.neutron import allowed_address_pairs
from octavia.network.drivers.neutron import utils

from a10_octavia.common import exceptions
from a10_octavia.network import data_models

LOG = logging.getLogger(__name__)
PROJECT_ID_ALIAS = 'project-id'
VIP_SECURITY_GRP_PREFIX = 'lb-'
OCTAVIA_OWNER = 'Octavia'

CONF = cfg.CONF


class A10OctaviaNeutronDriver(allowed_address_pairs.AllowedAddressPairsDriver):

    def __init__(self):
        super(allowed_address_pairs.AllowedAddressPairsDriver, self).__init__()
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
                             'device_owner': OCTAVIA_OWNER,
                             'fixed_ips': [{'subnet_id': subnet_id}]}}
            if fixed_ip:
                port['port']['fixed_ips'][0]['ip_address'] = fixed_ip
            new_port = self.neutron_client.create_port(port)
            new_port = utils.convert_port_dict_to_model(new_port)
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

    def reserve_subnet_addresses(self, subnet_id, addr_list):
        subnet = self.get_subnet(subnet_id)
        try:
            port = {'port': {'name': 'octavia-port-' + subnet.network_id,
                             'network_id': subnet.network_id,
                             'admin_state_up': True,
                             'device_owner': OCTAVIA_OWNER,
                             'fixed_ips': []}}
            for addr in addr_list:
                fixed_ip = {'subnet_id': subnet_id, 'ip_address': addr}
                port['port']['fixed_ips'].append(fixed_ip)
            new_port = self.neutron_client.create_port(port)
            new_port = utils.convert_port_dict_to_model(new_port)
        except Exception as e:
            LOG.exception(str(e))
            raise e
        return new_port

    def get_port_id_from_ip(self, ip):
        try:
            ports = self.neutron_client.list_ports(device_owner=OCTAVIA_OWNER)
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
