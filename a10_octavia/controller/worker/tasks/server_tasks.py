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

from a10_octavia.common import openstack_mappings
from a10_octavia.controller.worker.tasks.decorators import axapi_client_decorator
from a10_octavia.controller.worker.tasks import utils


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class MemberCreate(task.Task):
    """Task to create a member and associate to pool"""

    @axapi_client_decorator
    def execute(self, member, vthunder, pool, member_count_ip, flavor=None):
        server_name = '{}_{}'.format(member.project_id[:5], member.ip_address.replace('.', '_'))
        server_args = utils.meta(member, 'server', {})
        server_args = utils.dash_to_underscore(server_args)
        server_args['conn_limit'] = CONF.server.conn_limit
        server_args['conn_resume'] = CONF.server.conn_resume
        # overwrite options from flavor
        if flavor:
            server_flavor = flavor.get('server')
            if server_flavor:
                name_exprs = server_flavor.get('name_expressions')
                parsed_exprs = utils.parse_name_expressions(member.name, name_exprs)
                server_flavor.pop('name_expressions', None)
                server_args.update(server_flavor)
                server_args.update(parsed_exprs)
        server_args = {'server': server_args}

        server_temp = {}
        template_server = CONF.server.template_server
        if template_server and template_server.lower() != 'none':
            if CONF.a10_global.use_shared_for_template_lookup:
                LOG.warning('Shared partition template lookup for `[server]`'
                            ' is not supported on template `template-server`')
            server_temp = {'template-server': template_server}

        if not member.enabled:
            status = False
        else:
            status = True

        try:
            try:
                self.axapi_client.slb.server.create(server_name, member.ip_address, status=status,
                                                    server_templates=server_temp,
                                                    **server_args)
                LOG.debug("Successfully created member: %s", member.id)
            except (acos_errors.Exists, acos_errors.AddressSpecifiedIsInUse):
                self.axapi_client.slb.server.update(server_name, member.ip_address, status=status,
                                                    server_templates=server_temp,
                                                    **server_args)
        except (acos_errors.ACOSException, exceptions.ConnectionError) as e:
            LOG.exception("Failed to create member: %s", member.id)
            raise e

        try:
            self.axapi_client.slb.service_group.member.create(
                pool.id, server_name, member.protocol_port)
            LOG.debug("Successfully associated member %s to pool %s",
                      member.id, pool.id)
        except (acos_errors.ACOSException, exceptions.ConnectionError) as e:
            LOG.exception("Failed to associate member %s to pool %s",
                          member.id, pool.id)
            raise e

    @axapi_client_decorator
    def revert(self, member, vthunder, pool, member_count_ip, *args, **kwargs):
        if member_count_ip > 1:
            return
        server_name = '{}_{}'.format(member.project_id[:5], member.ip_address.replace('.', '_'))
        try:
            LOG.warning("Reverting creation of member: %s for pool: %s",
                        member.id, pool.id)
            self.axapi_client.slb.server.delete(server_name)
        except exceptions.ConnectionError:
            LOG.exception("Failed to connect A10 Thunder device: %s", vthunder.ip_address)
        except Exception as e:
            LOG.exception("Failed to revert creation of member %s for pool %s due to %s",
                          member.id, pool.id, str(e))


class MemberDelete(task.Task):
    """Task to delete member"""

    @axapi_client_decorator
    def execute(self, member, vthunder, pool, member_count_ip, member_count_ip_port_protocol):
        server_name = '{}_{}'.format(member.project_id[:5], member.ip_address.replace('.', '_'))
        try:
            self.axapi_client.slb.service_group.member.delete(
                pool.id, server_name, member.protocol_port)
            LOG.debug("Successfully dissociated member %s from pool %s", member.id, pool.id)
        except (acos_errors.ACOSException, exceptions.ConnectionError) as e:
            LOG.exception("Failed to dissociate member %s from pool %s",
                          member.id, pool.id)
            raise e

        try:
            if member_count_ip <= 1:
                self.axapi_client.slb.server.delete(server_name)
                LOG.debug("Successfully deleted member %s from pool %s", member.id, pool.id)
            elif member_count_ip_port_protocol <= 1:
                protocol = openstack_mappings.service_group_protocol(
                    self.axapi_client, pool.protocol)
                self.axapi_client.slb.server.port.delete(server_name, member.protocol_port,
                                                         protocol)
                LOG.debug("Successfully deleted port for member %s from pool %s",
                          member.id, pool.id)
        except (acos_errors.ACOSException, exceptions.ConnectionError) as e:
            LOG.exception("Failed to delete member/port: %s", member.id)
            raise e


