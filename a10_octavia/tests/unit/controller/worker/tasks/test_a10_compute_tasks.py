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


try:
    from unittest import mock
except ImportError:
    import mock
from oslo_utils import uuidutils

from octavia.common import constants as o_constants

from a10_octavia.common import data_models
from a10_octavia.controller.worker.tasks import a10_compute_tasks as task
from a10_octavia.tests.unit import base

VTHUNDER = data_models.VThunder()
COMPUTE_ID = uuidutils.generate_uuid()


class TestA10ComputeTasks(base.BaseTaskTestCase):

    @mock.patch('stevedore.driver.DriverManager.driver')
    def test_compute_amphora_status_active(self, mock_driver):
        VTHUNDER.compute_id = COMPUTE_ID
        _amphora_mock = mock.MagicMock()
        _amphora_mock.status = o_constants.ACTIVE
        mock_driver.get_amphora.return_value = _amphora_mock, None
        computestatus = task.CheckAmphoraStatus()
        status = computestatus.execute(VTHUNDER)
        self.assertEqual(status, True)

    @mock.patch('stevedore.driver.DriverManager.driver')
    def test_compute_amphora_status_shutoff(self, mock_driver):
        VTHUNDER.compute_id = COMPUTE_ID
        _amphora_mock = mock.MagicMock()
        _amphora_mock.status = "SHUTOFF"
        mock_driver.get_amphora.return_value = _amphora_mock, None
        computestatus = task.CheckAmphoraStatus()
        status = computestatus.execute(VTHUNDER)
        self.assertEqual(status, False)
