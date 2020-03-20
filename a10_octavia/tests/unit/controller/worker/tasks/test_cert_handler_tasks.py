import copy
import imp
import mock
from unittest.mock import patch

from octavia.certificates.common.auth.barbican_acl import BarbicanACLAuth
from octavia.common import data_models as o_data_models
from octavia.tests.common import constants as t_constants
import octavia.tests.unit.base as base

from a10_octavia.common.data_models import VThunder
from a10_octavia.controller.worker.tasks import cert_handler_tasks
from a10_octavia.tests.common import a10constants as a10_test_constants
from a10_octavia.tests.unit.base import BaseTaskTestCase

LB = o_data_models.LoadBalancer(id=a10_test_constants.MOCK_LOAD_BALANCER_ID,
                                project_id=t_constants.MOCK_PROJECT_ID)
LISTENER = o_data_models.Listener(protocol='TERMINATED_HTTPS', protocol_port=2222,
                                  load_balancer=LB, tls_certificate_id='certificate-id-1')
VTHUNDER = VThunder()

CERT_DATA = { 'cert_filename': a10_test_constants.MOCK_CERT_FILENAME,
              'cert_content': a10_test_constants.MOCK_CERT_CONTENT,
              'key_filename': a10_test_constants.MOCK_KEY_FILENAME,
              'key_content': a10_test_constants.MOCK_KEY_CONTENT,
              'template_name': a10_test_constants.MOCK_TEMPLATE_NAME,
              'key_pass': a10_test_constants.MOCK_KEY_PASS
            }


