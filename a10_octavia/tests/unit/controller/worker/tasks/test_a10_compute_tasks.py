#    Copyright 2020, A10 Networks
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

from octavia.common import constants as o_constants
from octavia.common import data_models as o_data_models
from octavia.tests.common import constants as o_test_constants

from a10_octavia.common import config_options
from a10_octavia.common import data_models
from a10_octavia.common import exceptions
from a10_octavia.controller.worker.tasks import a10_compute_tasks as task
from a10_octavia.tests.common import a10constants
from a10_octavia.tests.unit import base

AMPHORA = o_data_models.Amphora(id=a10constants.MOCK_AMPHORA_ID)
VTHUNDER = data_models.VThunder(compute_id=a10constants.MOCK_COMPUTE_ID)
VIP = o_data_models.Vip(ip_address="1.1.1.1", network_id=o_test_constants.MOCK_VIP_NET_ID)
LB = o_data_models.LoadBalancer(
    id=a10constants.MOCK_LOAD_BALANCER_ID, vip=VIP)


class TestA10ComputeTasks(base.BaseTaskTestCase):

    def setUp(self):
        super(TestA10ComputeTasks, self).setUp()
        self.conf = self.useFixture(oslo_fixture.Config(cfg.CONF))
        self.conf.register_opts(config_options.A10_GLM_LICENSE_OPTS,
                                group=a10constants.A10_GLOBAL_CONF_SECTION)
        imp.reload(task)
        self.client_mock = mock.Mock()
        self.db_session = mock.patch(
            'a10_octavia.controller.worker.tasks.a10_database_tasks.db_apis.get_session')
        self.db_session.start()

    def tearDown(self):
        super(TestA10ComputeTasks, self).tearDown()
        self.conf.reset()

    @mock.patch('stevedore.driver.DriverManager.driver')
    def test_ComputeCreate_execute_no_nets(self, mock_driver):
        compute_task = task.ComputeCreate()
        compute_task.compute = mock.MagicMock()
        task_function = compute_task.execute
        expected_error = exceptions.NetworkNotFoundToBootAmphora
        self.assertRaises(expected_error, task_function, AMPHORA.id)

    @mock.patch('stevedore.driver.DriverManager.driver')
    def test_ComputeCreate_execute_mgmt_only(self, mock_driver):
        self.conf.config(group=a10constants.A10_CONTROLLER_WORKER_CONF_SECTION,
                         amp_mgmt_network=a10constants.MOCK_NETWORK_ID)
        compute_task = task.ComputeCreate()
        compute_task.compute = mock.MagicMock()
        compute_task.execute(AMPHORA.id)
        args, kwargs = compute_task.compute.build.call_args
        self.assertEqual(kwargs.get('network_ids'), [a10constants.MOCK_NETWORK_ID])

    @mock.patch('stevedore.driver.DriverManager.driver')
    def test_ComputeCreate_execute_boot_only(self, mock_driver):
        boot_list = [a10constants.MOCK_NETWORK_ID, 'mock-network-id-2']
        self.conf.config(group=a10constants.A10_CONTROLLER_WORKER_CONF_SECTION,
                         amp_boot_network_list=boot_list)
        compute_task = task.ComputeCreate()
        compute_task.compute = mock.MagicMock()
        compute_task.execute(AMPHORA.id)
        args, kwargs = compute_task.compute.build.call_args

        actual_net_ids = kwargs.get('network_ids')
        self.assertEqual(set(boot_list), set(actual_net_ids))
        self.assertEqual(len(boot_list), len(actual_net_ids))

    @mock.patch('stevedore.driver.DriverManager.driver')
    def test_ComputeCreate_execute_glm_only(self, mock_driver):
        self.conf.config(group=a10constants.GLM_LICENSE_CONFIG_SECTION,
                         amp_license_network=a10constants.MOCK_NETWORK_ID)
        self.conf.config(group=a10constants.A10_CONTROLLER_WORKER_CONF_SECTION,
                         amp_boot_network_list=['mock-network-id-2'])
        compute_task = task.ComputeCreate()
        compute_task.compute.build = mock.MagicMock()
        compute_task.execute(AMPHORA.id)
        args, kwargs = compute_task.compute.build.call_args
        self.assertIn('mock-network-1', kwargs.get('network_ids'))

    @mock.patch('stevedore.driver.DriverManager.driver')
    def test_ComputeCreate_execute_lb_only(self, mock_driver):
        self.conf.config(group=a10constants.A10_CONTROLLER_WORKER_CONF_SECTION,
                         amp_boot_network_list=[a10constants.MOCK_NETWORK_ID])
        compute_task = task.ComputeCreate()
        compute_task.compute.build = mock.MagicMock()
        compute_task.execute(AMPHORA.id, loadbalancer=LB)
        args, kwargs = compute_task.compute.build.call_args
        self.assertIn('vip-net-1', kwargs['network_ids'])

    @mock.patch('stevedore.driver.DriverManager.driver')
    def test_ComputeCreate_execute_mgmt_is_glm(self, mock_driver):
        self.conf.config(group=a10constants.A10_CONTROLLER_WORKER_CONF_SECTION,
                         amp_mgmt_network=a10constants.MOCK_NETWORK_ID)
        self.conf.config(group=a10constants.GLM_LICENSE_CONFIG_SECTION,
                         amp_license_network=a10constants.MOCK_NETWORK_ID)
        compute_task = task.ComputeCreate()
        compute_task.compute.build = mock.MagicMock()
        compute_task.execute(AMPHORA.id)
        args, kwargs = compute_task.compute.build.call_args
        self.assertEqual(kwargs.get('network_ids'), [a10constants.MOCK_NETWORK_ID])

    @mock.patch('stevedore.driver.DriverManager.driver')
    def test_ComputeCreate_execute_mgmt_is_first_boot(self, mock_driver):
        mgmt_id = a10constants.MOCK_NETWORK_ID
        boot_list = [mgmt_id, 'mock-network-id-2']
        self.conf.config(group=a10constants.A10_CONTROLLER_WORKER_CONF_SECTION,
                         amp_mgmt_network=mgmt_id,
                         amp_boot_network_list=boot_list)
        compute_task = task.ComputeCreate()
        compute_task.compute = mock.MagicMock()
        compute_task.execute(AMPHORA.id)
        args, kwargs = compute_task.compute.build.call_args

        actual_net_ids = kwargs.get('network_ids')
        self.assertEqual(actual_net_ids, boot_list)

    @mock.patch('stevedore.driver.DriverManager.driver')
    def test_ComputeCreate_execute_mgmt_is_lb(self, mock_driver):
        loadbalancer = copy.deepcopy(LB)
        loadbalancer.vip.network_id = a10constants.MOCK_NETWORK_ID
        self.conf.config(group=a10constants.A10_CONTROLLER_WORKER_CONF_SECTION,
                         amp_mgmt_network=a10constants.MOCK_NETWORK_ID)
        compute_task = task.ComputeCreate()
        compute_task.compute.build = mock.MagicMock()
        compute_task.execute(AMPHORA.id, loadbalancer=loadbalancer)
        args, kwargs = compute_task.compute.build.call_args
        self.assertEqual(kwargs.get('network_ids'), [a10constants.MOCK_NETWORK_ID])

    @mock.patch('stevedore.driver.DriverManager.driver')
    def test_ComputeCreate_execute_glm_in_boot(self, mock_driver):
        boot_list = ['mock-mgmt-net-id', a10constants.MOCK_NETWORK_ID]

        self.conf.config(group=a10constants.A10_CONTROLLER_WORKER_CONF_SECTION,
                         amp_boot_network_list=boot_list)
        self.conf.config(group=a10constants.GLM_LICENSE_CONFIG_SECTION,
                         amp_license_network=a10constants.MOCK_NETWORK_ID)

        compute_task = task.ComputeCreate()
        compute_task.compute = mock.MagicMock()
        compute_task.execute(AMPHORA.id)
        args, kwargs = compute_task.compute.build.call_args

        actual_net_ids = kwargs.get('network_ids')
        self.assertIn(a10constants.MOCK_NETWORK_ID, actual_net_ids)
        self.assertEqual(len(actual_net_ids), len(boot_list))

    @mock.patch('stevedore.driver.DriverManager.driver')
    def test_ComputeCreate_execute_net_list_no_diff(self, mock_driver):
        mgmt_id = 'mock-mgmt-net-id'
        license_id = 'mock-mock-license-net-id'
        boot_list = ['mock-data-net-id-1']
        net_list = [mgmt_id, boot_list[0], LB.vip.network_id, license_id]

        self.conf.config(group=a10constants.A10_CONTROLLER_WORKER_CONF_SECTION,
                         amp_mgmt_network=mgmt_id,
                         amp_boot_network_list=boot_list)
        self.conf.config(group=a10constants.GLM_LICENSE_CONFIG_SECTION,
                         amp_license_network=license_id)

        compute_task = task.ComputeCreate()
        compute_task.compute = mock.MagicMock()
        compute_task.execute(AMPHORA.id, loadbalancer=LB, network_list=net_list)
        args, kwargs = compute_task.compute.build.call_args

        actual_net_ids = kwargs.get('network_ids')
        self.assertEqual(actual_net_ids[0], mgmt_id)
        self.assertEqual(set(actual_net_ids), set(net_list))
        self.assertEqual(len(actual_net_ids), len(net_list))

    @mock.patch('stevedore.driver.DriverManager.driver')
    def test_ComputeCreate_execute_net_list_with_diff(self, mock_driver):
        mgmt_id = 'mock-mgmt-net-id'
        license_id = 'mock-mock-license-net-id'
        boot_list = ['mock-data-net-id-1', 'mock-data-net-id-2']
        net_list = [mgmt_id, boot_list[0], license_id]

        self.conf.config(group=a10constants.A10_CONTROLLER_WORKER_CONF_SECTION,
                         amp_mgmt_network=mgmt_id,
                         amp_boot_network_list=boot_list)
        self.conf.config(group=a10constants.GLM_LICENSE_CONFIG_SECTION,
                         amp_license_network=license_id)

        compute_task = task.ComputeCreate()
        compute_task.compute = mock.MagicMock()
        compute_task.execute(AMPHORA.id, loadbalancer=LB, network_list=net_list)
        args, kwargs = compute_task.compute.build.call_args

        actual_net_ids = kwargs.get('network_ids')
        expected_net_ids = {mgmt_id, license_id, LB.vip.network_id}.union(boot_list)

        self.assertEqual(actual_net_ids[0], mgmt_id)
        self.assertNotEqual(set(actual_net_ids), set(net_list))
        self.assertNotEqual(len(actual_net_ids), len(net_list))
        self.assertEqual(set(actual_net_ids), expected_net_ids)
        self.assertEqual(len(actual_net_ids), len(expected_net_ids))

    @mock.patch('stevedore.driver.DriverManager.driver')
    def test_CheckAmphoraStatus_execute_status_active(self, mock_driver):
        vthunder = copy.deepcopy(VTHUNDER)
        _amphora_mock = mock.MagicMock()
        _amphora_mock.status = o_constants.ACTIVE
        mock_driver.get_amphora.return_value = _amphora_mock, None
        computestatus = task.CheckAmphoraStatus()
        status = computestatus.execute(vthunder)
        self.assertEqual(status, True)

    @mock.patch('stevedore.driver.DriverManager.driver')
    def test_CheckAmphoraStatus_status_execute_shutoff(self, mock_driver):
        vthunder = copy.deepcopy(VTHUNDER)
        _amphora_mock = mock.MagicMock()
        _amphora_mock.status = "SHUTOFF"
        mock_driver.get_amphora.return_value = _amphora_mock, None
        computestatus = task.CheckAmphoraStatus()
        status = computestatus.execute(vthunder)
        self.assertEqual(status, False)
