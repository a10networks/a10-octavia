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


from oslo_log import log as logging
from oslo_config import cfg
from a10_octavia.controller.worker.tasks.common import BaseVThunderTask

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class MemberCreate(BaseVThunderTask):
    """ Task to create a member and associate to pool """

    def execute(self, member, vthunder, pool):
        """ Execute create member """
        server_args = self.meta(member, 'server', {})
        server_args['conn-limit'] = CONF.server.conn_limit
        server_args['conn-resume'] = CONF.server.conn_resume
        server_args = {'server': server_args}
        server_temp = {}
        server_temp['template-server'] = CONF.server.template_server
        if not member.enabled:
            status = False
        else:
            status = True
        c = self.client_factory(vthunder)

        try:
            c.slb.server.create(member.id, member.ip_address, status=status,
                                server_templates=server_temp,
                                axapi_args=server_args)
            LOG.debug("Member created successfully: %s", member.id)
        except Exception as e:
            LOG.exception("Failed to create member: %s", str(e))
            raise

        try:
            c.slb.service_group.member.create(
                pool.id, member.id, member.protocol_port)
            LOG.debug("Member %s associated to pool %s successfully",
                      member.id, pool.id)
        except Exception as e:
            LOG.exception("Failed to associate member to pool: %s", str(e))
            raise

    def revert(self, member, vthunder, pool, *args, **kwargs):
        c = self.client_factory(vthunder)
        try:
            c.slb.service_group.member.delete(
                pool.id, member.id, member.protocol_port)
        except Exception as e:
            LOG.exception("Failed to revert create pool: %s", str(e))

        try:
            c.slb.server.delete(member.id)
        except Exception as e:
            LOG.exception("Failed to revert create member: %s", str(e))


class MemberDelete(BaseVThunderTask):
    """ Task to delete member """

    def execute(self, member, vthunder, pool):
        """ Execute delete member """
        c = self.client_factory(vthunder)
        try:
            c.slb.service_group.member.delete(
                pool.id, member.id, member.protocol_port)
            LOG.debug("Member %s is dissociated from pool %s successfully.", member.id, pool.id)
            c.slb.server.delete(member.id)
            LOG.debug("Member %s is deleted successfully.", member.id)
        except Exception as e:
            LOG.warning("Failed to delete member: %s", str(e))


class MemberUpdate(BaseVThunderTask):
    """ Task to update member """

    def execute(self, member, vthunder, pool):
        """Execute update member """
        server_args = self.meta(member, 'server', {})
        server_args['conn-limit'] = CONF.server.conn_limit
        server_args['conn-resume'] = CONF.server.conn_resume
        server_args = {'server': server_args}
        server_temp = {}
        server_temp['template-server'] = CONF.server.template_server
        if not member.enabled:
            status = False
        else:
            status = True
        c = self.client_factory(vthunder)

        try:
            c.slb.server.update(member.id, member.ip_address, status=status,
                                server_templates=server_temp,
                                axapi_args=server_args)
            LOG.debug("Member updated successfully: %s", member.id)
        except Exception as e:
            LOG.exception("Failed to update member: %s", str(e))
            raise

    def revert(self, member, vthunder, pool, *args, **kwargs):
        LOG.warning("Failed to revert update member: %s", member.id)
