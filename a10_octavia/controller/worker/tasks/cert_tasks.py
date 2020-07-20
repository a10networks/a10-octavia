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
from oslo_log import log as logging
from requests.exceptions import ConnectionError
from taskflow import task

from octavia.certificates.common.auth.barbican_acl import BarbicanACLAuth

from a10_octavia.controller.worker.tasks.decorators import axapi_client_decorator
from a10_octavia.controller.worker.tasks import utils

LOG = logging.getLogger(__name__)


class CheckListenerType(task.Task):
    """Task to check if listener type is TERMINATED_HTTPS"""

    def execute(self, listener):
        if listener.protocol == 'TERMINATED_HTTPS' and listener.tls_certificate_id:
            return True
        else:
            return False


class GetSSLCertData(task.Task):
    """Task to get SSL certificate data from Barbican"""

    def execute(self, loadbalancer, listener):
        cert_data = None
        try:
            barbican_client = BarbicanACLAuth().get_barbican_client(loadbalancer.project_id)
            cert_data = utils.get_cert_data(barbican_client, listener)
            cert_data.template_name = listener.id
            LOG.debug("Successfully received barbican data for listener: %s", listener.id)
        except (acos_errors.ACOSException, ConnectionError) as e:
            LOG.exception("Failed to get barbican data for listener: %s", listener.id)
            raise e
        return cert_data


class SSLCertCreate(task.Task):
    """Task to create an SSL certificate"""

    @axapi_client_decorator
    def execute(self, cert_data, vthunder, certificate_type="pem"):
        try:
            if self.axapi_client.file.ssl_cert.exists(file=cert_data.cert_filename):
                self.axapi_client.file.ssl_cert.update(file=cert_data.cert_filename,
                                                       cert=cert_data.cert_content,
                                                       size=len(cert_data.cert_content),
                                                       action="import",
                                                       certificate_type=certificate_type)
            else:
                self.axapi_client.file.ssl_cert.create(file=cert_data.cert_filename,
                                                       cert=cert_data.cert_content,
                                                       size=len(cert_data.cert_content),
                                                       action="import",
                                                       certificate_type=certificate_type)
            LOG.debug("Successfully created SSL certificate: %s", cert_data.cert_filename)
        except (acos_errors.ACOSException, ConnectionError) as e:
            LOG.exception("Failed to create SSL certificate: %s", cert_data.cert_filename)
            raise e

    @axapi_client_decorator
    def revert(self, cert_data, vthunder, *args, **kwargs):
        try:
            LOG.warning("Reverting creation of SSL certificate: %s", cert_data.cert_filename)
            self.axapi_client.file.ssl_cert.delete(private_key=cert_data.key_filename,
                                                   cert_name=cert_data.cert_filename)
        except ConnectionError:
            LOG.exception(
                "Failed to connect A10 Thunder device: %s", vthunder.ip_address)
        except Exception as e:
            LOG.exception("Failed to revert creation of SSL certificate: %s due to %s",
                          cert_data.cert_filename, str(e))


class SSLKeyCreate(task.Task):
    """Task to create an SSL Key"""

    @axapi_client_decorator
    def execute(self, cert_data, vthunder):
        try:
            if self.axapi_client.file.ssl_key.exists(file=cert_data.key_filename):
                self.axapi_client.file.ssl_key.update(file=cert_data.key_filename,
                                                      cert=cert_data.key_content,
                                                      size=len(cert_data.key_content),
                                                      action="import")
            else:
                self.axapi_client.file.ssl_key.create(file=cert_data.key_filename,
                                                      cert=cert_data.key_content,
                                                      size=len(cert_data.key_content),
                                                      action="import")
            LOG.debug("Successfully created SSL key: %s", cert_data.key_filename)
        except (acos_errors.ACOSException, ConnectionError) as e:
            LOG.exception("Failed to create SSL key: %s", cert_data.key_filename)
            raise e

    @axapi_client_decorator
    def revert(self, cert_data, vthunder, *args, **kwargs):
        try:
            LOG.warning("Reverting creation of SSL key: %s", cert_data.key_filename)
            self.axapi_client.file.ssl_key.delete(private_key=cert_data.key_filename)
        except ConnectionError:
            LOG.exception(
                "Failed to connect A10 Thunder device: %s", vthunder.ip_address)
        except Exception as e:
            LOG.exception("Failed to revert creation of SSL key: %s due to %s",
                          cert_data.key_filename, str(e))


