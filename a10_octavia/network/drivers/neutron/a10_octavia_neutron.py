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

import ipaddress
import time

from neutronclient.common import exceptions as neutron_client_exceptions
from novaclient import exceptions as nova_client_exceptions
from oslo_config import cfg
from oslo_log import log as logging
import six
from stevedore import driver as stevedore_driver

from octavia.common import constants
from octavia.common import data_models
from octavia.common import exceptions
from octavia.i18n import _
from octavia.network import base
from octavia.network import data_models as n_data_models
from octavia.network.drivers.neutron.allowed_address_pairs import AllowedAddressPairsDriver 
from octavia.network.drivers.neutron import utils

from a10_octavia.network import data_models

LOG = logging.getLogger(__name__)
#A10_Net_EXT_ALIAS = ''
PROJECT_ID_ALIAS = 'project-id'
VIP_SECURITY_GRP_PREFIX = 'lb-'
OCTAVIA_OWNER = 'Octavia'

CONF = cfg.CONF


class A10OctaviaNeutronDriver(AllowedAddressPairsDriver):

    def __init__(self):
        super(AllowedAddressPairsDriver, self).__init__()
        #self._check_a10_network_driver_loaded(self)
        self.compute = stevedore_driver.DriverManager(
            namespace='octavia.compute.drivers',
            name=CONF.controller_worker.compute_driver,
            invoke_on_load=True
        ).driver


    #def _check_a10_network_driver_loaded(self):
    #    if not self._check_extension_enabled(AAP_EXT_ALIAS):
    #        raise base.NetworkException(
    #            'The {alias} extension is not enabled in neutron.  This '
    #            'driver cannot be used with the {alias} extension '
    #            'disabled.'.format(alias=AAP_EXT_ALIAS))

    def _port_to_parent_port(self, port):
        fixed_ips = [n_data_models.FixedIP(subnet_id=fixed_ip.get('subnet_id'),
                                            ip_address=fixed_ip.get('ip_address'))
                     for fixed_ip in port.get('fixed_ips', [])]

        trunk_id = port['trunk_details']['trunk_id'] if port.get('trunk_details') else None
        subports = port['trunk_details']['sub_ports'] if port.get('trunk_details') else None
        subport_list = []
        if subports:
            subport_list = [data_models.Subport(segmentation_id=subports['segmentation_id'],
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

    def create_port(self, network_id):
        try:
            port = {'port': {'name': 'octavia-port-' + network_id,
                             'network_id': network_id,
                             'admin_state_up': True,
                             'device_owner': OCTAVIA_OWNER}}
            new_port = self.neutron_client.create_port(port)
            new_port = utils.convert_port_dict_to_model(new_port)
            LOG.debug('Create subport with id: ')
        except Exception:
            message = _('ERROR creating port')
            LOG.exception(message)
            # raise base.SubPortException

        return new_port

    def deallocate_security_group(self, vip):
        """Delete the sec group (instance port) in case nova didn't

        This can happen if a failover has occurred.
        """
        try:
            port = self.get_port(vip.port_id)
        except base.PortNotFound:
            LOG.warning("Can't deallocate VIP because the vip port {0} "
                        "cannot be found in neutron. "
                        "Continuing cleanup.".format(vip.port_id))
            port = None

        self._delete_security_group(vip, port)

    def allocate_trunk(self, parent_port_id):
        payload = {"trunk": { "port_id": parent_port_id,
                              "admin_state_up": "true"}}
        try:
            new_trunk = self.neutron_client.create_trunk(payload) 
        except Exception:
            message = _('Error creating trunk on port '
                        '{port_id}'.format(
                            port_id=parent_port_id))
            LOG.exception(message)
            # raise CustomTrunkException(msg) 

        return new_trunk

    def plug_trunk_subport(self, trunk_id, subports):
        payload = {'sub_ports': []}
        for subport in subports:
            payload['sub_ports'].append(self.subport_model_to_dict(subport))

        try:
            updated_trunk = self.neutron_client.trunk_add_subports(trunk_id, payload)
        except Exception:
            message = _('Error adding subports')
            LOG.exception(messag)

        return updated_trunk

    def get_plugged_parent_port(self, loadbalancer):
        try:
            port = self.neutron_client.show_port(loadbalancer.vip.port_id)
            parent_port = self._port_to_parent_port(port.get("port"))
        except Exception:
            LOG.debug('Couldn\'t retrieve port with id: {}'.format(loadbalancer.vip.port_id))

        return parent_port
