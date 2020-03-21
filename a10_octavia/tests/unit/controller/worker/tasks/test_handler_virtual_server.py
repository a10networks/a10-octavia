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

from octavia.common import data_models as o_data_models
from octavia.tests.common import constants as t_constants

from a10_octavia.common.data_models import VThunder
from a10_octavia.controller.worker.tasks.virtual_server_tasks import CreateVirtualServerTask
from a10_octavia.tests.common import a10constants
from a10_octavia.tests.unit.base import BaseTaskTestCase

AMPHORA = o_data_models.Amphora(id=t_constants.MOCK_AMP_ID1)
VTHUNDER = VThunder()
LB = o_data_models.LoadBalancer(id=a10constants.MOCK_LOAD_BALANCER_ID, amphorae=[AMPHORA])


class TestHandlerVirtualServerTasks(BaseTaskTestCase):

    def test_revert_create_virtual_server_task(self):
        mock_load_balancer = CreateVirtualServerTask()
        mock_load_balancer.revert(LB, VTHUNDER)
        self.client_mock.slb.virtual_server.delete.assert_called_with(LB.id)
