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

    def set(self, set_method, pool, vthunder, update=False):
        args = {'service_group': self.meta(pool, 'service_group', {})}

        try:
            conf_templates = CONF.service_group.template_server
            port_templates = CONF.service_group.template_port
            policy_templates = CONF.service_group.template_policy
            c = self.client_factory(vthunder)
            self._update_session_persistence(pool, c, update)
            service_group_temp = {}
            service_group_temp['template-server'] = conf_templates
            service_group_temp['template-port'] = port_templates
            service_group_temp['template-policy'] = policy_templates
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

    def _update_session_persistence(self, pool, c, update=False):
        if pool.session_persistence:
            p = handler_persist.PersistHandler(c, pool)
            if update:
                p.delete()
            p.create()
            return


class PoolCreate(PoolParent, BaseVThunderTask):
    """ Task to create pool """

    def execute(self, pool, vthunder):
        """ Execute create pool """
        c = self.client_factory(vthunder)
        self.set(c.slb.service_group.create, pool, vthunder)


class PoolDelete(BaseVThunderTask):
    """ Task to delete pool """

    def execute(self, pool, vthunder):
        """ Execute delete pool """
        try:
            c = self.client_factory(vthunder)
            handler_persist.PersistHandler(c, pool).delete()
            c.slb.service_group.delete(pool.id)
            LOG.info("Pool deleted successfully.")
        except Exception as e:
            LOG.error(str(e))


class PoolUpdate(PoolParent, BaseVThunderTask):
    """ Task to update pool """

    def execute(self, pool, vthunder, update_dict):
        """ Execute update pool """
        c = self.client_factory(vthunder)
        if 'session_persistence' in update_dict:
            pool.session_persistence.__dict__.update(update_dict['session_persistence'])
            del update_dict['session_persistence']
        pool.__dict__.update(update_dict)
        self.set(c.slb.service_group.update, pool, vthunder, update=True)
