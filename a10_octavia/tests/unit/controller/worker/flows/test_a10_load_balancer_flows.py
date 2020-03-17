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

import mock
from testtools import TestCase

from oslo_config import cfg
from oslo_config import fixture as oslo_fixture
from taskflow.patterns import linear_flow as flow

from octavia.common import constants

from a10_octavia.controller.worker.flows.a10_load_balancer_flows import LoadBalancerFlows


@mock.patch("octavia.controller.worker.tasks.database_tasks.UpdateAmphoraVIPData")
class TestLoadBalancerFlows(TestCase):
    def setUp(self):
        super(TestLoadBalancerFlows, self).setUp()
        self.conf = self.useFixture(oslo_fixture.Config(cfg.CONF))

        self.conf.config(
            group="controller_worker")
        #    amphora_driver='a10')
        self.conf.config(group="nova", enable_anti_affinity=False)
        self.flows = LoadBalancerFlows()

    def test_create_lb_flows(self, mock_net_driver):
        target = self.flows.get_create_load_balancer_flow(constants.TOPOLOGY_SINGLE)
        self.assertIsInstance(target, flow.Flow)
        self.assertIn("vthunder", target.provides)
