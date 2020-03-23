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
    from unittest.mock import patch
except ImportError:
    import mock
    from mock import patch

from octavia.common import data_models as o_data_models
from octavia.tests.common import constants as t_constants

from a10_octavia.controller.worker.tasks.service_group_tasks import PoolCreate
from a10_octavia.common.data_models import VThunder
from a10_octavia.tests.common import a10constants
from a10_octavia.tests.unit.base import BaseTaskTestCase

VTHUNDER = VThunder()
POOL = o_data_models.Pool(id=a10constants.MOCK_POOL_ID)


class TestHandlerServiceGroupTasks(BaseTaskTestCase):

    def setUp(self):
        super(TestHandlerServerTasks, self).setUp()
        imp.reload(task)
        self.client_mock = mock.Mock()
 
    @patch('octavia.controller.worker.task_utils.TaskUtils')
    def test_revert_pool_create_task(self, mock_task_utils):
        mock_pool = PoolCreate()
        mock_pool.revert(POOL, VTHUNDER)
        mock_pool.task_utils.mark_pool_prov_status_error.assert_called_with(POOL.id)
        self.client_mock.slb.service_group.delete.assert_called_with(POOL.id)
