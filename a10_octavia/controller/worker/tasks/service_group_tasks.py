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
from requests.exceptions import ConnectionError
from taskflow import task

from octavia.common import constants
from octavia.controller.worker.v1.tasks import lifecycle_tasks

import acos_client.errors as acos_errors

from a10_octavia.common import a10constants
from a10_octavia.common import openstack_mappings
from a10_octavia.controller.worker.tasks.decorators import axapi_client_decorator
from a10_octavia.controller.worker.tasks.decorators import axapi_client_decorator_for_revert
from a10_octavia.controller.worker.tasks import utils

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class PoolParent(object):
    def set(self, set_method, pool, vthunder, flavor=None, **kwargs):
        pool_args = {'service_group': utils.meta(pool, 'service_group', {})}

        device_templates = self.axapi_client.slb.template.templates.get()

        service_group_temp = {}
        template_server = CONF.service_group.template_server
        if template_server and template_server.lower() != 'none':
            if CONF.a10_global.use_shared_for_template_lookup:
                LOG.warning('Shared partition template lookup for `[service_group]`'
                            ' is not supported on template `template-server`')
            service_group_temp['template-server'] = template_server

        template_port = CONF.service_group.template_port
        if template_port and template_port.lower() != 'none':
            if CONF.a10_global.use_shared_for_template_lookup:
                LOG.warning('Shared partition template lookup for `[service_group]`'
                            ' is not supported on template `template-port`')
            service_group_temp['template-port'] = template_port

        template_policy = CONF.service_group.template_policy
        if template_policy and template_policy.lower() != 'none':
            template_key = 'template-policy'
            if vthunder.partition_name != "shared":
                if CONF.a10_global.use_shared_for_template_lookup:
                    template_key = utils.shared_template_modifier(template_key,
                                                                  template_policy,
                                                                  device_templates)
            service_group_temp[template_key] = template_policy

        protocol = openstack_mappings.service_group_protocol(
            self.axapi_client, pool.protocol)
        lb_method = openstack_mappings.service_group_lb_method(
            self.axapi_client, pool.lb_algorithm)

        # Handle options from flavor
        if flavor:
            pool_flavor = flavor.get('service_group')
            if pool_flavor:
                name_exprs = pool_flavor.get('name_expressions')
                parsed_exprs = utils.parse_name_expressions(pool.name, name_exprs)
                pool_flavor.pop('name_expressions', None)
                pool_args['service_group'].update(pool_flavor)
                pool_args['service_group'].update(parsed_exprs)

        set_method(pool.id,
                   protocol=protocol,
                   lb_method=lb_method,
                   service_group_templates=service_group_temp,
                   mem_list=kwargs.get('mem_list'),
                   hm_name=kwargs.get('health_monitor'),
                   **pool_args)

    def get_proxy_name(self, pool):
        name = a10constants.PROXY_PROTOCPL_TEMPLATE_NAME
        version = a10constants.PROXY_PROTOCPL_V1
        if pool.protocol != constants.PROTOCOL_PROXY:
            name = a10constants.PROXY_PROTOCPL_V2_TEMPLATE_NAME
            version = a10constants.PROXY_PROTOCPL_V2

        return name, version

    def set_proxy(self, pool, listener, **kwargs):
        proxy_aflex = """ when CLIENT_ACCEPTED {
        set sip [IP::remote_addr]
        set sport [TCP::remote_port]
        set dip [IP::local_addr]
        set dport [TCP::local_port]
        set proxyheader "PROXY TCP4 $sip $dip $sport $dport\\r\\n"
}

when SERVER_CONNECTED {
        TCP::respond $proxyheader
}"""

        if utils.proxy_protocol_use_aflex(listener, pool):
            size = len(proxy_aflex.encode('utf-8'))
            self.axapi_client.slb.aflex_policy.create(
                file=a10constants.PROXY_PROTOCPL_AFLEX_NAME,
                script=proxy_aflex, size=size, action="import")
        else:
            name, version = self.get_proxy_name(pool)
            if self.axapi_client.slb.tcp_proxy.exists(name):
                return

            self.axapi_client.slb.tcp_proxy.create(name, version)

    def delete_proxy(self, pool, listener, proxy_pool_count):
        if proxy_pool_count is None or proxy_pool_count > 0:
            return

        if utils.proxy_protocol_use_aflex(listener, pool):
            self.axapi_client.slb.aflex_policy.delete(a10constants.PROXY_PROTOCPL_AFLEX_NAME)
        else:
            name, version = self.get_proxy_name(pool)
            self.axapi_client.slb.tcp_proxy.delete(name)


