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
from a10_octavia.controller.worker.tasks.policy import PolicyUtil
from a10_octavia.controller.worker.tasks import persist
from a10_octavia.controller.worker.tasks.common import BaseVThunderTask

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class L7PolicyParent(object):

    def set(self, l7policy, listeners, vthunder):
        
        try:
            filename = l7policy.id
            p = PolicyUtil()
            script = p.createPolicy(l7policy)
            size = len(script.encode('utf-8'))
            c = self.client_factory(vthunder)
            c.slb.aflex_policy.create(file=filename, script=script, size=size, action="import")
            LOG.info("aFlex policy created successfully.")
            listener = listeners[0]

            get_listener = c.slb.virtual_server.vport.get(listener.load_balancer_id, listener.name,
                                                          listener.protocol, listener.protocol_port)

            aflex_scripts = []
            if 'aflex-scripts' in get_listener['port']:
                aflex_scripts = get_listener['port']['aflex-scripts']
                aflex_scripts.append({"aflex": filename})
            else:
                aflex_scripts = [{"aflex": filename}]

            persistence = persist.PersistHandler(c, listener.default_pool)

            s_pers = persistence.s_persistence()
            c_pers = persistence.c_persistence()
            kargs = {}
            kargs["aflex-scripts"] = aflex_scripts
            c.slb.virtual_server.vport.update(listener.load_balancer_id, listener.name,
                                              listener.protocol, listener.protocol_port, listener.default_pool_id,
                                              s_pers, c_pers, 1, **kargs)
            LOG.info("Listener updated successfully.")
        except Exception as e:
            LOG.error(str(e))
            LOG.info("Error occurred")



class CreateL7Policy(BaseVThunderTask, L7PolicyParent):
    """ Task to create a L7Policy """

    def execute(self, l7policy, listeners, vthunder):
        """ Execute create L7Policy """
        c = self.client_factory(vthunder)
        status = L7PolicyParent.set(self, 
                                    l7policy,
                                    listeners,
                                    vthunder)


class UpdateL7Policy(BaseVThunderTask, L7PolicyParent):
    """ Task to update L7Policy """

    def execute(self, l7policy, listeners, vthunder, update_dict):
        """ Execute update L7Policy """
        l7policy.__dict__.update(update_dict)
        c = self.client_factory(vthunder)
        status = L7PolicyParent.set(self,
                                    l7policy,
                                    listeners,
                                    vthunder)


class DeleteL7Policy(BaseVThunderTask):
    """ Task to delete L7Policy """

    def execute(self, l7policy, vthunder):
        """ Execute delete L7Policy """
        try:
            listener = l7policy.listener
            old_listener = l7policy.listener
            c = self.client_factory(vthunder)
            c.slb.virtual_server.vport.get(old_listener.load_balancer_id,
                                           old_listener.name,
                                           old_listener.protocol,
                                           old_listener.protocol_port)
            get_listener = c.slb.virtual_server.vport.get(listener.load_balancer_id, listener.name,
                                                          listener.protocol, listener.protocol_port)

            new_aflex_scripts = []
            if 'aflex-scripts' in get_listener['port']:
                aflex_scripts = get_listener['port']['aflex-scripts']
                for aflex in aflex_scripts:
                    if aflex['aflex'] != l7policy.id:
                        new_aflex_scripts.append(aflex)

            persistence = persist.PersistHandler(c, listener.default_pool)

            s_pers = persistence.s_persistence()
            c_pers = persistence.c_persistence()

            kargs = {}
            kargs["aflex-scripts"] = new_aflex_scripts

            c.slb.virtual_server.vport.update(listener.load_balancer_id, listener.name,
                                              listener.protocol, listener.protocol_port, listener.default_pool_id,
                                              s_pers, c_pers, 1, **kargs)

            LOG.info("aFlex policy detached from port successfully.")
            c.slb.aflex_policy.delete(l7policy.id)
            LOG.info("aFlex policy deleted successfully.")
        except Exception as e:
            LOG.error(str(e))
            LOG.info("Error occurred")
