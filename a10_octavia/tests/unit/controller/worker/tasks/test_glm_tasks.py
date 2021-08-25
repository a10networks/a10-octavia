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
import json
try:
    from unittest import mock
except ImportError:
    import mock

from oslo_config import cfg
from oslo_config import fixture as oslo_fixture

from octavia.common import data_models as o_data_models
from octavia.network import data_models as n_data_models
from octavia.network.drivers.neutron import utils

from acos_client import errors as acos_errors

from a10_octavia.common import config_options
from a10_octavia.common import data_models as a10_data_models
from a10_octavia.common import exceptions
from a10_octavia.common import utils as a10_utils
from a10_octavia.controller.worker.tasks import glm_tasks as task
from a10_octavia.network.drivers.neutron import a10_octavia_neutron
from a10_octavia.tests.common import a10constants
from a10_octavia.tests.unit import base


VTHUNDER = a10_data_models.VThunder()
DNS_SUBNET = n_data_models.Subnet(id=a10constants.MOCK_SUBNET_ID)
DNS_NETWORK = n_data_models.Network(subnets=[DNS_SUBNET])

class TestGLMTasks(base.BaseTaskTestCase):

    def setUp(self):
        super(TestGLMTasks, self).setUp()
        self.conf = self.useFixture(oslo_fixture.Config(cfg.CONF))
        self.conf.register_opts(config_options.A10_GLM_LICENSE,
                                group=a10constants.A10_GLOBAL_CONF_SECTION)
        imp.reload(task)
        self.client_mock = mock.Mock()
        self.db_session = mock.patch(
            'a10_octavia.controller.worker.tasks.a10_database_tasks.db_apis.get_session')
        self.db_session.start()

    def test_DNSConfiguration_execute_no_vthunder_warn(self):
        dns_task = task.DNSConfiguration()
        dns_task.axapi_client = self.client_mock
        task_path = "a10_octavia.controller.worker.tasks.glm_tasks"
        log_message = str("No vthunder therefore dns cannot be assigned.")
        expected_log = ["WARNING:{}:{}".format(task_path, log_message)]
        with self.assertLogs(task_path, level='WARN') as cm:
            dns_task.execute()
            self.assertEqual(expected_log, cm.output)

    def test_DNSConfiguration_execute_no_network_id_warn(self):
        vthunder = copy.deepcopy(VTHUNDER)
        dns_task = task.DNSConfiguration()
        dns_task.axapi_client = self.client_mock
        task_path = "a10_octavia.controller.worker.tasks.glm_tasks"
        log_message = str("No networks were configured therefore "
                          "nameservers cannot be set.")
        expected_log = ["WARNING:{}:{}".format(task_path, log_message)]
        with self.assertLogs(task_path, level='WARN') as cm:
            dns_task.execute(vthunder)
            self.assertEqual(expected_log, cm.output)

    @mock.patch('a10_octavia.controller.worker.tasks.glm_task.DNSConfiguration.network_driver')
    def test_DNSConfiguration_execute_use_network_dns(self, network_driver_mock):
        vthunder = copy.deepcopy(VTHUNDER)
        dns_net = copy.deepcopy(DNS_NETWORK)
        dns_subnet = dns_net.subnets[0].to_dict()
        dns_subnet['dns_nameservers'] = ['1.1.1.1', '2.2.2.2']
        network_driver_mock.get_network.return_value = dns_net
        network_driver_mock.show_subnet_detailed = dns_net.subnets[0].to_dict()

        dns_task = task.DNSConfiguration()
        dns_task.axapi_client = self.client_mock
        dns_task.execute(vthunder)
        args, kwargs = self.client_mock.dns.set.call_args
        self.assertEqual(args, ['1.1.1.1', '2.2.2.2'])

    def test_DNSConfiguration_execute_too_many_network_dns_warn(self):
        pass

    def test_DNSConfiguration_execute_use_license_net(self):
        pass

    def test_DNSConfiguration_execute_use_amp_mgmt_net(self):
        pass

    def test_DNSConfiguration_execute_use_first_amp_boot_net(self):
        pass

    def test_DNSConfiguration_execute_flavor_dns(self):
        pass

    # def test_DNSConfiguration_execute_no_dns(self):
    #     vthunder = copy.deepcopy(VTHUNDER)
    #     dns_task = task.DNSConfiguration()
    #     dns_task.axapi_client = self.client_mock
    #     dns_task.execute(vthunder)
        
    # def test_DNSConfiguration_execute_with_primary(self):
    #     self.conf.config(group=a10constants.GLM_LICENSE_CONFIG_SECTION,
    #                      primary_dns='1.1.1.1')
    #     dns_task = task.DNSConfiguration()
    #     dns_task.axapi_client = self.client_mock
    #     dns_task.CONF = self.conf

    # def test_DNSConfiguration_execute_with_primary_secondary(self):
    #     self.conf.config(group=a10constants.GLM_LICENSE_CONFIG_SECTION,
    #                      primary_dns='1.1.1.1', secondary_dns='2.2.2.2')
    #     dns_task = task.DNSConfiguration()
    #     dns_task.axapi_client = self.client_mock
    #     dns_task.CONF = self.conf

    # def test_DNSConfiguration_execute_with_secondary_revert(self):
    #     self.conf.config(group=a10constants.GLM_LICENSE_CONFIG_SECTION,
    #                      secondary_dns='2.2.2.2')


    def test_ActivateFlexpoolLicense_execute_success(self):
        pass

    def test_ActivateFlexpoolLicense_execute_no_vthunder_warn(self):
        pass

    def test_ActivateFlexpoolLicense_execute_use_mgmt_port(self):
        pass

    def test_ActivateFlexpoolLicense_execute_iface_up(self):
        pass

    def test_ActivateFlexpoolLicense_execute_set_hostname(self):
        pass

    def test_ActivateFlexpoolLicense_revert_deactivate_license(self):
        pass

    def test_RevokeFlexpoolLicense_execute_success(self):
        pass

    def test_RevokeFlexpoolLicense_execute_no_vthunder_warn(self):
        pass