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

import acos_client.errors as acos_errors
import copy
import imp
try:
    from unittest import mock
except ImportError:
    import mock

from octavia.common import data_models as o_data_models

from a10_octavia.common.data_models import VThunder
from a10_octavia.controller.worker.tasks import persist_tasks
from a10_octavia.tests.common import a10constants as a10_test_constants
from a10_octavia.tests.unit.base import BaseTaskTestCase

VTHUNDER = VThunder()
POOL = o_data_models.Pool(id=a10_test_constants.MOCK_POOL_ID)
SOURCE_IP_SESS_PERS = o_data_models.SessionPersistence(
    pool_id=a10_test_constants.MOCK_POOL_ID,
    type='SOURCE_IP')
APP_COOKIE_SESS_PERS = o_data_models.SessionPersistence(
    pool_id=a10_test_constants.MOCK_POOL_ID,
    type='APP_COOKIE', cookie_name=a10_test_constants.MOCK_COOKIE_NAME)
HTTP_COOKIE_SESS_PERS = o_data_models.SessionPersistence(
    pool_id=a10_test_constants.MOCK_POOL_ID,
    type='HTTP_COOKIE', cookie_name=a10_test_constants.MOCK_COOKIE_NAME)
APP_COOKIE_SESS_PERS_WITH_NO_TYPE = o_data_models.SessionPersistence(
    pool_id=a10_test_constants.MOCK_POOL_ID,
    cookie_name=a10_test_constants.MOCK_COOKIE_NAME)


class TestPersistTasks(BaseTaskTestCase):

    def setUp(self):
        super(TestPersistTasks, self).setUp()
        imp.reload(persist_tasks)
        self.pool = copy.deepcopy(POOL)
        self.client_mock = mock.Mock()

    def test_handle_session_persistence_with_source_ip(self):
        mock_session_persist = persist_tasks.HandleSessionPersistenceDelta()
        mock_session_persist.axapi_client = self.client_mock
        self.pool.session_persistence = SOURCE_IP_SESS_PERS
        mock_session_persist.execute(VTHUNDER, self.pool)
        self.client_mock.slb.template.src_ip_persistence.delete.assert_called_with(
            POOL.id)
        self.client_mock.slb.template.src_ip_persistence.create.assert_called_with(
            POOL.id)

    def test_handle_session_persistence_with_app_cookie(self):
        mock_session_persist = persist_tasks.HandleSessionPersistenceDelta()
        mock_session_persist.axapi_client = self.client_mock
        self.pool.session_persistence = APP_COOKIE_SESS_PERS
        mock_session_persist.execute(VTHUNDER, self.pool)
        self.client_mock.slb.template.cookie_persistence.delete.assert_called_with(
            POOL.id)
        self.client_mock.slb.template.cookie_persistence.create.assert_called_with(
            POOL.id, cookie_name=a10_test_constants.MOCK_COOKIE_NAME)

    def test_handle_session_persistence_with_http_cookie(self):
        mock_session_persist = persist_tasks.HandleSessionPersistenceDelta()
        mock_session_persist.axapi_client = self.client_mock
        self.pool.session_persistence = HTTP_COOKIE_SESS_PERS
        mock_session_persist.execute(VTHUNDER, self.pool)
        self.client_mock.slb.template.cookie_persistence.delete.assert_called_with(
            POOL.id)
        self.client_mock.slb.template.cookie_persistence.create.assert_called_with(
            POOL.id, cookie_name=a10_test_constants.MOCK_COOKIE_NAME)

    def test_handle_session_persistence_with_app_cookie_with_no_sess_pers_type(self):
        mock_session_persist = persist_tasks.HandleSessionPersistenceDelta()
        mock_session_persist.axapi_client = self.client_mock
        self.pool.session_persistence = APP_COOKIE_SESS_PERS_WITH_NO_TYPE
        mock_session_persist.execute(VTHUNDER, self.pool)
        self.client_mock.slb.template.cookie_persistence.delete.assert_not_called()
        self.client_mock.slb.template.cookie_persistence.create.assert_not_called()

    def test_handle_session_persistence_with_source_ip_with_no_sess_pers(self):
        mock_session_persist = persist_tasks.HandleSessionPersistenceDelta()
        mock_session_persist.axapi_client = self.client_mock
        mock_session_persist.execute(VTHUNDER, self.pool)
        self.client_mock.slb.template.src_ip_persistence.delete.assert_not_called()
        self.client_mock.slb.template.src_ip_persistence.create.assert_not_called()

    def test_revert_handle_session_persistence_with_source_ip(self):
        mock_session_persist = persist_tasks.HandleSessionPersistenceDelta()
        mock_session_persist.axapi_client = self.client_mock
        self.pool.session_persistence = SOURCE_IP_SESS_PERS
        mock_session_persist.execute(VTHUNDER, self.pool)
        self.client_mock.slb.template.src_ip_persistence.delete.assert_called_with(
            POOL.id)

    def test_revert_handle_session_persistence_with_http_cookie(self):
        mock_session_persist = persist_tasks.HandleSessionPersistenceDelta()
        mock_session_persist.axapi_client = self.client_mock
        self.pool.session_persistence = HTTP_COOKIE_SESS_PERS
        mock_session_persist.execute(VTHUNDER, self.pool)
        self.client_mock.slb.template.cookie_persistence.delete.assert_called_with(
            POOL.id)

    def test_handle_session_persistence_exception(self):
        mock_session_persist = persist_tasks.HandleSessionPersistenceDelta()
        mock_session_persist.axapi_client = self.client_mock
        self.client_mock.side_effect = acos_errors.Exists
        mock_session_persist.execute(VTHUNDER, self.pool)

    def test_delete_session_persistence(self):
        mock_session_persist = persist_tasks.DeleteSessionPersistence()
        mock_session_persist.axapi_client = self.client_mock
        self.pool.session_persistence = APP_COOKIE_SESS_PERS
        mock_session_persist.execute(VTHUNDER, self.pool)
        self.client_mock.slb.template.cookie_persistence.delete.assert_called_with(POOL.id)

    def test_delete_session_persistence_with_no_sess_pers(self):
        mock_session_persist = persist_tasks.DeleteSessionPersistence()
        mock_session_persist.axapi_client = self.client_mock
        mock_session_persist.execute(VTHUNDER, self.pool)
        self.client_mock.slb.template.cookie_persistence.delete.assert_not_called()
