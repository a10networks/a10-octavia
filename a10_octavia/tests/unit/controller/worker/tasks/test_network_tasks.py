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


import mock
from unittest.mock import patch

from octavia.common import data_models as o_data_models
from octavia.tests.common import constants as t_constants
from octavia.tests.unit import base

from a10_octavia.controller.worker.tasks import a10_network_tasks
from a10_octavia.network import data_models
from a10_octavia.network.data_models import Subport
from a10_octavia.tests.common import a10constants as a10_test_constants

SUBPORT1 = Subport(segmentation_id=a10_test_constants.SEGMENTATION_ID1)
SUBPORT2 = Subport(segmentation_id=a10_test_constants.SEGMENTATION_ID2)

VIP = o_data_models.Vip(port_id=t_constants.MOCK_PORT_ID,
                        subnet_id=t_constants.MOCK_SUBNET_ID,
                        qos_policy_id=t_constants.MOCK_QOS_POLICY_ID1)
LB = o_data_models.LoadBalancer(vip=VIP)
PARENT_PORT = data_models.ParentPort(trunk_id=a10_test_constants.TRUNK_ID)
EMPTY_PARENT_PORT = data_models.ParentPort()
DELETE_SUBPORTS = {t_constants.MOCK_AMP_ID1: [SUBPORT1]}
MULTIPLE_DELETE_SUBPORTS = {t_constants.MOCK_AMP_ID1: [SUBPORT1, SUBPORT2]}

PORT_DELTA = data_models.PortDelta(
            amphora_id=t_constants.MOCK_AMP_ID1, compute_id=t_constants.MOCK_AMP_COMPUTE_ID1,
            add_subports=[], delete_subports=[])


class TestNetworkTasks(base.TestCase):

    def setUp(self):
        patcher = patch(
            'a10_octavia.controller.worker.tasks.a10_network_tasks.BaseNetworkTask.network_driver')
        self.network_driver_mock = patcher.start()
        self.network_driver_mock.return_value = mock.Mock()
        super(TestNetworkTasks, self).setUp()

    def test_handle_delete_port_deltas_with_empty_port_deltas(self):
        empty_mock_port_deltas = {t_constants.MOCK_AMP_ID1: PORT_DELTA}
        network_task = a10_network_tasks.HandleDeletePortDeltas()
        self.assertEqual({t_constants.MOCK_AMP_ID1: []}, network_task.execute(
            PARENT_PORT, empty_mock_port_deltas))

    def test_handle_delete_port_deltas_with_port_deltas(self):
        PORT_DELTA.delete_subports = DELETE_SUBPORTS
        mock_port_deltas = {t_constants.MOCK_AMP_ID1: PORT_DELTA}
        network_task = a10_network_tasks.HandleDeletePortDeltas()
        network_task.execute(PARENT_PORT, mock_port_deltas)
        self.network_driver_mock.unplug_trunk_subports.assert_called_with(
            PARENT_PORT.trunk_id, DELETE_SUBPORTS)

    def test_handle_delete_port_deltas_with_multiple_port_deltas(self):
        PORT_DELTA.delete_subports = MULTIPLE_DELETE_SUBPORTS
        mock_port_deltas = {t_constants.MOCK_AMP_ID1: PORT_DELTA}
        network_task = a10_network_tasks.HandleDeletePortDeltas()
        network_task.execute(PARENT_PORT, mock_port_deltas)
        self.network_driver_mock.unplug_trunk_subports.assert_called_with(
            PARENT_PORT.trunk_id, MULTIPLE_DELETE_SUBPORTS)

    def test_deallocate_trunk(self):
        network_task =  a10_network_tasks.DeallocateTrunk()
        self.network_driver_mock.get_plugged_parent_port.return_value = PARENT_PORT
        network_task.execute(LB)
        self.network_driver_mock.get_plugged_parent_port.assert_called_with(LB.vip)
        self.network_driver_mock.deallocate_trunk.assert_called_with(PARENT_PORT.trunk_id)

    def test_deallocate_trunk_not_found(self):
        network_task =  a10_network_tasks.DeallocateTrunk()
        network_task.execute(LB)
        self.network_driver_mock.deallocate_trunk.side_effect = Exception()
        self.assertRaises(Exception, self.network_driver_mock.deallocate_trunk, EMPTY_PARENT_PORT.trunk_id)
