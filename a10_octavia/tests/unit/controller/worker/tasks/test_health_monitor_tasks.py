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

from octavia.common import constants as o_constants
from octavia.common import data_models as o_data_models

from a10_octavia.common.data_models import VThunder
import a10_octavia.controller.worker.tasks.health_monitor_tasks as task
from a10_octavia.controller.worker.tasks import utils
from a10_octavia.tests.common import a10constants
from a10_octavia.tests.unit.base import BaseTaskTestCase

VTHUNDER = VThunder()
HM = o_data_models.HealthMonitor(id=a10constants.MOCK_HM_ID,
                                 type=o_constants.HEALTH_MONITOR_TCP,
                                 delay=o_constants.DELAY,
                                 timeout=o_constants.TIMEOUT,
                                 rise_threshold=o_constants.RISE_THRESHOLD,
                                 http_method=o_constants.HTTP_METHOD,
                                 url_path=o_constants.URL_PATH,
                                 expected_codes=o_constants.EXPECTED_CODES)
ARGS = utils.meta(HM, 'hm', {})
LISTENERS = [o_data_models.Listener(id=a10constants.MOCK_LISTENER_ID, protocol_port=mock.ANY)]


class TestHandlerHealthMonitorTasks(BaseTaskTestCase):

    def setUp(self):
        super(TestHandlerHealthMonitorTasks, self).setUp()
        imp.reload(task)
        self.client_mock = mock.Mock()

    def tearDown(self):
        super(TestHandlerHealthMonitorTasks, self).tearDown()

    def test_health_monitor_create_task(self):
        mock_hm = task.CreateAndAssociateHealthMonitor()
        mock_hm.axapi_client = self.client_mock
        mock_hm.execute(LISTENERS, HM, VTHUNDER)
        self.client_mock.slb.hm.create.assert_called_with(a10constants.MOCK_HM_ID,
                                                          self.client_mock.slb.hm.TCP,
                                                          HM.delay, HM.timeout,
                                                          HM.rise_threshold, method=None,
                                                          port=mock.ANY, url=None,
                                                          expect_code=None, axapi_args=ARGS)

    def test_health_monitor_update_task(self):
        mock_hm = task.UpdateHealthMonitor()
        mock_hm.axapi_client = self.client_mock
        UPDATE_DICT = {'HM.delay': '10'}
        mock_hm.execute(LISTENERS, HM, VTHUNDER, UPDATE_DICT)
        self.client_mock.slb.hm.update.assert_called_with(a10constants.MOCK_HM_ID,
                                                          self.client_mock.slb.hm.TCP,
                                                          HM.delay, HM.timeout,
                                                          HM.rise_threshold, method=None,
                                                          port=mock.ANY, url=None,
                                                          expect_code=None, axapi_args=ARGS)

    def test_health_monitor_delete_task(self):
        mock_hm = task.DeleteHealthMonitor()
        mock_hm.axapi_client = self.client_mock
        mock_hm.execute(HM, VTHUNDER)
        self.client_mock.slb.hm.delete.assert_called_with(a10constants.MOCK_HM_ID)
