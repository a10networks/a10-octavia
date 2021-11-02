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

import copy
import imp

try:
    from unittest import mock
except ImportError:
    import mock

from oslo_config import cfg
from oslo_config import fixture as oslo_fixture

from octavia.common import data_models as o_data_models
from octavia.network import data_models as n_data_models
from octavia.tests.common import constants as t_constants

from acos_client import errors as acos_errors

from a10_octavia.common import config_options
from a10_octavia.common import data_models as a10_data_models
from a10_octavia.common import exceptions as a10_ex
from a10_octavia.controller.worker.tasks import glm_tasks as task
from a10_octavia.tests.common import a10constants
from a10_octavia.tests.unit import base


VTHUNDER = a10_data_models.VThunder(id=a10constants.MOCK_VTHUNDER_ID)
AMPHORA = o_data_models.Amphora(id=t_constants.MOCK_AMP_ID1)
DNS_SUBNET = n_data_models.Subnet(id=a10constants.MOCK_SUBNET_ID)
DNS_NETWORK = n_data_models.Network(id=a10constants.MOCK_NETWORK_ID,
                                    subnets=[DNS_SUBNET.id])
PRIMARY_DNS = '1.3.3.7'
SECONDARY_DNS = '1.0.0.7'
PROXY_HOST = '10.10.10.10'
PROXY_PORT = 1111
PROXY_USERNAME = 'user'
PROXY_PASSWORD = True
PROXY_PASSWORD_VALUE = 'password'


