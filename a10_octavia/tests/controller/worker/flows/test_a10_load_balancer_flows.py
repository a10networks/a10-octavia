import mock
from oslo_config import cfg
from oslo_config import fixture as oslo_fixture
from taskflow.patterns import linear_flow as flow

from a10_octavia.tests.test_base import TestBase
from octavia.common import constants

from a10_octavia.controller.worker.flows.a10_load_balancer_flows import LoadBalancerFlows
#from octavia.controller.worker.flows.load_balancer_flows import LoadBalancerFlows
# @mock.patch('octavia.common.utils.get_network_driver')
@mock.patch("octavia.controller.worker.tasks.database_tasks.UpdateAmphoraVIPData")
class TestLoadBalancerFlows(TestBase):
    def setUp(self):
        super(TestBase, self).setUp()
        self.conf = self.useFixture(oslo_fixture.Config(cfg.CONF))

        self.conf.config(
                    group="controller_worker")
                    #    amphora_driver='a10')
        self.conf.config(group="nova", enable_anti_affinity=False)
        self.flows = LoadBalancerFlows()
    
    def test_create_lb_flows(self, mock_net_driver):
        target = self.flows.get_create_load_balancer_flow(constants.TOPOLOGY_SINGLE)
        self.assertIsInstance(target, flow.Flow)
        import pdb; pdb.set_trace()
