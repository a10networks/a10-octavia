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


import logging
from taskflow import task

from octavia.certificates.common.auth.barbican_acl import BarbicanACLAuth

from a10_octavia.controller.worker.tasks.decorators import axapi_client_decorator
from a10_octavia.controller.worker.tasks import utils

LOG = logging.getLogger(__name__)


class SSLCertCreate(task.Task):
    """Task to create an SSL certificate"""
    @axapi_client_decorator
    def execute(self, loadbalancer, listener, vthunder, certificate_type="pem"):
        barbican_client = BarbicanACLAuth().get_barbican_client(loadbalancer.project_id)
        cert_data = utils.get_cert_data(barbican_client, listener)
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
        except Exception as e:
            LOG.exception("Failed to create SSL certificate: %s", str(e))
            raise e
        return cert_data

    @axapi_client_decorator
    def revert(self, loadbalancer, listener, vthunder, *args, **kwargs):
        barbican_client = BarbicanACLAuth().get_barbican_client(loadbalancer.project_id)
        cert_data = utils.get_cert_data(barbican_client, listener)
        try:
            self.axapi_client.file.ssl_cert.delete(file=cert_data.cert_filename)
            LOG.debug("Reverted SSLCertCreate: %s", cert_data.cert_filename)
        except Exception:
            pass


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
        except Exception as e:
            LOG.exception("Failed to create SSL key: %s", str(e))
            raise e

    @axapi_client_decorator
    def revert(self, cert_data, vthunder, *args, **kwargs):
        try:
            self.axapi_client.file.ssl_key.delete(file=cert_data.key_filename)
            LOG.debug("Reverted SSLKeyCreate: %s", cert_data.key_filename)
        except Exception:
            pass


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
        except Exception as e:
            LOG.exception("Failed to create client SSL template: %s", str(e))
            raise e

    @axapi_client_decorator
    def revert(self, cert_data, vthunder, *args, **kwargs):
        try:
            self.axapi_client.slb.template.client_ssl.delete(name=cert_data.template_name)
            LOG.debug("Reverted ClientSSLTemplateCreate: %s", cert_data.template_name)
        except Exception:
            pass


class SSLCertUpdate(task.Task):
    """Task to update an SSL certificate"""
    @axapi_client_decorator
    def execute(self, loadbalancer, listener, vthunder, action="import", certificate_type="pem"):
        barbican_client = BarbicanACLAuth().get_barbican_client(loadbalancer.project_id)
        cert_data = utils.get_cert_data(barbican_client, listener)
        try:
            if self.axapi_client.file.ssl_cert.exists(file=cert_data.cert_filename):
                self.axapi_client.file.ssl_cert.update(file=cert_data.cert_filename,
                                                       cert=cert_data.cert_content,
                                                       size=len(cert_data.cert_content),
                                                       action=action,
                                                       certificate_type=certificate_type)
                LOG.debug("SSL certificate updated successfully: %s", cert_data.cert_filename)
        except Exception as e:
            LOG.warning("Failed to update SSL Certificate: %s", str(e))
        return cert_data


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
                LOG.debug("SSL Key updated successfully: %s", cert_data.key_filename)
        except Exception as e:
            LOG.warning("Failed to update SSL Key: %s", str(e))


class ClientSSLTemplateUpdate(task.Task):
    """Task to update a client ssl template for a listener"""
    @axapi_client_decorator
    def execute(self, cert_data, vthunder):
        try:
            if self.axapi_client.slb.template.client_ssl.exists(name=cert_data.template_name):
                self.axapi_client.slb.template.client_ssl.update(name=cert_data.template_name,
                                                                 cert=cert_data.cert_filename,
                                                                 key=cert_data.key_filename,
                                                                 passphrase=cert_data.key_pass)
                LOG.debug("Client SSL Template updated successfully: %s",
                          cert_data.template_name)
        except Exception as e:
            LOG.warning("Failed to update Client SSL Template: %s", str(e))


class SSLCertDelete(task.Task):
    """Task to delete an SSL certificate"""
    @axapi_client_decorator
    def execute(self, loadbalancer, listener, vthunder):
        barbican_client = BarbicanACLAuth().get_barbican_client(loadbalancer.project_id)
        cert_data = utils.get_cert_data(barbican_client, listener)
        try:
            if self.axapi_client.file.ssl_cert.exists(file=cert_data.cert_filename):
                self.axapi_client.file.ssl_cert.delete(file=cert_data.cert_filename)
                LOG.debug("SSL certificate deleted successfully: %s", cert_data.cert_filename)
        except Exception as e:
            LOG.warning("Failed to delete SSL Certificate: %s", str(e))
        return cert_data


class SSLKeyDelete(task.Task):
    """Task to delete an SSL Key"""
    @axapi_client_decorator
    def execute(self, cert_data, vthunder):
        try:
            if self.axapi_client.file.ssl_key.exists(file=cert_data.key_filename):
                self.axapi_client.file.ssl_key.delete(file=cert_data.key_filename)
                LOG.debug("SSL Key deleted successfully: %s", cert_data.key_filename)
        except Exception as e:
            LOG.warning("Failed to delete SSL Key: %s", str(e))


class ClientSSLTemplateDelete(task.Task):
    """Task to delete a client ssl template for a listener"""
    @axapi_client_decorator
    def execute(self, cert_data, vthunder):
        try:
            if self.axapi_client.slb.template.client_ssl.exists(name=cert_data.template_name):
                self.axapi_client.slb.template.client_ssl.delete(name=cert_data.template_name)
                LOG.debug("Client SSL Template deleted successfully: %s",
                          cert_data.template_name)
        except Exception as e:
            LOG.warning("Failed to delete Client SSL Template: %s", str(e))
