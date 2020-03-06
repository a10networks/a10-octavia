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

import acos_client
import mock
from unittest.mock import patch
from acos_client.v30.slb.template.persistence import CookiePersistence

import octavia.tests.unit.base as base
from octavia.common import data_models as o_data_models
from octavia.tests.common import constants as t_constants

from a10_octavia.common.data_models import VThunder
from a10_octavia.controller.worker.tasks.persist_tasks import HandleSessionPersistenceDelta
from a10_octavia.tests.common import a10constants as a10_test_constants

from a10_octavia.controller.worker.tasks.common import BaseVThunderTask
from a10_octavia.tests.unit.base import BaseTaskTestCase


VTHUNDER = VThunder()
POOL = o_data_models.Pool(id=a10_test_constants.MOCK_POOL_ID)
SESSION_PERSISTENCE = o_data_models.SessionPersistence(
    pool_id=a10_test_constants.MOCK_POOL_ID, cookie_name=a10_test_constants.MOCK_COOKIE_NAME)

class TestPersistTasks(BaseTaskTestCase):

    '''@mock.patch('acos_client.v30.slb.template', 'create')
    def test_handle_session_persistence_delta(self, mock_cp):
        mock_session_persist = HandleSessionPersistenceDelta()
        mock_session_persist.execute(VTHUNDER, POOL)
        
        mock_cp = mock.patch.object(CookiePersistence, 'get')
        # mock_cp.create.assert_called_with(POOL.id, cookie_name=SESSION_PERSISTENCE.cookie_name)
        # self.client_mock.slb.template.create.assert_called_with(POOL.id, cookie_name=SESSION_PERSISTENCE.cookie_name)'''


    @mock.patch('acos_client.v30.slb.template.CookiePersistence', 'create')
    def test_handle_session_persistence_delta(self):
        # import pdb; pdb.set_trace()
        mock_session_persist = HandleSessionPersistenceDelta()
        mock_session_persist.execute(VTHUNDER, POOL)
        # mock_session_persist.getattr("axapi_client.slb.template", "SP_OBJ_DICT[sp.type]")
        # self.client_mock.getattr.assert_called_with("self.client_mock.axapi_client.slb.template", "SP_OBJ_DICT[sp.type]")
        # mock_cp.create.assert_called_with(POOL.id, cookie_name=SESSION_PERSISTENCE.cookie_name)
        # self.client_mock.slb.template.create.assert_called_with(POOL.id, cookie_name=SESSION_PERSISTENCE.cookie_name)
