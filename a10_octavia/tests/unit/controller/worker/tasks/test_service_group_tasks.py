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


import imp
try:
    from unittest import mock
except ImportError:
    import mock

from octavia.common import data_models as o_data_models

from a10_octavia.common.data_models import VThunder
import a10_octavia.controller.worker.tasks.service_group_tasks as task
from a10_octavia.tests.common import a10constants
from a10_octavia.tests.unit.base import BaseTaskTestCase

VTHUNDER = VThunder()
POOL = o_data_models.Pool(id=a10constants.MOCK_POOL_ID)


class TestHandlerServiceGroupTasks(BaseTaskTestCase):

    def setUp(self):
        super(TestHandlerServiceGroupTasks, self).setUp()
        imp.reload(task)
        self.client_mock = mock.Mock()

    def test_revert_pool_create_task(self):
        mock_pool = task.PoolCreate()
        mock_pool.axapi_client = self.client_mock
        mock_pool.revert(POOL, VTHUNDER)
        self.client_mock.slb.service_group.delete.assert_called_with(POOL.id)