class PoolCreate(PoolParent, task.Task):
    """Task to create pool"""

    @axapi_client_decorator
    def execute(self, pool, vthunder, flavor=None, listener=None):
        try:
            if utils.is_proxy_protocol_pool(pool) is True:
                self.set_proxy(pool, listener)
        except (acos_errors.ACOSException, ConnectionError) as e:
            LOG.exception("Failed to create tcp-proxy/aflex for PROXY protocol pood: %s", pool.id)
            raise e

        try:
            self.set(self.axapi_client.slb.service_group.create, pool, vthunder, flavor)
            LOG.debug("Successfully created pool: %s", pool.id)
            return pool
        except (acos_errors.ACOSException, ConnectionError) as e:
            LOG.exception("Failed to create pool: %s", pool.id)
            raise e

    @axapi_client_decorator_for_revert
    def revert(self, pool, vthunder, flavor=None, listener=None, *args, **kwargs):
        LOG.warning("Reverting creation of pool: %s", pool.id)
        try:
            self.axapi_client.slb.service_group.delete(pool.id)
        except ConnectionError:
            LOG.exception(
                "Failed to connect A10 Thunder device: %s", vthunder.ip_address)
        except Exception as e:
            LOG.exception("Failed to revert creation of pool: %s due to: %s",
                          pool.id, str(e))


class PoolDelete(PoolParent, task.Task):
    """Task to delete pool"""

    @axapi_client_decorator
    def execute(self, pool, vthunder, listener=None, proxy_pool_count=None):
        try:
            if utils.is_proxy_protocol_pool(pool) is True:
                self.delete_proxy(pool, listener, proxy_pool_count)
        except (acos_errors.ACOSException, ConnectionError):
            LOG.exception("Failed to delete tcp-proxy/aflex for PROXY protocol pood: %s", pool.id)

        try:
            self.axapi_client.slb.service_group.delete(pool.id)
            LOG.debug("Successfully deleted pool: %s", pool.id)
        except (acos_errors.ACOSException, ConnectionError) as e:
            LOG.exception("Failed to delete pool: %s", pool.id)
            raise e


class PoolUpdate(PoolParent, task.Task):
    """Task to update pool"""

    @axapi_client_decorator
    def execute(self, pool, vthunder, update_dict={}, flavor=None):
        pool.__dict__.update(update_dict)
        try:
            service_group = self.axapi_client.slb.service_group.get(
                pool.id)['service-group']
            mem_list = service_group.get('member-list')
            health_monitor = service_group.get('health-check')
            self.set(self.axapi_client.slb.service_group.replace, pool, vthunder,
                     mem_list=mem_list, health_monitor=health_monitor, flavor=flavor)
            LOG.debug("Successfully updated pool: %s", pool.id)
        except (acos_errors.ACOSException, ConnectionError) as e:
            LOG.exception("Failed to update pool: %s", pool.id)
            raise e


class PoolToErrorOnRevertTask(lifecycle_tasks.BaseLifecycleTask):
    """Task to set a pool to ERROR on revert."""

    def execute(self, pool):
        pass

    def revert(self, pool, *args, **kwargs):
        self.task_utils.mark_pool_prov_status_error(pool.id)
