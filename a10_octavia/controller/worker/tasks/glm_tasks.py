#    Copyright 2021, A10 Networks
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

import acos_client
from acos_client import errors as acos_errors

from requests import exceptions as req_exceptions
from taskflow import task

from oslo_config import cfg
from oslo_log import log as logging

from a10_octavia.common import utils as a10_utils
from a10_octavia.controller.worker.tasks.decorators import axapi_client_decorator
from a10_octavia.controller.worker.tasks.decorators import axapi_client_decorator_for_revert

CONF = cfg.CONF
LOG = logging.getLogger(__name__)



class DNSConfiguration(task.Task):

    def __init__(self, **kwargs):
        super(DNSConfiguration, self).__init__(**kwargs)
        self._network_driver = None

    @property
    def network_driver(self):
        if self._network_driver is None:
            self._network_driver = a10_utils.get_network_driver()
        return self._network_driver

    def _get_dns_nameservers(self, flavor_data=None):
        license_net_id = CONF.glm_license.amp_license_network
        license_net = self.network_driver.get_network(license_net_id)
        license_subnet_id = license_net[0]
        license_subnet = self.network_driver.get_subnet(license_subnet_id)

        primary_dns = None
        secondary_dns = None
        subnet_dns = license_subnet.get('dns_nameservers')
        if len(subnet_dns) == 1:
            primary_dns = subnet_dns[0]
        elif len(subnet_dns) >= 2:
            primary_dns = subnet_dns[0]
            secondary_dns = subnet_dns[1]
            if len(subnet_dns) > 2:
                LOG.warning("More than one DNS nameserver detected on subnet %s. "
                            "Using %s as primary and %s as secondary.",
                            license_subnet_id, primary_dns, secondary_dns)
        
        if CONF.glm_license.primary_dns:
            primary_dns = CONF.glm_license.primary_dns
        
        if CONF.glm_license.secondary_dns:
            secondary_dns = CONF.glm_license.secondary_dns

        if flavor_data:
            dns_flavor = flavor_data.get('dns')
            if dns_flavor and dns_flavor.get('primary_dns'):
                primary_dns = dns_flavor.get('primary_dns')
            if dns_flavor and dns_flavor.get('secondary_dns'):
                secondary_dns = dns_flavor.get('secondary_dns')

        return primary_dns, secondary_dns

    @axapi_client_decorator
    def execute(self, vthunder, flavor_data=None):
        primary_dns, secondary_dns = self._get_dns_nameservers(flavor_data)
        try:
            self.axapi_client.set(primary_dns, secondary_dns)
        except acos_errors.ACOSException as e:
            LOG.error("Could not set DNS configuration for amphora %s",
                      vthunder.amphora_id)
            raise e
    
    @axapi_client_decorator_for_revert
    def revert(self, vthunder, flavor_data, *args, **kwargs):
        primary_dns, secondary_dns = self._get_dns_nameservers(flavor_data)
        try:
            self.axapi_client.delete(primary_dns, secondary_dns)
        except req_exceptions.ConnectionError:
            LOG.exception("Failed to connect A10 Thunder device: %s", vthunder.ip_address)