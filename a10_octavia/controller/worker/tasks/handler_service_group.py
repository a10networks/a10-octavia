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
from a10_octavia.controller.worker.tasks import handler_persist
import acos_client

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class PoolParent(object):

    def set(self, set_method, pool, vthunder, old_pool=None):
        try:
            c = self.client_factory(vthunder)
            self._update_session_persistence(pool, old_pool, c)
            args = {'service_group': self.meta(pool, 'service_group', {})}
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

    def _update_session_persistence(self, pool, old_pool, c):
        # didn't exist, does exist, create
        if not old_pool or (not old_pool.session_persistence and pool.session_persistence):
            p = handler_persist.PersistHandler(c,  pool)
            p.create()
            return

        # existed, change, delete and recreate
        if (old_pool.session_persistence and pool.session_persistence and
                old_pool.session_persistence.type != pool.session_persistence.type):
            p = handler_persist.PersistHandler(c, old_pool)
            p.delete()
            p = handler_persist.PersistHandler(c, pool)
            p.create()
            return

        # didn't exist, does exist now, create
        if old_pool.session_persistence and not pool.session_persistence:
            p = handler_persist.PersistHandler(c, pool)
            p.create()
            return

        # didn't exist, doesn't exist
        # did exist, does exist, didn't changen
        return



class PoolCreate(BaseVThunderTask, PoolParent):
    """ Task to create pool """

    def execute(self, pool, vthunder):
        """ Execute create pool """
        c = self.client_factory(vthunder)
        PoolParent.set(self, c.slb.service_group.create, pool, vthunder)


class PoolDelete(BaseVThunderTask):
    """ Task to delete pool """

    def execute(self, pool, vthunder):
        """ Execute delete pool """
        try:
            axapi_version = acos_client.AXAPI_21 if vthunder.axapi_version == 21 else acos_client.AXAPI_30
            c = self.client_factory(vthunder)
            c.slb.service_group.delete(pool.id)
            LOG.info("Pool deleted successfully.")
        except Exception as e:
            LOG.error(str(e))


class PoolUpdate(BaseVThunderTask, PoolParent):
    """ Task to update pool """

    def execute(self, pool, vthunder, update_dict):
        """ Execute update pool """
        old_pool = pool
        if 'session_persistence' in update_dict:
            pool.session_persistence.__dict__.update(update_dict['session_persistence'])
            del update_dict['session_persistence']
        pool.__dict__.update(update_dict)
        c = self.client_factory(vthunder)
        PoolParent.set(self, c.slb.service_group.update, pool, vthunder, old_pool)
