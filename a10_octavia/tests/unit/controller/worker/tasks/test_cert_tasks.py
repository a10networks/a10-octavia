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


import copy
import imp

try:
    from unittest import mock
    from unittest.mock import patch
except ImportError:
    import mock
    from mock import patch

from octavia.certificates.common.auth.barbican_acl import BarbicanACLAuth
from octavia.common import data_models as o_data_models
from octavia.tests.common import constants as t_constants

from a10_octavia.common.data_models import Certificate
from a10_octavia.common.data_models import VThunder
from a10_octavia.controller.worker.tasks import cert_tasks
from a10_octavia.tests.common import a10constants as a10_test_constants
from a10_octavia.tests.unit.base import BaseTaskTestCase

LB = o_data_models.LoadBalancer(id=a10_test_constants.MOCK_LOAD_BALANCER_ID,
                                project_id=t_constants.MOCK_PROJECT_ID)
LISTENER = o_data_models.Listener(id=a10_test_constants.MOCK_LISTENER_ID,
                                  protocol='TERMINATED_HTTPS', protocol_port=2222,
                                  load_balancer=LB, tls_certificate_id='certificate-id-1')
VTHUNDER = VThunder()

CERT_DATA = Certificate(cert_filename=a10_test_constants.MOCK_CERT_FILENAME,
                        cert_content=a10_test_constants.MOCK_CERT_CONTENT,
                        key_filename=a10_test_constants.MOCK_KEY_FILENAME,
                        key_content=a10_test_constants.MOCK_KEY_CONTENT,
                        template_name=a10_test_constants.MOCK_TEMPLATE_NAME,
                        key_pass=a10_test_constants.MOCK_KEY_PASS)


