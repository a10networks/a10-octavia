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
from a10_octavia.controller.worker.tasks import utils

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

    def _get_dns_nameservers(self, vthunder, flavor={}):
        license_net_id = CONF.glm_license.amp_license_network
        if not license_net_id:
            license_net_id = CONF.a10_controller_worker.amp_mgmt_network
            if not license_net_id:
                if len(CONF.a10_controller_worker.amp_boot_network_list) >= 1:
                    license_net_id = CONF.a10_controller_worker.amp_boot_network_list[0]
                else:
                    LOG.warning("No networks were configured therefore "
                                "nameservers cannot be set on the "
                                "vThunder-Amphora %s", vthunder.id)
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

        if CONF.glm_license.primary_dns:
            primary_dns = CONF.glm_license.primary_dns

        if CONF.glm_license.secondary_dns:
            secondary_dns = CONF.glm_license.secondary_dns

        use_network_dns = flavor and flavor.get('glm') and flavor.get('glm').get('use-network-dns')
        if not primary_dns or use_network_dns:
            subnet_dns = license_subnet['subnet'].get('dns_nameservers', [])
            if len(subnet_dns) == 1:
                primary_dns = subnet_dns[0]
            elif len(subnet_dns) >= 2:
                primary_dns = subnet_dns[0]
                secondary_dns = subnet_dns[1]
                if len(subnet_dns) > 2:
                    LOG.warning("More than one DNS nameserver detected on subnet %s. "
                                "Using %s as primary and %s as secondary.",
                                license_subnet_id, primary_dns, secondary_dns)

            if use_network_dns:
                if not primary_dns and not secondary_dns:
                    LOG.warning("The flavor option `use_network_dns` was defined "
                                "but no nameservers were found on the network. "
                                "Nameservers will not be configure on the "
                                "vThunder-Amphora %s", vthunder.id)
                return primary_dns, secondary_dns

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

        flavor = flavor if flavor else {}
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
        flavor = flavor if flavor else {}
        primary_dns, secondary_dns = self._get_dns_nameservers(vthunder, flavor)
        if not primary_dns and not secondary_dns:
            return None

        try:
            self.axapi_client.dns.delete(primary_dns, secondary_dns)
        except req_exceptions.ConnectionError:
            LOG.exception("Failed to connect A10 Thunder device: %s", vthunder.ip_address)


