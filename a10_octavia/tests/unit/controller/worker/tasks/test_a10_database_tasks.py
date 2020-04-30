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

from octavia.common import data_models as o_data_models

from a10_octavia.common.config_options import A10_GLOBAL_OPTS
from a10_octavia.common import data_models
from a10_octavia.controller.worker.tasks import a10_database_tasks as task
from a10_octavia.tests.common import a10constants
from a10_octavia.tests.unit import base

VTHUNDER = data_models.VThunder()
LB = o_data_models.LoadBalancer(id=a10constants.MOCK_LOAD_BALANCER_ID)


class TestA10DatabaseTasks(base.BaseTaskTestCase):
    def setUp(self):
        super(TestA10DatabaseTasks, self).setUp()
        imp.reload(task)
        self.conf = self.useFixture(oslo_fixture.Config(cfg.CONF))
        self.conf.register_opts(A10_GLOBAL_OPTS,
                                group=a10constants.A10_GLOBAL_OPTS)

    @mock.patch('a10_octavia.common.utils.get_parent_project',
                return_value=a10constants.MOCK_PARENT_PROJECT_ID)
    @mock.patch('a10_octavia.db.repositories.VThunderRepository.get_vthunder_from_lb')
    def test_get_vthunder_by_loadbalancer_parent_partition_exists(self,
                                                                  mock_db_get,
                                                                  mock_parent_project_id):
        self.conf.config(group=a10constants.A10_GLOBAL_OPTS, use_parent_partition=True)

        mock_vthunder = copy.deepcopy(VTHUNDER)
        mock_vthunder.partition_name = a10constants.MOCK_CHILD_PART
        mock_vthunder.undercloud = True
        mock_vthunder.hierarchical_multitenancy = True

        mock_get_vthunder = task.GetVThunderByLoadBalancer()
        mock_db_get.return_value = mock_vthunder
        vthunder = mock_get_vthunder.execute(LB)
        self.assertEqual(vthunder.partition_name, a10constants.MOCK_PARENT_PROJECT_ID[:14])

    @mock.patch('a10_octavia.common.utils.get_parent_project',
                return_value=None)
    @mock.patch('a10_octavia.db.repositories.VThunderRepository.get_vthunder_from_lb')
    def test_get_vthunder_by_loadbalancer_parent_partition_not_exists(self,
                                                                      mock_db_get,
                                                                      mock_parent_project_id):
        self.conf.config(group=a10constants.A10_GLOBAL_OPTS, use_parent_partition=True)

        mock_vthunder = copy.deepcopy(VTHUNDER)
        mock_vthunder.partition_name = a10constants.MOCK_CHILD_PART
        mock_vthunder.undercloud = True
        mock_vthunder.hierarchical_multitenancy = True

        mock_get_vthunder = task.GetVThunderByLoadBalancer()
        mock_db_get.return_value = mock_vthunder
        vthunder = mock_get_vthunder.execute(LB)
        self.assertEqual(vthunder.partition_name, a10constants.MOCK_CHILD_PART)

    @mock.patch('a10_octavia.db.repositories.VThunderRepository.get_vthunder_from_lb')
    def test_get_vthunder_by_loadbalancer_parent_partition_no_ohm(self,
                                                                  mock_db_get):
        self.conf.config(group=a10constants.A10_GLOBAL_OPTS, use_parent_partition=True)

        mock_vthunder = copy.deepcopy(VTHUNDER)
        mock_vthunder.partition_name = a10constants.MOCK_CHILD_PART
        mock_vthunder.undercloud = True
        mock_vthunder.hierarchical_multitenancy = False

        mock_get_vthunder = task.GetVThunderByLoadBalancer()
        mock_db_get.return_value = mock_vthunder
        vthunder = mock_get_vthunder.execute(LB)
        self.assertEqual(vthunder.partition_name, a10constants.MOCK_CHILD_PART)

    @mock.patch('a10_octavia.db.repositories.VThunderRepository.get_vthunder_from_lb')
    def test_get_vthunder_by_loadbalancer_parent_partition_ohm_no_use_parent_partition(self,
                                                                                       mock_db_get):
        self.conf.config(group=a10constants.A10_GLOBAL_OPTS, use_parent_partition=False)

        mock_vthunder = copy.deepcopy(VTHUNDER)
        mock_vthunder.partition_name = a10constants.MOCK_CHILD_PROJECT_ID[:14]
        mock_vthunder.undercloud = True
        mock_vthunder.hierarchical_multitenancy = True

        mock_get_vthunder = task.GetVThunderByLoadBalancer()
        mock_db_get.return_value = mock_vthunder
        vthunder = mock_get_vthunder.execute(LB)
        self.assertEqual(vthunder.partition_name, a10constants.MOCK_CHILD_PROJECT_ID[:14])