class ClientSSLTemplateCreate(task.Task):
    """Task to create a client ssl template for a listener"""

    @axapi_client_decorator
    def execute(self, cert_data, vthunder):
        try:
            if self.axapi_client.slb.template.client_ssl.exists(name=cert_data.template_name):
                self.axapi_client.slb.template.client_ssl.update(name=cert_data.template_name,
                                                                 cert=cert_data.cert_filename,
                                                                 key=cert_data.key_filename,
                                                                 passphrase=cert_data.key_pass)
            else:
                self.axapi_client.slb.template.client_ssl.create(name=cert_data.template_name,
                                                                 cert=cert_data.cert_filename,
                                                                 key=cert_data.key_filename,
                                                                 passphrase=cert_data.key_pass)
            LOG.debug("Successfully created SSL template: %s", cert_data.template_name)
        except (acos_errors.ACOSException, ConnectionError) as e:
            LOG.exception("Failed to create SSL template: %s", cert_data.template_name)
            raise e

    @axapi_client_decorator
    def revert(self, cert_data, vthunder, *args, **kwargs):
        try:
            LOG.warning("Reverting creation of SSL template: %s", cert_data.template_name)
            self.axapi_client.slb.template.client_ssl.delete(name=cert_data.template_name)
        except ConnectionError:
            LOG.exception(
                "Failed to connect A10 Thunder device: %s", vthunder.ip_address)
        except Exception as e:
            LOG.exception("Failed to revert creation of SSL template: %s due to %s",
                          cert_data.template_name, str(e))


class SSLCertUpdate(task.Task):
    """Task to update an SSL certificate"""

    @axapi_client_decorator
    def execute(self, cert_data, vthunder, action="import", certificate_type="pem"):
        try:
            if self.axapi_client.file.ssl_cert.exists(file=cert_data.cert_filename):
                self.axapi_client.file.ssl_cert.update(file=cert_data.cert_filename,
                                                       cert=cert_data.cert_content,
                                                       size=len(cert_data.cert_content),
                                                       action=action,
                                                       certificate_type=certificate_type)
                LOG.debug("Successfully updated SSL certificate: %s", cert_data.cert_filename)
        except (acos_errors.ACOSException, ConnectionError) as e:
            LOG.exception("Failed to update SSL certificate: %s", cert_data.cert_filename)
            raise e


class SSLKeyUpdate(task.Task):
    """Task to update an SSL Key"""

    @axapi_client_decorator
    def execute(self, cert_data, vthunder, action="import"):
        try:
            if self.axapi_client.file.ssl_key.exists(file=cert_data.key_filename):
                self.axapi_client.file.ssl_key.update(file=cert_data.key_filename,
                                                      cert=cert_data.key_content,
                                                      size=len(cert_data.key_content),
                                                      action=action)
                LOG.debug("Successfully updated SSL key: %s", cert_data.key_filename)
        except (acos_errors.ACOSException, ConnectionError) as e:
            LOG.exception("Failed to update SSL key: %s", cert_data.key_filename)
            raise e


class ClientSSLTemplateUpdate(task.Task):
    """Task to update a client ssl template"""

    @axapi_client_decorator
    def execute(self, cert_data, vthunder):
        try:
            if self.axapi_client.slb.template.client_ssl.exists(name=cert_data.template_name):
                self.axapi_client.slb.template.client_ssl.update(name=cert_data.template_name,
                                                                 cert=cert_data.cert_filename,
                                                                 key=cert_data.key_filename,
                                                                 passphrase=cert_data.key_pass)
                LOG.debug("Successfully updated SSL template: %s", cert_data.template_name)
        except (acos_errors.ACOSException, ConnectionError) as e:
            LOG.exception("Failed to update SSL template: %s", cert_data.template_name)
            raise e


class SSLCertDelete(task.Task):
    """Task to delete an SSL certificate"""

    @axapi_client_decorator
    def execute(self, cert_data, vthunder):
        try:
            if self.axapi_client.file.ssl_cert.exists(file=cert_data.cert_filename):
                self.axapi_client.file.ssl_cert.delete(private_key=cert_data.key_filename,
                                                       cert_name=cert_data.cert_filename)
                LOG.debug("Successfully deleted SSL certificate: %s", cert_data.cert_filename)
        except acos_errors.Exists as e:
            LOG.warning("Failed to delete SSL cert as its being used in another place")
            LOG.exception(str(e))
        except (acos_errors.ACOSException, ConnectionError) as e:
            LOG.exception("Failed to delete SSL certificate: %s", cert_data.cert_filename)
            raise e


class SSLKeyDelete(task.Task):
    """Task to delete an SSL Key"""

    @axapi_client_decorator
    def execute(self, cert_data, vthunder):
        try:
            if self.axapi_client.file.ssl_key.exists(file=cert_data.key_filename):
                self.axapi_client.file.ssl_key.delete(private_key=cert_data.key_filename)
                LOG.debug("Successfully deleted SSL key: %s", cert_data.key_filename)
        except acos_errors.Exists as e:
            LOG.warning("Failed to delete SSL cert as its being used in another place")
            LOG.exception(str(e))
        except (acos_errors.ACOSException, ConnectionError) as e:
            LOG.exception("Failed to delete SSL key: %s", cert_data.key_filename)
            raise e


class ClientSSLTemplateDelete(task.Task):
    """Task to delete a client ssl template for a listener"""

    @axapi_client_decorator
    def execute(self, cert_data, vthunder):
        try:
            if self.axapi_client.slb.template.client_ssl.exists(name=cert_data.template_name):
                self.axapi_client.slb.template.client_ssl.delete(name=cert_data.template_name)
                LOG.debug("Successfully deleted SSL template: %s", cert_data.template_name)
        except (acos_errors.ACOSException, ConnectionError) as e:
            LOG.exception("Failed to delete SSL template: %s", cert_data.template_name)
            raise e