class TestCertHandlerTasks(BaseTaskTestCase):

    def setUp(self):
        super(TestCertHandlerTasks, self).setUp()
        imp.reload(cert_handler_tasks)
        self.listener = copy.deepcopy(LISTENER)
        self.client_mock = mock.Mock()

    # SSL Cert
    @patch.object(BarbicanACLAuth, 'get_barbican_client')
    @mock.patch('a10_octavia.controller.worker.tasks.utils.get_cert_data', return_value=CERT_DATA)
    def test_ssl_cert_create_update(self, barbican_class):
        mock_ssl_cert = cert_handler_tasks.SSLCertCreate()
        mock_ssl_cert.axapi_client = self.client_mock
        mock_ssl_cert.execute(LB, self.listener, VTHUNDER)
        self.client_mock.file.ssl_cert.exists.assert_called_with(
            file=a10_test_constants.MOCK_CERT_FILENAME)
        self.client_mock.file.ssl_cert.update.assert_called_with(
            file=a10_test_constants.MOCK_CERT_FILENAME, cert=a10_test_constants.MOCK_CERT_CONTENT,
            size=len(a10_test_constants.MOCK_CERT_CONTENT), action=a10_test_constants.MOCK_CERT_ACTION,
            certificate_type=a10_test_constants.MOCK_CERT_TYPE)
        self.client_mock.file.ssl_cert.create.assert_not_called()

    @patch.object(BarbicanACLAuth, 'get_barbican_client')
    @mock.patch('a10_octavia.controller.worker.tasks.utils.get_cert_data', return_value=CERT_DATA)
    def test_ssl_cert_create_new(self, barbican_class):
        mock_ssl_cert = cert_handler_tasks.SSLCertCreate()
        mock_ssl_cert.axapi_client = self.client_mock
        self.client_mock.file.ssl_cert.exists.return_value = False
        mock_ssl_cert.execute(LB, self.listener, VTHUNDER)
        self.client_mock.file.ssl_cert.create.assert_called_with(
            file=a10_test_constants.MOCK_CERT_FILENAME, cert=a10_test_constants.MOCK_CERT_CONTENT,
            size=len(a10_test_constants.MOCK_CERT_CONTENT), action=a10_test_constants.MOCK_CERT_ACTION,
            certificate_type=a10_test_constants.MOCK_CERT_TYPE)
        self.client_mock.file.ssl_cert.update.assert_not_called()

    @patch.object(BarbicanACLAuth, 'get_barbican_client')
    @mock.patch('a10_octavia.controller.worker.tasks.utils.get_cert_data', return_value=CERT_DATA)
    def test_ssl_cert_create_revert(self, barbican_class):
        mock_ssl_cert = cert_handler_tasks.SSLCertCreate()
        mock_ssl_cert.axapi_client = self.client_mock
        mock_ssl_cert.revert(LB, self.listener, VTHUNDER)
        self.client_mock.file.ssl_cert.delete.assert_called_with(
            file=a10_test_constants.MOCK_CERT_FILENAME)

    @patch.object(BarbicanACLAuth, 'get_barbican_client')
    @mock.patch('a10_octavia.controller.worker.tasks.utils.get_cert_data', return_value=CERT_DATA)
    def test_ssl_cert_update(self, barbican_class):
        mock_ssl_cert = cert_handler_tasks.SSLCertUpdate()
        mock_ssl_cert.axapi_client = self.client_mock
        mock_ssl_cert.execute(LB, self.listener, VTHUNDER)
        self.client_mock.file.ssl_cert.exists.assert_called_with(
            file=a10_test_constants.MOCK_CERT_FILENAME)
        self.client_mock.file.ssl_cert.update.assert_called_with(
            file=a10_test_constants.MOCK_CERT_FILENAME, cert=a10_test_constants.MOCK_CERT_CONTENT,
            size=len(a10_test_constants.MOCK_CERT_CONTENT), action=a10_test_constants.MOCK_CERT_ACTION,
            certificate_type=a10_test_constants.MOCK_CERT_TYPE)

    @patch.object(BarbicanACLAuth, 'get_barbican_client')
    @mock.patch('a10_octavia.controller.worker.tasks.utils.get_cert_data', return_value=CERT_DATA)
    def test_ssl_cert_delete(self, barbican_class):
        mock_ssl_cert = cert_handler_tasks.SSLCertDelete()
        mock_ssl_cert.axapi_client = self.client_mock
        mock_ssl_cert.execute(LB, self.listener, VTHUNDER)
        self.client_mock.file.ssl_cert.exists.assert_called_with(
            file=a10_test_constants.MOCK_CERT_FILENAME)
        self.client_mock.file.ssl_cert.delete.assert_called_with(
            file=a10_test_constants.MOCK_CERT_FILENAME)

    # SSL Key
    @patch.object(BarbicanACLAuth, 'get_barbican_client')
    def test_ssl_key_create_update(self, barbican_class):
        mock_ssl_key = cert_handler_tasks.SSLKeyCreate()
        mock_ssl_key.axapi_client = self.client_mock
        mock_ssl_key.execute(CERT_DATA, VTHUNDER)
        self.client_mock.file.ssl_key.exists.assert_called_with(
            file=a10_test_constants.MOCK_KEY_FILENAME)
        self.client_mock.file.ssl_key.update.assert_called_with(
            file=a10_test_constants.MOCK_KEY_FILENAME, cert=a10_test_constants.MOCK_KEY_CONTENT,
            size=len(a10_test_constants.MOCK_KEY_CONTENT), action=a10_test_constants.MOCK_CERT_ACTION)
        self.client_mock.file.ssl_key.create.assert_not_called()

    @patch.object(BarbicanACLAuth, 'get_barbican_client')
    def test_ssl_key_create_new(self, barbican_class):
        mock_ssl_key = cert_handler_tasks.SSLKeyCreate()
        mock_ssl_key.axapi_client = self.client_mock
        self.client_mock.file.ssl_key.exists.return_value = False
        mock_ssl_key.execute(CERT_DATA, VTHUNDER)
        self.client_mock.file.ssl_key.create.assert_called_with(
            file=a10_test_constants.MOCK_KEY_FILENAME, cert=a10_test_constants.MOCK_KEY_CONTENT,
            size=len(a10_test_constants.MOCK_KEY_CONTENT), action=a10_test_constants.MOCK_CERT_ACTION)
        self.client_mock.file.ssl_key.update.assert_not_called()

    @patch.object(BarbicanACLAuth, 'get_barbican_client')
    def test_ssl_key_create_revert(self, barbican_class):
        mock_ssl_key = cert_handler_tasks.SSLKeyCreate()
        mock_ssl_key.axapi_client = self.client_mock
        mock_ssl_key.revert(CERT_DATA, VTHUNDER)
        self.client_mock.file.ssl_key.delete.assert_called_with(
            file=a10_test_constants.MOCK_KEY_FILENAME)

    @patch.object(BarbicanACLAuth, 'get_barbican_client')
    def test_ssl_key_update(self, barbican_class):
        mock_ssl_key = cert_handler_tasks.SSLKeyUpdate()
        mock_ssl_key.axapi_client = self.client_mock
        mock_ssl_key.execute(CERT_DATA, VTHUNDER)
        self.client_mock.file.ssl_key.exists.assert_called_with(
            file=a10_test_constants.MOCK_KEY_FILENAME)
        self.client_mock.file.ssl_key.update.assert_called_with(
            file=a10_test_constants.MOCK_KEY_FILENAME, cert=a10_test_constants.MOCK_KEY_CONTENT,
            size=len(a10_test_constants.MOCK_KEY_CONTENT), action=a10_test_constants.MOCK_CERT_ACTION)

    @patch.object(BarbicanACLAuth, 'get_barbican_client')
    def test_ssl_key_delete(self, barbican_class):
        mock_ssl_key = cert_handler_tasks.SSLKeyDelete()
        mock_ssl_key.axapi_client = self.client_mock
        mock_ssl_key.execute(CERT_DATA, VTHUNDER)
        self.client_mock.file.ssl_key.delete.assert_called_with(
            file=a10_test_constants.MOCK_KEY_FILENAME)

    # Client Template
    @patch.object(BarbicanACLAuth, 'get_barbican_client')
    def test_client_ssl_template_create_update(self, barbican_class):
        mock_client_ssl_template = cert_handler_tasks.ClientSSLTemplateCreate()
        mock_client_ssl_template.axapi_client = self.client_mock
        mock_client_ssl_template.execute(CERT_DATA, VTHUNDER)
        self.client_mock.slb.template.client_ssl.exists.assert_called_with(
            name=a10_test_constants.MOCK_TEMPLATE_NAME)
        self.client_mock.slb.template.client_ssl.update.assert_called_with(
            name=a10_test_constants.MOCK_TEMPLATE_NAME, cert=a10_test_constants.MOCK_CERT_FILENAME,
            key=a10_test_constants.MOCK_KEY_FILENAME, passphrase=a10_test_constants.MOCK_KEY_PASS)
        self.client_mock.slb.template.client_ssl.create.assert_not_called()

    @patch.object(BarbicanACLAuth, 'get_barbican_client')
    def test_client_ssl_template_create_new(self, barbican_class):
        mock_client_ssl_template = cert_handler_tasks.ClientSSLTemplateCreate()
        mock_client_ssl_template.axapi_client = self.client_mock
        self.client_mock.slb.template.client_ssl.exists.return_value = False
        mock_client_ssl_template.execute(CERT_DATA, VTHUNDER)
        self.client_mock.slb.template.client_ssl.create.assert_called_with(
            name=a10_test_constants.MOCK_TEMPLATE_NAME, cert=a10_test_constants.MOCK_CERT_FILENAME,
            key=a10_test_constants.MOCK_KEY_FILENAME, passphrase=a10_test_constants.MOCK_KEY_PASS)
        self.client_mock.slb.template.client_ssl.update.assert_not_called()

    @patch.object(BarbicanACLAuth, 'get_barbican_client')
    def test_client_ssl_template_create_revert(self, barbican_class):
        mock_client_ssl_template = cert_handler_tasks.ClientSSLTemplateCreate()
        mock_client_ssl_template.axapi_client = self.client_mock
        mock_client_ssl_template.revert(CERT_DATA, VTHUNDER)
        self.client_mock.slb.template.client_ssl.delete.assert_called_with(
            name=a10_test_constants.MOCK_TEMPLATE_NAME)

    @patch.object(BarbicanACLAuth, 'get_barbican_client')
    def test_client_ssl_template_update(self, barbican_class):
        mock_client_ssl_template = cert_handler_tasks.ClientSSLTemplateUpdate()
        mock_client_ssl_template.axapi_client = self.client_mock
        mock_client_ssl_template.execute(CERT_DATA, VTHUNDER)
        self.client_mock.slb.template.client_ssl.exists.assert_called_with(
            name=a10_test_constants.MOCK_TEMPLATE_NAME)
        self.client_mock.slb.template.client_ssl.update.assert_called_with(
            name=a10_test_constants.MOCK_TEMPLATE_NAME, cert=a10_test_constants.MOCK_CERT_FILENAME,
            key=a10_test_constants.MOCK_KEY_FILENAME, passphrase=a10_test_constants.MOCK_KEY_PASS)

    @patch.object(BarbicanACLAuth, 'get_barbican_client')
    def test_client_ssl_template_delete(self, barbican_class):
        mock_client_ssl_template = cert_handler_tasks.ClientSSLTemplateDelete()
        mock_client_ssl_template.axapi_client = self.client_mock
        mock_client_ssl_template.execute(CERT_DATA, VTHUNDER)
        self.client_mock.slb.template.client_ssl.delete.assert_called_with(
            name=a10_test_constants.MOCK_TEMPLATE_NAME)

