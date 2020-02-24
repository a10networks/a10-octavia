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

# -*- coding: utf-8 -*-

import mock

from octavia.tests.common import constants as t_constants
import octavia.tests.unit.base as base

from a10_octavia.controller.worker.tasks import a10_network_tasks
from a10_octavia.network import data_models
from a10_octavia.network.data_models import Subport
from a10_octavia.tests.common import a10constants as a10_test_constants

SUBPORT = Subport(segmentation_id=a10_test_constants.SEGMENTATION_ID)


class TestNetworkTasks(base.TestCase):

    @mock.patch('a10_octavia.controller.worker.tasks.a10_network_tasks.BaseNetworkTask.network_driver')
    def test_handle_delete_port_deltas(self, get_network_drivers_mock):
        get_network_drivers_mock.return_value = mock.Mock()
        mock_parent_port = data_models.ParentPort(trunk_id=a10_test_constants.TRUNK_ID)

        empty_mock_port_deltas = {t_constants.MOCK_AMP_ID1: data_models.PortDelta(
            amphora_id=t_constants.MOCK_AMP_ID1, compute_id=t_constants.MOCK_AMP_COMPUTE_ID1,
            add_subports=[], delete_subports=[])}
        net = a10_network_tasks.HandleDeletePortDeltas()
        self.assertEqual({t_constants.MOCK_AMP_ID1: []}, net.execute(
            mock_parent_port, empty_mock_port_deltas))

        delete_subports = {t_constants.MOCK_AMP_ID2: [SUBPORT]}
        mock_port_deltas = {t_constants.MOCK_AMP_ID2: data_models.PortDelta(
            amphora_id=t_constants.MOCK_AMP_ID2, compute_id=t_constants.MOCK_AMP_COMPUTE_ID2,
            add_subports=[], delete_subports=delete_subports)}
        net.execute(mock_parent_port, mock_port_deltas)
        get_network_drivers_mock.unplug_trunk_subports.assert_called_with(
            mock_parent_port.trunk_id, delete_subports)
