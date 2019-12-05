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
from a10_octavia.common import openstack_mappings
from a10_octavia.controller.worker.tasks.common import BaseVThunderTask
import acos_client

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class PoolParent(object):

    def set(self, set_method, pool, vthunder):
        args = {'service_group': self.meta(pool, 'service_group', {})}
        PROTOCOL_MAP = {
                        'TCP' : 'TCP',
                        'UDP' : 'UDP',
                        'HTTP' : 'TCP',
                        'HTTPS' : 'TCP',
                        'TERMINATED_HTTPS' : 'TCP',
                        'PROXY' : 'TCP'
                       }
        try:
            conf_templates = self.readConf('SERVICE_GROUP', 'templates').strip('"')
            service_group_temp = {}
            service_group_temp['template-server'] = conf_templates
        except:
            service_group_temp = None

        try:
            c = self.client_factory(vthunder)
            protocol = openstack_mappings.service_group_protocol(c, pool.protocol)
            lb_method = openstack_mappings.service_group_lb_method(c, pool.lb_algorithm)
            set_method(pool.id,
                       protocol=protocol,
                       lb_method=lb_method,
                       service_group_templates=service_group_temp,
                       axapi_args=args)
            LOG.info("Pool created successfully.")
        except Exception as e:
            LOG.error(str(e))


class PoolCreate(BaseVThunderTask, PoolParent):
    """Task to update amphora with all specified listeners' configurations."""

    def execute(self, pool, vthunder):
        """Execute create pool for an amphora."""
        c = self.client_factory(vthunder)
        PoolParent.set(self, c.slb.service_group.create, pool, vthunder)


class PoolDelete(BaseVThunderTask):
    """Task to update amphora with all specified listeners' configurations."""

    def execute(self, pool, vthunder):
        """Execute create pool for an amphora."""
        try:
            axapi_version = acos_client.AXAPI_21 if vthunder.axapi_version == 21 else acos_client.AXAPI_30
            c = self.client_factory(vthunder)
            # need to put algorithm logic
            c.slb.service_group.delete(pool.id)
            LOG.info("Pool deleted successfully.")
        except Exception as e:
            LOG.error(str(e))


class PoolUpdate(BaseVThunderTask, PoolParent):

    def execute(self, pool, vthunder):
        """Execute update pool for an amphora."""
        c = self.client_factory(vthunder)
        PoolParent.set(self, c.slb.service_group.update, pool, vthunder)
