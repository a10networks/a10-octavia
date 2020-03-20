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

from a10_octavia.controller.worker.tasks.decorators import axapi_client_decorator
from a10_octavia.controller.worker.tasks.policy import PolicyUtil
from a10_octavia.controller.worker.tasks import utils

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class L7RuleParent(object):

    def set(self, l7rule, listeners):
        l7policy = l7rule.l7policy
        filename = l7policy.id
        p = PolicyUtil()
        script = p.createPolicy(l7policy)
        size = len(script.encode('utf-8'))
        listener = listeners[0]
        c_pers, s_pers = utils.get_sess_pers_templates(listener.default_pool)
        kargs = {}
        get_listener = None
        try:
            self.axapi_client.slb.aflex_policy.create(
                file=filename, script=script, size=size, action="import")
            LOG.debug("aFlex policy created successfully.")
        except Exception as e:
            LOG.exception("Failed to create/update l7rule: %s", str(e))
            raise

        try:
            get_listener = self.axapi_client.slb.virtual_server.vport.get(
                listener.load_balancer_id, listener.name,
                listener.protocol, listener.protocol_port)
        except Exception as e:
            LOG.exception("Failed to get listener for l7rule: %s", str(e))
            raise

        aflex_scripts = []
        if 'aflex-scripts' in get_listener['port']:
            aflex_scripts = get_listener['port']['aflex-scripts']
            aflex_scripts.append({"aflex": filename})
        else:
            aflex_scripts = [{"aflex": filename}]
        kargs["aflex-scripts"] = aflex_scripts

        try:
            self.axapi_client.slb.virtual_server.vport.update(
                listener.load_balancer_id, listener.name,
                listener.protocol, listener.protocol_port,
                listener.default_pool_id, s_pers,
                c_pers, 1, **kargs)
            LOG.debug("Listener updated successfully: %s", listener.id)
        except Exception as e:
            LOG.exception("Failed to create/update l7rule: %s", str(e))
            raise


class CreateL7Rule(L7RuleParent, task.Task):
    """Task to create L7Rule"""

    @axapi_client_decorator
    def execute(self, l7rule, listeners, vthunder):
        self.set(l7rule, listeners)


class UpdateL7Rule(L7RuleParent, task.Task):
    """Task to update L7Rule"""

    @axapi_client_decorator
    def execute(self, l7rule, listeners, vthunder, update_dict):
        l7rule.__dict__.update(update_dict)
        self.set(l7rule, listeners)


class DeleteL7Rule(task.Task):
    """Task to delete a L7rule and disassociate from provided pool"""

    @axapi_client_decorator
    def execute(self, l7rule, listeners, vthunder):
        policy = l7rule.l7policy
        rules = policy.l7rules

        for index, rule in enumerate(rules):
            if rule.id == l7rule.id:
                del rules[index]
                break
        policy.rules = rules
        l7rule.l7policy = policy
        l7policy = l7rule.l7policy
        filename = l7policy.id
        p = PolicyUtil()
        script = p.createPolicy(l7policy)
        size = len(script.encode('utf-8'))
        listener = listeners[0]
        c_pers, s_pers = utils.get_sess_pers_templates(listener.default_pool)
        kargs = {}
        try:
            self.axapi_client.slb.aflex_policy.create(
                file=filename, script=script, size=size, action="import")
            LOG.debug("aFlex policy deleted successfully.")
        except Exception as e:
            LOG.warning("Failed to delete l7rule: %s", str(e))
            raise

        try:
            get_listener = self.axapi_client.slb.virtual_server.vport.get(
                listener.load_balancer_id, listener.name,
                listener.protocol, listener.protocol_port)
        except Exception as e:
            LOG.warning("Failed to delete l7rule: %s", str(e))
            raise

        aflex_scripts = []
        if 'aflex-scripts' in get_listener['port']:
            aflex_scripts = get_listener['port']['aflex-scripts']
            aflex_scripts.append({"aflex": filename})
        else:
            aflex_scripts = [{"aflex": filename}]
        kargs["aflex-scripts"] = aflex_scripts

        try:
            self.axapi_client.slb.virtual_server.vport.update(
                listener.load_balancer_id, listener.name,
                listener.protocol, listener.protocol_port, listener.default_pool_id,
                s_pers, c_pers, 1, **kargs)
            LOG.debug("Listener updated successfully: %s", listener.id)
        except Exception as e:
            LOG.warning("Failed to delete l7rule: %s", str(e))
            raise
