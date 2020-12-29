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

from octavia.common import data_models as o_data_models

from a10_octavia.common.data_models import VThunder
import a10_octavia.controller.worker.tasks.nat_pool_tasks as task
from a10_octavia.tests.common import a10constants
from a10_octavia.tests.unit import base

VTHUNDER = VThunder()
LB = o_data_models.LoadBalancer(id=a10constants.MOCK_LOAD_BALANCER_ID)


class TestHandlerNatPoolTasks(base.BaseTaskTestCase):

    def setUp(self):
        super(TestHandlerNatPoolTasks, self).setUp()
        imp.reload(task)
        self.client_mock = mock.Mock()

    def tearDown(self):
        super(TestHandlerNatPoolTasks, self).tearDown()

    def test_create_nat_pool_with_nat_pool_not_exists_with_nat_pool_flavor(self):
        flavor = {u'nat_pool': {u'start_address': u'172.16.1.101', u'end_address': u'172.16.1.108',
                                u'netmask': u'/24', u'gateway': u'172.16.1.1',
                                u'pool_name': u'pool1'}}

        vthunder = copy.deepcopy(VTHUNDER)
        mock_nat_pool_task = task.NatPoolCreate()
        mock_nat_pool_task.axapi_client = self.client_mock
        self.client_mock.nat.pool.exists.return_value = False
        mock_nat_pool_task.execute(LB, vthunder, flavor_data=flavor)
        args, kwargs = self.client_mock.nat.pool.create.call_args
        self.assertIn('172.16.1.101', args)
        self.assertEqual(kwargs['gateway'], '172.16.1.1')

    def test_create_nat_pool_with_nat_pool_exists_with_nat_pool_flavor(self):
        flavor = {u'nat_pool': {u'start_address': u'172.16.1.101', u'end_address': u'172.16.1.108',
                                u'netmask': u'/24', u'gateway': u'172.16.1.1',
                                u'pool_name': u'pool1'}}

        device_pool = {u'pool': {u'uuid': u'947c228e-443a-11eb-9273-525400bf462d',
                                 u'start-address': u'172.16.1.101', u'port-overload': 0,
                                 u'a10-url': u'/axapi/v3/ip/nat/pool/pool1', u'netmask': u'/24',
                                 u'end-address': u'172.16.1.108', u'ip-rr': 0,
                                 u'gateway': u'172.16.1.1', u'pool-name': u'pool1'}}

        vthunder = copy.deepcopy(VTHUNDER)
        mock_nat_pool_task = task.NatPoolCreate()
        mock_nat_pool_task.axapi_client = self.client_mock
        self.client_mock.nat.pool.exists.return_value = True
        self.client_mock.nat.pool.get.return_value = device_pool
        mock_nat_pool_task.execute(LB, vthunder, flavor_data=flavor)
        self.client_mock.nat.pool.create.not_called()

    def test_create_nat_pool_with_nat_pool_not_exists_with_nat_pool_list_flavor(self):
        flavor = {u'nat_pool_list': [{u'start_address': u'172.16.2.101',
                                      u'end_address': u'172.16.2.102', u'netmask': u'/24',
                                      u'gateway': u'172.16.2.1', u'pool_name': u'pooln1'},
                                     {u'start_address': u'172.16.3.101',
                                      u'end_address': u'172.16.3.102', u'netmask': u'/24',
                                      u'gateway': u'172.16.3.1', u'pool_name': u'pooln2'}]}

        vthunder = copy.deepcopy(VTHUNDER)
        mock_nat_pool_task = task.NatPoolCreate()
        mock_nat_pool_task.axapi_client = self.client_mock
        self.client_mock.nat.pool.exists.return_value = False
        mock_nat_pool_task.execute(LB, vthunder, flavor_data=flavor)
        args, kwargs = self.client_mock.nat.pool.create.call_args
        self.assertIn('pooln2', args)
        self.assertEqual(kwargs['gateway'], '172.16.3.1')

    def test_create_nat_pool_with_nat_pool_exists_with_nat_pool_list_flavor(self):
        flavor = {u'nat_pool_list': [{u'start_address': u'172.16.2.101',
                                      u'end_address': u'172.16.2.102', u'netmask': u'/24',
                                      u'gateway': u'172.16.2.1', u'pool_name': u'pooln1'},
                                     {u'start_address': u'172.16.3.101',
                                      u'end_address': u'172.16.3.102', u'netmask': u'/24',
                                      u'gateway': u'172.16.3.1', u'pool_name': u'pooln2'}]}

        device_pool = {u'pool': {u'uuid': u'eef8b1ea-48dc-11eb-b050-5254000780f9',
                                 u'start-address': u'172.16.2.101', u'port-overload': 0,
                                 u'a10-url': u'/axapi/v3/ip/nat/pool/pooln1', u'netmask': u'/24',
                                 u'end-address': u'172.16.2.102', u'ip-rr': 0,
                                 u'gateway': u'172.16.2.1', u'pool-name': u'pooln1'}}

        vthunder = copy.deepcopy(VTHUNDER)
        mock_nat_pool_task = task.NatPoolCreate()
        mock_nat_pool_task.axapi_client = self.client_mock
        self.client_mock.nat.pool.exists.return_value = True
        self.client_mock.nat.pool.get.return_value = device_pool
        mock_nat_pool_task.execute(LB, vthunder, flavor_data=flavor)
        self.client_mock.nat.pool.create.not_called()