class ActivateFlexpoolLicense(task.Task):

    def _build_configuration(self, flavor={}):
        glm_config = dict(CONF.glm_license)
        glm_config.update(utils.dash_to_underscore(flavor.get('glm', {})))

        config_payload = {
            "port": glm_config.get('port'),
            "burst": glm_config.get('burst'),
            "token": glm_config.get('flexpool_token'),
            "interval": glm_config.get('interval'),
            "enable_requests": glm_config.get('enable_requests'),
            "allocate_bandwidth": glm_config.get('allocate_bandwidth'),
        }
        return config_payload

    @axapi_client_decorator
    def execute(self, vthunder, amphora, flavor=None):
        if not vthunder:
            LOG.warning("No vthunder therefore licensing cannot occur.")
            return None

        flavor = flavor if flavor else {}
        amp_mgmt_net = CONF.a10_controller_worker.amp_mgmt_network
        amp_boot_nets = CONF.a10_controller_worker.amp_boot_network_list
        config_payload = self._build_configuration(flavor)
        burst = config_payload.pop('burst')
        use_mgmt_port = False

        if not config_payload["token"]:
            LOG.warning("No token was set in config therefore the "
                        "vthunder-amphora cannot be licensed.")
            return None

        license_net_id = CONF.glm_license.amp_license_network
        if not license_net_id:
            license_net_id = CONF.a10_controller_worker.amp_mgmt_network
            if not license_net_id:
                if len(CONF.a10_controller_worker.amp_boot_network_list) >= 1:
                    license_net_id = CONF.a10_controller_worker.amp_boot_network_list[0]
                else:
                    LOG.warning("No networks were configured therefore "
                                "vthunder cannot be licensed.")
                    return None

        # ID provided to amp_license_network may be equal other provided mgmt network IDs
        if amp_mgmt_net:
            if license_net_id == amp_mgmt_net:
                use_mgmt_port = True
        elif amp_boot_nets:
            if license_net_id == amp_boot_nets[0]:
                use_mgmt_port = True

        interfaces = self.axapi_client.interface.get_list()
        for i in range(len(interfaces['interface']['ethernet-list'])):
            if interfaces['interface']['ethernet-list'][i]['action'] == "disable":
                ifnum = interfaces['interface']['ethernet-list'][i]['ifnum']
                self.axapi_client.system.action.setInterface(ifnum)

        try:
            self.axapi_client.glm.create(
                use_mgmt_port=use_mgmt_port,
                **config_payload
            )
            self.axapi_client.glm.send.create(license_request=1)
            if burst:
                # Must have the license on the device before enabling burst
                self.axapi_client.glm.update(burst=burst)
        except acos_errors.LicenseOptionNotAllowed as e:
            error_msg = ("A specified configuration option is "
                         "incompatible with license type provided. "
                         "This error can occur when the license request has "
                         "failed due to connection issue. Please check your "
                         "configured GLM network and dns settings.")
            LOG.error(error_msg)
            raise e
        except acos_errors.ACOSException as e:
            LOG.error("Could not activate license for amphora %s", amphora.id)
            raise e

    @axapi_client_decorator_for_revert
    def revert(self, vthunder, amphora, flavor=None, *args, **kwargs):
        try:
            self.axapi_client.delete.glm_license.post()
        except req_exceptions.ConnectionError:
            LOG.exception("Failed to connect A10 Thunder device: %s", vthunder.ip_address)
        except Exception as e:
            LOG.exception("Could not delete license for amphora %s due to: \n%s", amphora.id, e)


class RevokeFlexpoolLicense(task.Task):

    @axapi_client_decorator
    def execute(self, vthunder):
        if not vthunder:
            LOG.warning("No vthunder therefore license revocation cannot occur.")
            return None
        try:
            self.axapi_client.delete.glm_license.post()
        except Exception as e:
            LOG.exception("Could not delete license for vthunder %s due to: \n%s", vthunder.id, e)


class ConfigureForwardProxyServer(task.Task):

    def _build_configuration(self, flavor):
        glm_config = dict(CONF.glm_license)
        glm_config.update(utils.dash_to_underscore(flavor.get('glm-proxy-server', {})))

        config_payload = {
            "host": glm_config.get('proxy_host'),
            "port": glm_config.get('proxy_port'),
            "username": glm_config.get('proxy_username'),
            "password": glm_config.get('proxy_password'),
            "secret_string": glm_config.get('proxy_secret_string'),
        }
        return config_payload

    @axapi_client_decorator
    def execute(self, vthunder, flavor={}):
        if not vthunder:
            LOG.warning("No vthunder therefore forward proxy server cannot be configured.")
            return
        flavor = {} if flavor is None else flavor
        config_payload = self._build_configuration(flavor)
        if config_payload['host'] and config_payload['port']:
            try:
                self.axapi_client.glm.proxy_server.create(**config_payload)
            except acos_errors.ACOSException as e:
                LOG.error("Could not configure forward proxy server for A10 "
                          "Thunder device", vthunder.ip_address)
                raise e

    @axapi_client_decorator_for_revert
    def revert(self, vthunder, flavor={}, *args, **kwargs):
        try:
            self.axapi_client.glm.proxy_server.delete()
        except req_exceptions.ConnectionError:
            LOG.exception("Failed to connect A10 Thunder device: %s", vthunder.ip_address)
        except Exception as e:
            LOG.exception(
                "Could not delete forward proxy for vthunder %s due to: \n%s",
                vthunder.id, e)