class MemberUpdate(task.Task):
    """Task to update member"""

    @axapi_client_decorator
    def execute(self, member, vthunder, pool, flavor=None):
        server_name = '{}_{}'.format(member.project_id[:5], member.ip_address.replace('.', '_'))
        server_args = utils.meta(member, 'server', {})
        server_args = utils.dash_to_underscore(server_args)
        server_args['conn_limit'] = CONF.server.conn_limit
        server_args['conn_resume'] = CONF.server.conn_resume
        # overwrite options from flavor
        if flavor:
            server_flavor = flavor.get('server')
            if server_flavor:
                name_exprs = server_flavor.get('name_expressions')
                parsed_exprs = utils.parse_name_expressions(member.name, name_exprs)
                server_flavor.pop('name_expressions', None)
                server_args.update(server_flavor)
                server_args.update(parsed_exprs)
        server_args = {'server': server_args}

        template_server = CONF.server.template_server
        if template_server and template_server.lower() == 'none':
            template_server = None
        server_temp = {'template-server': template_server}

        if not member.enabled:
            status = False
        else:
            status = True

        try:
            port_list = self.axapi_client.slb.server.get(server_name)['server'].get('port-list')
            self.axapi_client.slb.server.replace(server_name, member.ip_address, status=status,
                                                 server_templates=server_temp,
                                                 port_list=port_list,
                                                 **server_args)
            LOG.debug("Successfully updated member: %s", member.id)
        except (acos_errors.ACOSException, exceptions.ConnectionError) as e:
            LOG.exception("Failed to update member: %s", member.id)
            raise e


class MemberDeletePool(task.Task):
    """Task to delete member"""

    @axapi_client_decorator
    def execute(self, member, vthunder, pool, pool_count_ip, member_count_ip_port_protocol):
        try:
            server_name = '{}_{}'.format(member.project_id[:5], member.ip_address.replace('.', '_'))
            if pool_count_ip <= 1:
                self.axapi_client.slb.server.delete(server_name)
                LOG.debug("Successfully deleted member %s from pool %s", member.id, pool.id)
            elif member_count_ip_port_protocol <= 1:
                protocol = openstack_mappings.service_group_protocol(
                    self.axapi_client, pool.protocol)
                self.axapi_client.slb.server.port.delete(server_name, member.protocol_port,
                                                         protocol)
                LOG.debug("Successfully deleted port for member %s from pool %s",
                          member.id, pool.id)
        except acos_errors.ACOSException:
            pass
        except exceptions.ConnectionError as e:
            LOG.exception("Failed to delete member/port: %s", member.id)
            raise e


class MemberFindNatPool(task.Task):

    @axapi_client_decorator
    def execute(self, member, vthunder, pool, flavor=None):
        if flavor is None:
            return

        pool_flavor = flavor.get('nat_pool')
        pools_flavor = flavor.get('nat_pool_list')
        if pool_flavor or pools_flavor:
            for listener in pool.listeners:
                vport = self.axapi_client.slb.virtual_server.vport.get(pool.load_balancer.id,
                                                                       listener.id,
                                                                       listener.protocol,
                                                                       listener.protocol_port)
                if vport and 'port' in vport and 'pool' in vport['port']:
                    if pool_flavor and vport['port']['pool'] == pool_flavor['pool_name']:
                        return pool_flavor
                    for flavor in (pools_flavor or []):
                        if vport['port']['pool'] == flavor['pool_name']:
                            return flavor
