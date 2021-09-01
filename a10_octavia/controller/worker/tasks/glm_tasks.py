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

from acos_client import errors as acos_errors

from requests import exceptions as req_exceptions
from taskflow import task

from oslo_config import cfg
from oslo_log import log as logging

from a10_octavia.common import exceptions as a10_ex
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

    def _get_dns_nameservers(self, vthunder, flavor=None):
        license_net_id = CONF.glm_license.amp_license_network
        if not license_net_id:
            license_net_id = CONF.a10_controller_worker.amp_mgmt_network
            if not license_net_id:
                if len(CONF.a10_controller_worker.amp_boot_network_list) >= 1:
                    license_net_id = CONF.a10_controller_worker.amp_boot_network_list[0]
                else:
                    LOG.warning("No networks were configured therefore "
                                "nameservers cannot be set.")
                    return None, None

        license_net = self.network_driver.get_network(license_net_id)
        if len(license_net.subnets) < 1:
            LOG.warning("Network %s did not have subnet configured "
                        "therefore nameservers cannot be set.", license_net_id)
            return None, None
        license_subnet_id = license_net.subnets[0]
        license_subnet = self.network_driver.show_subnet_detailed(license_subnet_id)

        primary_dns = None
        secondary_dns = None
        subnet_dns = license_subnet.get('dns_nameservers', [])
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

        if flavor:
            dns_flavor = flavor.get('dns')
            if dns_flavor and dns_flavor.get('primary-dns'):
                primary_dns = dns_flavor.get('primary-dns')
            if dns_flavor and dns_flavor.get('secondary-dns'):
                secondary_dns = dns_flavor.get('secondary-dns')

        return primary_dns, secondary_dns

    @axapi_client_decorator
    def execute(self, vthunder, flavor=None):
        if not vthunder:
            LOG.warning("No vthunder therefore dns cannot be assigned.")
            return None

        primary_dns, secondary_dns = self._get_dns_nameservers(vthunder, flavor)
        if not primary_dns and secondary_dns:
            LOG.error("A secondary DNS with IP %s was specified without a primary DNS",
                      primary_dns)
            raise a10_ex.PrimaryDNSMissing(secondary_dns)
        elif not primary_dns and not secondary_dns:
            return None

        try:
            self.axapi_client.dns.set(primary_dns, secondary_dns)
        except acos_errors.ACOSException as e:
            LOG.error("Could not set DNS configuration for amphora %s",
                      vthunder.amphora_id)
            raise e

    @axapi_client_decorator_for_revert
    def revert(self, vthunder, flavor=None, *args, **kwargs):
        primary_dns, secondary_dns = self._get_dns_nameservers(vthunder, flavor)
        if not primary_dns and not secondary_dns:
            return None

        try:
            self.axapi_client.dns.delete(primary_dns, secondary_dns)
        except req_exceptions.ConnectionError:
            LOG.exception("Failed to connect A10 Thunder device: %s", vthunder.ip_address)


class ActivateFlexpoolLicense(task.Task):

    @axapi_client_decorator
    def execute(self, vthunder, amphora):
        if not vthunder:
            LOG.warning("No vthunder therefore licensing cannot occur.")
            return None

        amp_mgmt_net = CONF.a10_controller_worker.amp_mgmt_network
        amp_boot_nets = CONF.a10_controller_worker.amp_boot_network_list
        token = CONF.glm_license.flexpool_token
        bandwidth = CONF.glm_license.allocate_bandwidth
        hostname = "amphora-" + amphora.id
        hostname = hostname[0:31]
        use_mgmt_port = False

        license_net_id = CONF.glm_license.amp_license_network
        if not license_net_id:
            license_net_id = CONF.a10_controller_worker.amp_mgmt_network
            if not license_net_id:
                if len(CONF.a10_controller_worker.amp_boot_network_list) >= 1:
                    license_net_id = CONF.a10_controller_worker.amp_boot_network_list[0]
                else:
                    LOG.warning("No networks were configured therefore "
                                "nameservers cannot be set.")
                    return None

        # ID provided to amp_license_network may be equal other provided mgmt network IDs
        if (license_net_id == amp_mgmt_net or
                (amp_boot_nets and license_net_id == amp_boot_nets[0])):
            use_mgmt_port = True

        interfaces = self.axapi_client.interface.get_list()
        for i in range(len(interfaces['interface']['ethernet-list'])):
            if interfaces['interface']['ethernet-list'][i]['action'] == "disable":
                ifnum = interfaces['interface']['ethernet-list'][i]['ifnum']
                self.axapi_client.system.action.setInterface(ifnum)

        try:
            self.axapi_client.system.action.set_hostname(hostname)
            self.axapi_client.glm.create(
                token=token,
                allocate_bandwidth=bandwidth,
                use_mgmt_port=use_mgmt_port
            )
            self.axapi_client.glm.send.create(license_request=1)
        except acos_errors.ACOSException as e:
            LOG.error("Could not activate license for amphora %s", amphora.id)
            raise e

    @axapi_client_decorator_for_revert
    def revert(self, vthunder, flavor=None, *args, **kwargs):
        try:
            self.axapi_client.delete.glm_license.post()
        except req_exceptions.ConnectionError:
            LOG.exception("Failed to connect A10 Thunder device: %s", vthunder.ip_address)


class RevokeFlexpoolLicense(task.Task):

    @axapi_client_decorator
    def execute(self, vthunder):
        if not vthunder:
            LOG.warning("No vthunder therefore license revocation cannot occur.")
            return None
        self.axapi_client.delete.glm_license.post()


class ConfigureForwardProxyServer(task.Task):

    @axapi_client_decorator
    def execute(self, vthunder):
        if not vthunder:
            LOG.warning("No vthunder therefore forward proxy server cannot be configured.")
            return
        host = CONF.glm_license.proxy_host
        port = CONF.glm_license.proxy_port
        username = CONF.glm_license.proxy_username
        enable_password = CONF.glm_license.proxy_password
        if host and port:
            try:
                if enable_password:
                    secret_string = CONF.glm_license.proxy_secret_string \
                        if CONF.glm_license.proxy_secret_string else ""
                    self.axapi_client.glm_proxy_server.create(host, port, username,
                                                              enable_password, secret_string)
                else:
                    self.axapi_client.glm_proxy_server.create(host, port, username)
            except acos_errors.ACOSException as e:
                LOG.error("Could not configure forward proxy server for A10 "
                          "Thunder device", vthunder.ip_address)
                raise e
        else:
            LOG.warning("Please provide forward proxy server IP address and port. ")
            return