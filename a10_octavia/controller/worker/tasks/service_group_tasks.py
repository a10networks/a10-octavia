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

import acos_client.errors as acos_errors

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
            LOG.debug("Successfully created pool: %s", pool.id)
            return pool
        except (acos_errors.ACOSException, ConnectionError) as e:
            LOG.exception("Failed to create pool: %s", pool.id)
            raise e

    @axapi_client_decorator
    def revert(self, pool, vthunder, *args, **kwargs):
        LOG.warning("Reverting creation of pool: %s", pool.id)
        try:
            self.axapi_client.slb.service_group.delete(pool.id)
        except ConnectionError:
            LOG.exception("Failed to connect A10 Thunder device: %s", vthunder.ip_address)
        except Exception as e:
            LOG.exception("Failed to revert creation of pool: %s due to: %s",
                          pool.id, str(e))


class PoolDelete(task.Task):
    """Task to delete pool"""

    @axapi_client_decorator
    def execute(self, pool, vthunder):
        try:
            self.axapi_client.slb.service_group.delete(pool.id)
            LOG.debug("Successfully deleted pool: %s", pool.id)
        except (acos_errors.ACOSException, ConnectionError) as e:
            LOG.exception("Failed to delete pool: %s", pool.id)
            raise e


class PoolUpdate(PoolParent, task.Task):
    """Task to update pool"""

    @axapi_client_decorator
    def execute(self, pool, vthunder, update_dict):
        pool.update(update_dict)
        try:
            self.set(self.axapi_client.slb.service_group.update, pool)
            LOG.debug("Successfully updated pool: %s", pool.id)
        except (acos_errors.ACOSException, ConnectionError) as e:
            LOG.exception("Failed to update pool: %s", pool.id)
            raise e