class TestCertHandlerTasks(BaseTaskTestCase):

    def setUp(self):
        super(TestCertHandlerTasks, self).setUp()
        imp.reload(cert_tasks)
        self.listener = copy.deepcopy(LISTENER)
        self.client_mock = mock.Mock()

    @patch.object(BarbicanACLAuth, 'get_barbican_client')
    @mock.patch('a10_octavia.controller.worker.tasks.utils.get_cert_data', return_value=CERT_DATA)
    def test_GetSSLCertData_success(self, barbican_class, cert_data):
        mock_ssl_cert = cert_tasks.GetSSLCertData()
        out = mock_ssl_cert.execute(LB, LISTENER)
        self.assertEqual(out, CERT_DATA)

    @patch.object(BarbicanACLAuth, 'get_barbican_client')
    def test_GetSSLCertData_barbican_exception(self, barbican_class):
        mock_ssl_cert = cert_tasks.SSLCertCreate()
        mock_ssl_cert.axapi_client = self.client_mock
        barbican_class.side_effect = Exception
        self.assertRaises(Exception, lambda: mock_ssl_cert.execute(LB, LISTENER))
        self.client_mock.file.ssl_cert.exists.assert_not_called()

    # SSL Cert
    def test_ssl_cert_create_update(self):
        mock_ssl_cert = cert_tasks.SSLCertCreate()
        mock_ssl_cert.axapi_client = self.client_mock
        mock_ssl_cert.execute(CERT_DATA, VTHUNDER)
        self.client_mock.file.ssl_cert.exists.assert_called_with(
            file=a10_test_constants.MOCK_CERT_FILENAME)
        self.client_mock.file.ssl_cert.update.assert_called_with(
            file=a10_test_constants.MOCK_CERT_FILENAME,
            cert=a10_test_constants.MOCK_CERT_CONTENT,
            size=len(a10_test_constants.MOCK_CERT_CONTENT),
            action=a10_test_constants.MOCK_CERT_ACTION,
            certificate_type=a10_test_constants.MOCK_CERT_TYPE)
        self.client_mock.file.ssl_cert.create.assert_not_called()

    def test_ssl_cert_create_new(self):
        mock_ssl_cert = cert_tasks.SSLCertCreate()
        mock_ssl_cert.axapi_client = self.client_mock
        self.client_mock.file.ssl_cert.exists.return_value = False
        mock_ssl_cert.execute(CERT_DATA, VTHUNDER)
        self.client_mock.file.ssl_cert.create.assert_called_with(
            file=a10_test_constants.MOCK_CERT_FILENAME,
            cert=a10_test_constants.MOCK_CERT_CONTENT,
            size=len(a10_test_constants.MOCK_CERT_CONTENT),
            action=a10_test_constants.MOCK_CERT_ACTION,
            certificate_type=a10_test_constants.MOCK_CERT_TYPE)
        self.client_mock.file.ssl_cert.update.assert_not_called()

    def test_ssl_cert_create_revert(self):
        mock_ssl_cert = cert_tasks.SSLCertCreate()
        mock_ssl_cert.axapi_client = self.client_mock
        mock_ssl_cert.revert(CERT_DATA, VTHUNDER)
        self.client_mock.file.ssl_cert.delete.assert_called_with(
            private_key=a10_test_constants.MOCK_KEY_FILENAME,
            cert_name=a10_test_constants.MOCK_CERT_FILENAME)

    def test_ssl_cert_update(self):
        mock_ssl_cert = cert_tasks.SSLCertUpdate()
        mock_ssl_cert.axapi_client = self.client_mock
        mock_ssl_cert.execute(CERT_DATA, VTHUNDER)
        self.client_mock.file.ssl_cert.exists.assert_called_with(
            file=a10_test_constants.MOCK_CERT_FILENAME)
        self.client_mock.file.ssl_cert.update.assert_called_with(
            file=a10_test_constants.MOCK_CERT_FILENAME,
            cert=a10_test_constants.MOCK_CERT_CONTENT,
            size=len(a10_test_constants.MOCK_CERT_CONTENT),
            action=a10_test_constants.MOCK_CERT_ACTION,
            certificate_type=a10_test_constants.MOCK_CERT_TYPE)

    def test_ssl_cert_delete(self):
        mock_ssl_cert = cert_tasks.SSLCertDelete()
        mock_ssl_cert.axapi_client = self.client_mock
        mock_ssl_cert.execute(CERT_DATA, VTHUNDER)
        self.client_mock.file.ssl_cert.exists.assert_called_with(
            file=a10_test_constants.MOCK_CERT_FILENAME)
        self.client_mock.file.ssl_cert.delete.assert_called_with(
            private_key=a10_test_constants.MOCK_KEY_FILENAME,
            cert_name=a10_test_constants.MOCK_CERT_FILENAME)

    # SSL Key
    def test_ssl_key_create_update(self):
        mock_ssl_key = cert_tasks.SSLKeyCreate()
        mock_ssl_key.axapi_client = self.client_mock
        mock_ssl_key.execute(CERT_DATA, VTHUNDER)
        self.client_mock.file.ssl_key.exists.assert_called_with(
            file=a10_test_constants.MOCK_KEY_FILENAME)
        self.client_mock.file.ssl_key.update.assert_called_with(
            file=a10_test_constants.MOCK_KEY_FILENAME,
            cert=a10_test_constants.MOCK_KEY_CONTENT,
            size=len(a10_test_constants.MOCK_KEY_CONTENT),
            action=a10_test_constants.MOCK_CERT_ACTION)
        self.client_mock.file.ssl_key.create.assert_not_called()

    def test_ssl_key_create_new(self):
        mock_ssl_key = cert_tasks.SSLKeyCreate()
        mock_ssl_key.axapi_client = self.client_mock
        self.client_mock.file.ssl_key.exists.return_value = False
        mock_ssl_key.execute(CERT_DATA, VTHUNDER)
        self.client_mock.file.ssl_key.create.assert_called_with(
            file=a10_test_constants.MOCK_KEY_FILENAME,
            cert=a10_test_constants.MOCK_KEY_CONTENT,
            size=len(a10_test_constants.MOCK_KEY_CONTENT),
            action=a10_test_constants.MOCK_CERT_ACTION)
        self.client_mock.file.ssl_key.update.assert_not_called()

    def test_ssl_key_create_revert(self):
        mock_ssl_key = cert_tasks.SSLKeyCreate()
        mock_ssl_key.axapi_client = self.client_mock
        mock_ssl_key.revert(CERT_DATA, VTHUNDER)
        self.client_mock.file.ssl_key.delete.assert_called_with(
            private_key=a10_test_constants.MOCK_KEY_FILENAME)

    def test_ssl_key_update(self):
        mock_ssl_key = cert_tasks.SSLKeyUpdate()
        mock_ssl_key.axapi_client = self.client_mock
        mock_ssl_key.execute(CERT_DATA, VTHUNDER)
        self.client_mock.file.ssl_key.exists.assert_called_with(
            file=a10_test_constants.MOCK_KEY_FILENAME)
        self.client_mock.file.ssl_key.update.assert_called_with(
            file=a10_test_constants.MOCK_KEY_FILENAME,
            cert=a10_test_constants.MOCK_KEY_CONTENT,
            size=len(a10_test_constants.MOCK_KEY_CONTENT),
            action=a10_test_constants.MOCK_CERT_ACTION)

    def test_ssl_key_delete(self):
        mock_ssl_key = cert_tasks.SSLKeyDelete()
        mock_ssl_key.axapi_client = self.client_mock
        mock_ssl_key.execute(CERT_DATA, VTHUNDER)
        self.client_mock.file.ssl_key.delete.assert_called_with(
            private_key=a10_test_constants.MOCK_KEY_FILENAME)

    # Client Template
    def test_client_ssl_template_create_update(self):
        mock_client_ssl_template = cert_tasks.ClientSSLTemplateCreate()
        mock_client_ssl_template.axapi_client = self.client_mock
        mock_client_ssl_template.execute(CERT_DATA, VTHUNDER)
        self.client_mock.slb.template.client_ssl.exists.assert_called_with(
            name=a10_test_constants.MOCK_LISTENER_ID)
        self.client_mock.slb.template.client_ssl.update.assert_called_with(
            name=a10_test_constants.MOCK_LISTENER_ID,
            cert=a10_test_constants.MOCK_CERT_FILENAME,
            key=a10_test_constants.MOCK_KEY_FILENAME,
            passphrase=a10_test_constants.MOCK_KEY_PASS)
        self.client_mock.slb.template.client_ssl.create.assert_not_called()

    def test_client_ssl_template_create_new(self):
        mock_client_ssl_template = cert_tasks.ClientSSLTemplateCreate()
        mock_client_ssl_template.axapi_client = self.client_mock
        self.client_mock.slb.template.client_ssl.exists.return_value = False
        mock_client_ssl_template.execute(CERT_DATA, VTHUNDER)
        self.client_mock.slb.template.client_ssl.create.assert_called_with(
            name=a10_test_constants.MOCK_LISTENER_ID,
            cert=a10_test_constants.MOCK_CERT_FILENAME,
            key=a10_test_constants.MOCK_KEY_FILENAME,
            passphrase=a10_test_constants.MOCK_KEY_PASS)
        self.client_mock.slb.template.client_ssl.update.assert_not_called()

    def test_client_ssl_template_create_revert(self):
        mock_client_ssl_template = cert_tasks.ClientSSLTemplateCreate()
        mock_client_ssl_template.axapi_client = self.client_mock
        mock_client_ssl_template.revert(CERT_DATA, VTHUNDER)
        self.client_mock.slb.template.client_ssl.delete.assert_called_with(
            name=a10_test_constants.MOCK_LISTENER_ID)

    def test_client_ssl_template_update(self):
        mock_client_ssl_template = cert_tasks.ClientSSLTemplateUpdate()
        mock_client_ssl_template.axapi_client = self.client_mock
        mock_client_ssl_template.execute(CERT_DATA, VTHUNDER)
        self.client_mock.slb.template.client_ssl.exists.assert_called_with(
            name=a10_test_constants.MOCK_LISTENER_ID)
        self.client_mock.slb.template.client_ssl.update.assert_called_with(
            name=a10_test_constants.MOCK_LISTENER_ID,
            cert=a10_test_constants.MOCK_CERT_FILENAME,
            key=a10_test_constants.MOCK_KEY_FILENAME,
            passphrase=a10_test_constants.MOCK_KEY_PASS)

    def test_client_ssl_template_delete(self):
        mock_client_ssl_template = cert_tasks.ClientSSLTemplateDelete()
        mock_client_ssl_template.axapi_client = self.client_mock
        mock_client_ssl_template.execute(CERT_DATA, VTHUNDER)
        self.client_mock.slb.template.client_ssl.delete.assert_called_with(
            name=a10_test_constants.MOCK_LISTENER_ID)