class TestGLMTasks(base.BaseTaskTestCase):

    def setUp(self):
        super(TestGLMTasks, self).setUp()
        self.conf = self.useFixture(oslo_fixture.Config(cfg.CONF))
        self.conf.register_opts(config_options.A10_GLM_LICENSE_OPTS,
                                group=a10constants.A10_GLOBAL_CONF_SECTION)
        imp.reload(task)
        self.client_mock = mock.Mock()
        self.db_session = mock.patch(
            'a10_octavia.controller.worker.tasks.a10_database_tasks.db_apis.get_session')
        self.db_session.start()

    def tearDown(self):
        super(TestGLMTasks, self).tearDown()
        self.conf.reset()

    def test_DNSConfiguration_execute_no_vthunder_warn(self):
        dns_task = task.DNSConfiguration()
        dns_task.axapi_client = self.client_mock
        task_path = "a10_octavia.controller.worker.tasks.glm_tasks"
        log_message = str("No vthunder therefore dns cannot be assigned.")
        expected_log = ["WARNING:{}:{}".format(task_path, log_message)]
        with self.assertLogs(task_path, level='WARN') as cm:
            dns_task.execute(None)
            self.assertEqual(expected_log, cm.output)

    def test_DNSConfiguration_execute_no_network_id_warn(self):
        vthunder = copy.deepcopy(VTHUNDER)
        dns_task = task.DNSConfiguration()
        dns_task.axapi_client = self.client_mock
        task_path = "a10_octavia.controller.worker.tasks.glm_tasks"
        log_message = str("No networks were configured therefore "
                          "nameservers cannot be set on the "
                          "vThunder-Amphora {}").format(a10constants.MOCK_VTHUNDER_ID)
        expected_log = ["WARNING:{}:{}".format(task_path, log_message)]
        with self.assertLogs(task_path, level='WARN') as cm:
            dns_task.execute(vthunder)
            self.assertEqual(expected_log, cm.output)

    @mock.patch('a10_octavia.controller.worker.tasks.glm_tasks.DNSConfiguration.network_driver')
    def test_DNSConfiguration_execute_no_dns(self, network_driver_mock):
        self.conf.config(group=a10constants.GLM_LICENSE_CONFIG_SECTION,
                         amp_license_network=DNS_NETWORK.id)
        vthunder = copy.deepcopy(VTHUNDER)
        dns_net = copy.deepcopy(DNS_NETWORK)
        network_driver_mock.get_network.return_value = dns_net
        dns_subnet = copy.deepcopy(DNS_SUBNET).to_dict()
        network_driver_mock.show_subnet_detailed.return_value = {'subnet': dns_subnet}

        dns_task = task.DNSConfiguration()
        dns_task.axapi_client = self.client_mock
        dns_task.execute(vthunder)
        self.client_mock.dns.set.assert_not_called()

    @mock.patch('a10_octavia.controller.worker.tasks.glm_tasks.DNSConfiguration.network_driver')
    def test_DNSConfiguration_execute_use_license_net_primary_only(self, network_driver_mock):
        self.conf.config(group=a10constants.GLM_LICENSE_CONFIG_SECTION,
                         amp_license_network=DNS_NETWORK.id, primary_dns=PRIMARY_DNS)
        vthunder = copy.deepcopy(VTHUNDER)
        dns_net = copy.deepcopy(DNS_NETWORK)
        network_driver_mock.get_network.return_value = dns_net
        dns_subnet = copy.deepcopy(DNS_SUBNET).to_dict()
        network_driver_mock.show_subnet_detailed.return_value = {'subnet': dns_subnet}

        dns_task = task.DNSConfiguration()
        dns_task.axapi_client = self.client_mock
        dns_task.execute(vthunder)
        args, kwargs = self.client_mock.dns.set.call_args
        self.assertEqual(args, (PRIMARY_DNS, None))

    @mock.patch('a10_octavia.controller.worker.tasks.glm_tasks.DNSConfiguration.network_driver')
    def test_DNSConfiguration_execute_with_primary_secondary(self, network_driver_mock):
        self.conf.config(group=a10constants.GLM_LICENSE_CONFIG_SECTION,
                         amp_license_network=DNS_NETWORK.id,
                         primary_dns=PRIMARY_DNS, secondary_dns=SECONDARY_DNS)
        vthunder = copy.deepcopy(VTHUNDER)
        dns_net = copy.deepcopy(DNS_NETWORK)
        network_driver_mock.get_network.return_value = dns_net
        dns_subnet = copy.deepcopy(DNS_SUBNET).to_dict()
        network_driver_mock.show_subnet_detailed.return_value = {'subnet': dns_subnet}

        dns_task = task.DNSConfiguration()
        dns_task.axapi_client = self.client_mock
        dns_task.execute(vthunder)
        args, kwargs = self.client_mock.dns.set.call_args
        self.assertEqual(args, (PRIMARY_DNS, SECONDARY_DNS))

    @mock.patch('a10_octavia.controller.worker.tasks.glm_tasks.DNSConfiguration.network_driver')
    def test_DNSConfiguration_execute_use_network_dns(self, network_driver_mock):
        self.conf.config(group=a10constants.GLM_LICENSE_CONFIG_SECTION,
                         amp_license_network=DNS_NETWORK.id)
        vthunder = copy.deepcopy(VTHUNDER)
        dns_net = copy.deepcopy(DNS_NETWORK)
        dns_subnet = copy.deepcopy(DNS_SUBNET).to_dict()
        dns_subnet['dns_nameservers'] = [PRIMARY_DNS, SECONDARY_DNS]
        network_driver_mock.get_network.return_value = dns_net
        network_driver_mock.show_subnet_detailed.return_value = {'subnet': dns_subnet}

        dns_task = task.DNSConfiguration()
        dns_task.axapi_client = self.client_mock
        dns_task.execute(vthunder)
        args, kwargs = self.client_mock.dns.set.call_args
        self.assertEqual(args, (PRIMARY_DNS, SECONDARY_DNS))

    @mock.patch('a10_octavia.controller.worker.tasks.glm_tasks.DNSConfiguration.network_driver')
    def test_DNSConfiguration_execute_too_many_network_dns_warn(self, network_driver_mock):
        self.conf.config(group=a10constants.GLM_LICENSE_CONFIG_SECTION,
                         amp_license_network=DNS_NETWORK.id)
        vthunder = copy.deepcopy(VTHUNDER)
        dns_net = copy.deepcopy(DNS_NETWORK)
        dns_subnet = copy.deepcopy(DNS_SUBNET).to_dict()
        dns_subnet['dns_nameservers'] = [PRIMARY_DNS, SECONDARY_DNS, '3.3.3.3']
        network_driver_mock.get_network.return_value = dns_net
        network_driver_mock.show_subnet_detailed.return_value = {'subnet': dns_subnet}

        dns_task = task.DNSConfiguration()
        dns_task.axapi_client = self.client_mock

        task_path = "a10_octavia.controller.worker.tasks.glm_tasks"
        log_message = ("More than one DNS nameserver detected on subnet {}. "
                       "Using {} as primary and {} as secondary.".format(
                           DNS_SUBNET.id, PRIMARY_DNS, SECONDARY_DNS))
        expected_log = ["WARNING:{}:{}".format(task_path, log_message)]
        with self.assertLogs(task_path, level='WARN') as cm:
            dns_task.execute(vthunder)
            self.assertEqual(expected_log, cm.output)

    @mock.patch('a10_octavia.controller.worker.tasks.glm_tasks.DNSConfiguration.network_driver')
    def test_DNSConfiguration_execute_use_amp_mgmt_net(self, network_driver_mock):
        self.conf.config(group=a10constants.GLM_LICENSE_CONFIG_SECTION,
                         primary_dns=PRIMARY_DNS, secondary_dns=SECONDARY_DNS)
        self.conf.config(group=a10constants.A10_CONTROLLER_WORKER_CONF_SECTION,
                         amp_mgmt_network=DNS_NETWORK.id)
        vthunder = copy.deepcopy(VTHUNDER)
        dns_net = copy.deepcopy(DNS_NETWORK)
        network_driver_mock.get_network.return_value = dns_net
        dns_subnet = copy.deepcopy(DNS_SUBNET).to_dict()
        network_driver_mock.show_subnet_detailed.return_value = {'subnet': dns_subnet}

        dns_task = task.DNSConfiguration()
        dns_task.axapi_client = self.client_mock
        dns_task.execute(vthunder)
        args, kwargs = self.client_mock.dns.set.call_args
        self.assertEqual(args, (PRIMARY_DNS, SECONDARY_DNS))

    @mock.patch('a10_octavia.controller.worker.tasks.glm_tasks.DNSConfiguration.network_driver')
    def test_DNSConfiguration_execute_use_first_amp_boot_net(self, network_driver_mock):
        self.conf.config(group=a10constants.GLM_LICENSE_CONFIG_SECTION,
                         primary_dns=PRIMARY_DNS, secondary_dns=SECONDARY_DNS)
        self.conf.config(group=a10constants.A10_CONTROLLER_WORKER_CONF_SECTION,
                         amp_boot_network_list=[DNS_NETWORK.id, 'random-net'])
        vthunder = copy.deepcopy(VTHUNDER)
        dns_net = copy.deepcopy(DNS_NETWORK)
        network_driver_mock.get_network.return_value = dns_net
        dns_subnet = copy.deepcopy(DNS_SUBNET).to_dict()
        network_driver_mock.show_subnet_detailed.return_value = {'subnet': dns_subnet}

        dns_task = task.DNSConfiguration()
        dns_task.axapi_client = self.client_mock
        dns_task.execute(vthunder)
        args, kwargs = self.client_mock.dns.set.call_args
        self.assertEqual(args, (PRIMARY_DNS, SECONDARY_DNS))

    @mock.patch('a10_octavia.controller.worker.tasks.glm_tasks.DNSConfiguration.network_driver')
    def test_DNSConfiguration_execute_config_precedence(self, network_driver_mock):
        self.conf.config(group=a10constants.GLM_LICENSE_CONFIG_SECTION,
                         amp_license_network=DNS_NETWORK.id,
                         primary_dns=PRIMARY_DNS, secondary_dns=SECONDARY_DNS)
        vthunder = copy.deepcopy(VTHUNDER)
        dns_net = copy.deepcopy(DNS_NETWORK)
        dns_subnet = copy.deepcopy(DNS_SUBNET).to_dict()
        dns_subnet['dns_nameservers'] = ['8.8.8.8', '8.8.4.4']
        network_driver_mock.get_network.return_value = dns_net
        network_driver_mock.show_subnet_detailed.return_value = {'subnet': dns_subnet}

        dns_task = task.DNSConfiguration()
        dns_task.axapi_client = self.client_mock
        dns_task.execute(vthunder)
        args, kwargs = self.client_mock.dns.set.call_args
        self.assertEqual(args, (PRIMARY_DNS, SECONDARY_DNS))

    @mock.patch('a10_octavia.controller.worker.tasks.glm_tasks.DNSConfiguration.network_driver')
    def test_DNSConfiguration_execute_flavor_dns(self, network_driver_mock):
        flavor = {'dns': {'primary-dns': PRIMARY_DNS, 'secondary-dns': SECONDARY_DNS}}
        self.conf.config(group=a10constants.GLM_LICENSE_CONFIG_SECTION,
                         amp_license_network=DNS_NETWORK.id)
        vthunder = copy.deepcopy(VTHUNDER)
        dns_net = copy.deepcopy(DNS_NETWORK)
        network_driver_mock.get_network.return_value = dns_net
        dns_subnet = copy.deepcopy(DNS_SUBNET).to_dict()
        network_driver_mock.show_subnet_detailed.return_value = {'subnet': dns_subnet}

        dns_task = task.DNSConfiguration()
        dns_task.axapi_client = self.client_mock
        dns_task.execute(vthunder, flavor)
        args, kwargs = self.client_mock.dns.set.call_args
        self.assertEqual(args, (PRIMARY_DNS, SECONDARY_DNS))

    @mock.patch('a10_octavia.controller.worker.tasks.glm_tasks.DNSConfiguration.network_driver')
    def test_DNSConfiguration_execute_flavor_dns_precedence(self, network_driver_mock):
        flavor = {'dns': {'primary-dns': PRIMARY_DNS, 'secondary-dns': SECONDARY_DNS}}
        self.conf.config(group=a10constants.GLM_LICENSE_CONFIG_SECTION,
                         amp_license_network=DNS_NETWORK.id,
                         primary_dns='1.0.1.0', secondary_dns='0.1.0.1')
        vthunder = copy.deepcopy(VTHUNDER)
        dns_net = copy.deepcopy(DNS_NETWORK)
        dns_subnet = copy.deepcopy(DNS_SUBNET).to_dict()
        dns_subnet['dns_nameservers'] = ['8.8.8.8', '8.8.4.4']
        network_driver_mock.get_network.return_value = dns_net
        network_driver_mock.show_subnet_detailed.return_value = {'subnet': dns_subnet}

        dns_task = task.DNSConfiguration()
        dns_task.axapi_client = self.client_mock
        dns_task.execute(vthunder, flavor)
        args, kwargs = self.client_mock.dns.set.call_args
        self.assertEqual(args, (PRIMARY_DNS, SECONDARY_DNS))

    @mock.patch('a10_octavia.controller.worker.tasks.glm_tasks.DNSConfiguration.network_driver')
    def test_DNSConfiguration_execute_with_secondary_fail(self, network_driver_mock):
        self.conf.config(group=a10constants.GLM_LICENSE_CONFIG_SECTION,
                         amp_license_network=DNS_NETWORK.id,
                         secondary_dns=SECONDARY_DNS)
        vthunder = copy.deepcopy(VTHUNDER)
        dns_net = copy.deepcopy(DNS_NETWORK)
        network_driver_mock.get_network.return_value = dns_net
        dns_subnet = copy.deepcopy(DNS_SUBNET).to_dict()
        network_driver_mock.show_subnet_detailed.return_value = {'subnet': dns_subnet}

        dns_task = task.DNSConfiguration()
        dns_task.axapi_client = self.client_mock
        self.assertRaises(a10_ex.PrimaryDNSMissing, dns_task.execute, vthunder)

    @mock.patch('a10_octavia.controller.worker.tasks.glm_tasks.DNSConfiguration.network_driver')
    def test_DNSConfiguration_revert_delete_dns(self, network_driver_mock):
        self.conf.config(group=a10constants.GLM_LICENSE_CONFIG_SECTION,
                         amp_license_network=DNS_NETWORK.id,
                         secondary_dns=SECONDARY_DNS)
        vthunder = copy.deepcopy(VTHUNDER)
        dns_net = copy.deepcopy(DNS_NETWORK)
        network_driver_mock.get_network.return_value = dns_net
        dns_subnet = copy.deepcopy(DNS_SUBNET).to_dict()
        network_driver_mock.show_subnet_detailed.return_value = {'subnet': dns_subnet}

        dns_task = task.DNSConfiguration()
        dns_task.axapi_client = self.client_mock
        dns_task.revert(vthunder)
        args, kwargs = self.client_mock.dns.delete.call_args
        self.assertEqual(args, (None, SECONDARY_DNS))

    @mock.patch('a10_octavia.controller.worker.tasks.glm_tasks.DNSConfiguration.network_driver')
    def test_DNSConfiguration_revert_no_dns_return(self, network_driver_mock):
        self.conf.config(group=a10constants.GLM_LICENSE_CONFIG_SECTION,
                         amp_license_network=DNS_NETWORK.id)
        vthunder = copy.deepcopy(VTHUNDER)
        dns_net = copy.deepcopy(DNS_NETWORK)
        network_driver_mock.get_network.return_value = dns_net
        dns_subnet = copy.deepcopy(DNS_SUBNET).to_dict()
        network_driver_mock.show_subnet_detailed.return_value = {'subnet': dns_subnet}

        dns_task = task.DNSConfiguration()
        dns_task.axapi_client = self.client_mock
        dns_task.execute(vthunder)
        self.client_mock.dns.delete.assert_not_called()

    def test_ActivateFlexpoolLicense_execute_no_vthunder_warn(self):
        flexpool_task = task.ActivateFlexpoolLicense()
        flexpool_task.axapi_client = self.client_mock
        task_path = "a10_octavia.controller.worker.tasks.glm_tasks"
        log_message = str("No vthunder therefore licensing cannot occur.")
        expected_log = ["WARNING:{}:{}".format(task_path, log_message)]
        with self.assertLogs(task_path, level='WARN') as cm:
            flexpool_task.execute(None, None)
            self.assertEqual(expected_log, cm.output)

    def _template_glm_call(self):
        expected_call = {
            'token': a10constants.MOCK_FLEXPOOL_TOKEN,
            'enable_requests': True,
            'interval': None,
            'port': 443,
            'allocate_bandwidth': None,
            'use_mgmt_port': False
        }
        return expected_call

    def test_ActivateFlexpoolLicense_execute_success(self):
        self.conf.config(group=a10constants.GLM_LICENSE_CONFIG_SECTION,
                         amp_license_network=DNS_NETWORK.id,
                         flexpool_token=a10constants.MOCK_FLEXPOOL_TOKEN)
        vthunder = copy.deepcopy(VTHUNDER)
        amphora = copy.deepcopy(AMPHORA)
        interfaces = {
            'interface': {
                'ethernet-list': []
            }
        }
        expected_call = self._template_glm_call()

        flexpool_task = task.ActivateFlexpoolLicense()
        flexpool_task.axapi_client = self.client_mock
        flexpool_task.axapi_client.interface.get_list.return_value = interfaces

        flexpool_task.execute(vthunder, amphora)
        args, kwargs = self.client_mock.glm.create.call_args
        self.assertEqual(kwargs, expected_call)

    def test_ActivateFlexpoolLicense_execute_use_mgmt_port(self):
        self.conf.config(group=a10constants.A10_CONTROLLER_WORKER_CONF_SECTION,
                         amp_mgmt_network=DNS_NETWORK.id)
        self.conf.config(group=a10constants.GLM_LICENSE_CONFIG_SECTION,
                         amp_license_network=DNS_NETWORK.id,
                         flexpool_token=a10constants.MOCK_FLEXPOOL_TOKEN)
        vthunder = copy.deepcopy(VTHUNDER)
        amphora = copy.deepcopy(AMPHORA)
        interfaces = {
            'interface': {
                'ethernet-list': []
            }
        }
        expected_call = self._template_glm_call()
        expected_call['use_mgmt_port'] = True

        flexpool_task = task.ActivateFlexpoolLicense()
        flexpool_task.axapi_client = self.client_mock
        flexpool_task.axapi_client.interface.get_list.return_value = interfaces

        flexpool_task.execute(vthunder, amphora)
        args, kwargs = self.client_mock.glm.create.call_args
        self.assertEqual(kwargs, expected_call)

    def test_ActivateFlexpoolLicense_execute_iface_up(self):
        self.conf.config(group=a10constants.GLM_LICENSE_CONFIG_SECTION,
                         amp_license_network=DNS_NETWORK.id,
                         flexpool_token=a10constants.MOCK_FLEXPOOL_TOKEN)
        vthunder = copy.deepcopy(VTHUNDER)
        amphora = copy.deepcopy(AMPHORA)
        interfaces = {
            'interface': {
                'ethernet-list': [{
                    'ifnum': 2,
                    'action': 'disable'
                }]
            }
        }

        flexpool_task = task.ActivateFlexpoolLicense()
        flexpool_task.axapi_client = self.client_mock
        flexpool_task.axapi_client.interface.get_list.return_value = interfaces

        flexpool_task.execute(vthunder, amphora)
        self.client_mock.system.action.setInterface.assert_called_with(2)

    def test_ActivateFlexpoolLicense_execute_enable_burst(self):
        self.conf.config(group=a10constants.GLM_LICENSE_CONFIG_SECTION,
                         amp_license_network=DNS_NETWORK.id,
                         flexpool_token=a10constants.MOCK_FLEXPOOL_TOKEN,
                         burst=True)
        vthunder = copy.deepcopy(VTHUNDER)
        amphora = copy.deepcopy(AMPHORA)
        interfaces = {
            'interface': {
                'ethernet-list': []
            }
        }
        expected_call = self._template_glm_call()

        flexpool_task = task.ActivateFlexpoolLicense()
        flexpool_task.axapi_client = self.client_mock
        flexpool_task.axapi_client.interface.get_list.return_value = interfaces

        flexpool_task.execute(vthunder, amphora)
        args, kwargs = self.client_mock.glm.create.call_args
        self.assertEqual(kwargs, expected_call)
        flexpool_task.axapi_client.glm.update.assert_called_with(burst=True)

    def test_ActiveFlexpoolLicense_execute_fail_LicenseOptionNotAllowed_burst(self):
        self.conf.config(group=a10constants.GLM_LICENSE_CONFIG_SECTION,
                         amp_license_network=DNS_NETWORK.id,
                         flexpool_token=a10constants.MOCK_FLEXPOOL_TOKEN)
        vthunder = copy.deepcopy(VTHUNDER)
        amphora = copy.deepcopy(AMPHORA)
        interfaces = {
            'interface': {
                'ethernet-list': []
            }
        }

        flexpool_task = task.ActivateFlexpoolLicense()
        flexpool_task.axapi_client = self.client_mock
        flexpool_task.axapi_client.interface.get_list.return_value = interfaces
        flexpool_task.axapi_client.glm.create.side_effect = acos_errors.LicenseOptionNotAllowed()

        flexpool_task.axapi_client = self.client_mock
        task_path = "a10_octavia.controller.worker.tasks.glm_tasks"
        log_message = ("A specified configuration option is "
                       "incompatible with license type provided. "
                       "This error can occur when the license request has "
                       "failed due to connection issue. Please check your "
                       "configured GLM network and dns settings.")
        expected_log = ["ERROR:{}:{}".format(task_path, log_message)]
        with self.assertLogs(task_path, level='ERROR') as cm:
            try:
                flexpool_task.execute(vthunder, amphora)
            except Exception:
                pass
            self.assertEqual(expected_log, cm.output)

    def test_ActivateFlexpoolLicense_revert_deactivate_license(self):
        vthunder = copy.deepcopy(VTHUNDER)
        amphora = copy.deepcopy(AMPHORA)
        flexpool_task = task.ActivateFlexpoolLicense()
        flexpool_task.axapi_client = self.client_mock

        flexpool_task.revert(vthunder, amphora)
        self.client_mock.delete.glm_license.post.assert_called()

    def test_RevokeFlexpoolLicense_execute_success(self):
        vthunder = copy.deepcopy(VTHUNDER)
        revoke_task = task.RevokeFlexpoolLicense()
        revoke_task.axapi_client = self.client_mock

        revoke_task.execute(vthunder)
        self.client_mock.delete.glm_license.post.assert_called()

    def test_RevokeFlexpoolLicense_execute_no_vthunder_warn(self):
        revoke_task = task.RevokeFlexpoolLicense()
        revoke_task.axapi_client = self.client_mock

        task_path = "a10_octavia.controller.worker.tasks.glm_tasks"
        log_message = str("No vthunder therefore license revocation cannot occur.")
        expected_log = ["WARNING:{}:{}".format(task_path, log_message)]
        with self.assertLogs(task_path, level='WARN') as cm:
            revoke_task.execute(None)
            self.assertEqual(expected_log, cm.output)

    def test_ConfigureForwardProxyServer_execute_success(self):
        self.conf.config(group=a10constants.GLM_LICENSE_CONFIG_SECTION,
                         proxy_host=PROXY_HOST, proxy_port=PROXY_PORT,
                         proxy_username=PROXY_USERNAME, proxy_password=PROXY_PASSWORD,
                         proxy_secret_string=PROXY_PASSWORD_VALUE)
        vthunder = copy.deepcopy(VTHUNDER)
        proxy_server = task.ConfigureForwardProxyServer()
        proxy_server.axapi_client = self.client_mock
        proxy_server.execute(vthunder)
        self.client_mock.glm.proxy_server.create.assert_called()

    def test_ConfigureForwardProxyServer_execute_flavor_success(self):
        flavor = {
            'glm-proxy-server': {
                'proxy_host': PROXY_HOST,
                'proxy_port': PROXY_PORT,
                'proxy_username': PROXY_USERNAME,
                'proxy_password': PROXY_PASSWORD,
                'proxy_secret_string': PROXY_PASSWORD_VALUE
            }
        }
        self.conf.config(group=a10constants.GLM_LICENSE_CONFIG_SECTION,
                         proxy_host="10.10.10.11", proxy_port=8888,
                         proxy_username='configuser', proxy_password=False,
                         proxy_secret_string='configpwrd')
        vthunder = copy.deepcopy(VTHUNDER)
        proxy_server = task.ConfigureForwardProxyServer()
        proxy_server.axapi_client = self.client_mock
        proxy_server.execute(vthunder, flavor)
        self.client_mock.glm.proxy_server.create.assert_called_with(**{'host': PROXY_HOST,
                                                                       'port': PROXY_PORT,
                                                                       'username': PROXY_USERNAME,
                                                                       'password': PROXY_PASSWORD,
                                                                       'secret_string':
                                                                           PROXY_PASSWORD_VALUE})

    def test_ConfigureForwardProxyServer_execute_no_vthunder_warn(self):
        proxy_server = task.ConfigureForwardProxyServer()
        proxy_server.axapi_client = self.client_mock
        task_path = "a10_octavia.controller.worker.tasks.glm_tasks"
        log_message = str("No vthunder therefore forward proxy server cannot be configured.")
        expected_log = ["WARNING:{}:{}".format(task_path, log_message)]
        with self.assertLogs(task_path, level='WARN') as cm:
            proxy_server.execute(None, None)
            self.assertEqual(expected_log, cm.output)

    def test_ConfigureForwardProxyServer_execute_no_proxy_conf(self):
        self.conf.config(group=a10constants.GLM_LICENSE_CONFIG_SECTION,
                         proxy_host=None, proxy_port=None)
        vthunder = copy.deepcopy(VTHUNDER)
        proxy_server = task.ConfigureForwardProxyServer()
        proxy_server.axapi_client = self.client_mock
        proxy_server.execute(vthunder)
        self.client_mock.glm.proxy_server.create.assert_not_called()
