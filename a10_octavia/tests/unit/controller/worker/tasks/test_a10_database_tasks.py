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

from oslo_utils import uuidutils

from octavia.network import data_models as o_data_models

from a10_octavia.common import data_models
from a10_octavia.controller.worker.tasks import a10_database_tasks as task
from a10_octavia.tests.unit import base

VTHUNDER_ID_1 = uuidutils.generate_uuid()
VTHUNDER = data_models.VThunder(id=VTHUNDER_ID_1)
FIXED_IP = o_data_models.FixedIP(ip_address='10.10.10.10')
PORT = o_data_models.Port(id=uuidutils.generate_uuid(), fixed_ips=[FIXED_IP])


class TestA10DatabaseTasks(base.BaseTaskTestCase):
    def setUp(self):
        super(TestA10DatabaseTasks, self).setUp()
        imp.reload(task)
        self.db_session = mock.patch(
            'a10_octavia.controller.worker.tasks.a10_database_tasks.db_apis.get_session')
        self.db_session.start()

    def tearDown(self):
        super(TestA10DatabaseTasks, self).tearDown()
        self.db_session.stop()

    def test_update_vthunder_vrrp_entry_with_port_info(self):
        mock_vthunder_entry = task.UpdateVThunderVRRPEntry()
        mock_vthunder_entry.vthunder_repo = mock.Mock()
        mock_vthunder_entry.execute(VTHUNDER, PORT)
        mock_vthunder_entry.vthunder_repo.update.assert_called_once_with(
            mock.ANY,
            VTHUNDER_ID_1,
            vrrp_port_id=PORT.id,
            vrid_floating_ip=PORT.fixed_ips[0].ip_address)

    def test_update_vthunder_vrrp_entry_with_none_port(self):
        mock_vthunder_entry = task.UpdateVThunderVRRPEntry()
        mock_vthunder_entry.vthunder_repo = mock.Mock()
        mock_vthunder_entry.execute(VTHUNDER, None)
        mock_vthunder_entry.vthunder_repo.update.assert_not_called()
