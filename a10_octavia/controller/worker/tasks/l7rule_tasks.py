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


class L7RuleParent(object):

    def set(self, l7rule, listeners, vthunder):
        """ Execute create l7rule """
        try:
            l7policy = l7rule.l7policy
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


class CreateL7Rule(L7RuleParent, BaseVThunderTask):
    """ Task to create L7Rule """

    def execute(self, l7rule, listeners, vthunder):
        self.client_factory(vthunder)
        self.set(l7rule, listeners, vthunder)


class UpdateL7Rule(L7RuleParent, BaseVThunderTask):
    """ Task to update L7Rule """

    def execute(self, l7rule, listeners, vthunder, update_dict):
        l7rule.__dict__.update(update_dict)
        self.client_factory(vthunder)
        self.set(l7rule, listeners, vthunder)


class DeleteL7Rule(BaseVThunderTask):
    """ Task to delete a L7rule and disassociate from provided pool """

    def execute(self, l7rule, listeners, vthunder):
        """ Execute delete L7Rule """
        policy = l7rule.l7policy
        rules = policy.l7rules

        for index, rule in enumerate(rules):
                if rule.id == l7rule.id:
                    del rules[index]
                    break
        policy.rules = rules
        l7rule.l7policy = policy
        try:
            l7pol = l7rule.l7policy
            filename = l7pol.id
            p = PolicyUtil()
            script = p.createPolicy(l7pol)
            size = len(script.encode('utf-8'))
            c = self.client_factory(vthunder)
            c.slb.aflex_policy.create(file=filename, script=script, size=size, action="import")
            LOG.info("aFlex policy created successfully.")
            # get SLB vPort
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
