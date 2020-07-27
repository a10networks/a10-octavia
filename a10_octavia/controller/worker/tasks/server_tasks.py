#    Copyright 2019, A10 Networks
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

from oslo_config import cfg
from oslo_log import log as logging
from requests import exceptions
from taskflow import task

import acos_client.errors as acos_errors

from a10_octavia.controller.worker.tasks.decorators import axapi_client_decorator
from a10_octavia.controller.worker.tasks import utils


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class MemberCreate(task.Task):
    """Task to create a member and associate to pool"""

    @axapi_client_decorator
    def execute(self, member, vthunder, pool):
        server_args = utils.meta(member, 'server', {})
        server_args['conn-limit'] = CONF.server.conn_limit
        server_args['conn-resume'] = CONF.server.conn_resume
        server_args = {'server': server_args}
        server_temp = {}
        server_temp['template-server'] = CONF.server.template_server
        if not member.enabled:
            status = False
        else:
            status = True

        try:
            self.axapi_client.slb.server.create(member.id, member.ip_address, status=status,
                                                server_templates=server_temp,
                                                axapi_args=server_args)
            LOG.debug("Successfully created member: %s", member.id)
        except (acos_errors.ACOSException, exceptions.ConnectionError) as e:
            LOG.exception("Failed to create member: %s", member.id)
            raise e

        try:
            self.axapi_client.slb.service_group.member.create(
                pool.id, member.id, member.protocol_port)
            LOG.debug("Successfully associated member %s to pool %s",
                      member.id, pool.id)
        except (acos_errors.ACOSException, exceptions.ConnectionError) as e:
            LOG.exception("Failed to associate member %s to pool %s",
                          member.id, pool.id)
            raise e

    @axapi_client_decorator
    def revert(self, member, vthunder, pool, *args, **kwargs):
        try:
            LOG.warning("Reverting creation of member: %s for pool: %s",
                        member.id, pool.id)
            self.axapi_client.slb.server.delete(member.id)
        except exceptions.ConnectionError:
            LOG.exception("Failed to connect A10 Thunder device: %s", vthunder.ip_address)
        except Exception as e:
            LOG.exception("Failed to revert creation of member %s for pool %s due to %s",
                          member.id, pool.id, str(e))


class MemberDelete(task.Task):
    """Task to delete member"""

    @axapi_client_decorator
    def execute(self, member, vthunder, pool):
        try:
            self.axapi_client.slb.service_group.member.delete(
                pool.id, member.id, member.protocol_port)
            LOG.debug("Successfully dissociated member %s from pool %s", member.id, pool.id)
        except (acos_errors.ACOSException, exceptions.ConnectionError) as e:
            LOG.exception("Failed to dissociate member %s from pool %s",
                          member.id, pool.id)
            raise e
        try:
            self.axapi_client.slb.server.delete(member.id)
            LOG.debug("Successfully deleted member %s from pool %s", member.id, pool.id)
        except (acos_errors.ACOSException, exceptions.ConnectionError) as e:
            LOG.exception("Failed to delete member: %s", member.id)
            raise e


class MemberUpdate(task.Task):
    """Task to update member"""

    @axapi_client_decorator
    def execute(self, member, vthunder):
        server_args = utils.meta(member, 'server', {})
        server_args['conn-limit'] = CONF.server.conn_limit
        server_args['conn-resume'] = CONF.server.conn_resume
        server_args = {'server': server_args}
        server_temp = {}
        server_temp['template-server'] = CONF.server.template_server
        if not member.enabled:
            status = False
        else:
            status = True

        try:
            self.axapi_client.slb.server.update(member.id, member.ip_address, status=status,
                                                server_templates=server_temp,
                                                axapi_args=server_args)
            LOG.debug("Successfully updated member: %s", member.id)
        except (acos_errors.ACOSException, exceptions.ConnectionError) as e:
            LOG.exception("Failed to update member: %s", member.id)
            raise e
