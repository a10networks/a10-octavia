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
from taskflow import task

from a10_octavia.common import openstack_mappings
from a10_octavia.controller.worker.tasks.decorators import axapi_client_decorator
from a10_octavia.controller.worker.tasks import utils

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class PoolParent(object):

    def set(self, set_method, pool):

        axapi_args = {'service_group': utils.meta(pool, 'service_group', {})}
        service_group_temp = {}
        service_group_temp['template-server'] = CONF.service_group.template_server
        service_group_temp['template-port'] = CONF.service_group.template_port
        service_group_temp['template-policy'] = CONF.service_group.template_policy
        protocol = openstack_mappings.service_group_protocol(self.axapi_client, pool.protocol)
        lb_method = openstack_mappings.service_group_lb_method(self.axapi_client, pool.lb_algorithm)
        set_method(pool.id,
                   protocol=protocol,
                   lb_method=lb_method,
                   service_group_templates=service_group_temp,
                   axapi_args=axapi_args)


class PoolCreate(PoolParent, task.Task):
    """Task to create pool"""

    @axapi_client_decorator
    def execute(self, pool, vthunder):
        try:
            self.set(self.axapi_client.slb.service_group.create, pool)
            LOG.debug("Pool created successfully: %s", pool.id)
            return pool
        except Exception as e:
            LOG.exception("Failed to create pool: %s", str(e))
            raise

    @axapi_client_decorator
    def revert(self, pool, vthunder, *args, **kwargs):
        try:
            self.axapi_client.slb.service_group.delete(pool.id)
        except Exception as e:
            LOG.warning("Failed to revert create pool: %s", str(e))


class PoolDelete(task.Task):
    """Task to delete pool"""

    @axapi_client_decorator
    def execute(self, pool, vthunder):
        try:
            self.axapi_client.slb.service_group.delete(pool.id)
            LOG.debug("Pool deleted successfully: %s", pool.id)
        except Exception as e:
            LOG.warning("Failed to delete pool: %s", str(e))


class PoolUpdate(PoolParent, task.Task):
    """Task to update pool"""

    @axapi_client_decorator
    def execute(self, pool, vthunder, update_dict):
        pool.__dict__.update(update_dict)
        try:
            self.set(self.axapi_client.slb.service_group.update, pool)
            LOG.debug("Pool updated successfully: %s", pool.id)
        except Exception as e:
            LOG.warning("Failed to update pool: %s", str(e))
