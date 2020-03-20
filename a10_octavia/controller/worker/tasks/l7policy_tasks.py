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


class L7PolicyParent(object):

    def set(self, l7policy, listeners):
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
            LOG.debug("l7policy created successfully: %s", l7policy.id)
        except Exception as e:
            LOG.exception("Failed to create/update l7policy: %s", str(e))
            raise

        try:
            get_listener = self.axapi_client.slb.virtual_server.vport.get(
                listener.load_balancer_id, listener.name,
                listener.protocol, listener.protocol_port)
        except Exception as e:
            LOG.exception("Failed to get listener for l7policy: %s", str(e))
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
            LOG.exception("Failed to update listener for l7policy: %s", str(e))
            raise


class CreateL7Policy(L7PolicyParent, task.Task):
    """Task to create a L7Policy"""

    @axapi_client_decorator
    def execute(self, l7policy, listeners, vthunder):
        self.set(l7policy, listeners)


class UpdateL7Policy(L7PolicyParent, task.Task):
    """Task to update L7Policy"""

    @axapi_client_decorator
    def execute(self, l7policy, listeners, vthunder, update_dict):
        l7policy.__dict__.update(update_dict)
        self.set(l7policy, listeners)


class DeleteL7Policy(task.Task):
    """Task to delete L7Policy"""

    @axapi_client_decorator
    def execute(self, l7policy, vthunder):
        listener = l7policy.listener
        c_pers, s_pers = utils.get_sess_pers_templates(
            listener.default_pool)
        kargs = {}
        get_listener = None

        try:
            get_listener = self.axapi_client.slb.virtual_server.vport.get(
                listener.load_balancer_id, listener.name,
                listener.protocol, listener.protocol_port)
        except Exception as e:
            LOG.warning("Failed to get listener for l7policy: %s", str(e))
            raise

        new_aflex_scripts = []
        if 'aflex-scripts' in get_listener['port']:
            aflex_scripts = get_listener['port']['aflex-scripts']
            for aflex in aflex_scripts:
                if aflex['aflex'] != l7policy.id:
                    new_aflex_scripts.append(aflex)
        kargs["aflex-scripts"] = new_aflex_scripts

        try:
            self.axapi_client.slb.virtual_server.vport.update(
                listener.load_balancer_id, listener.name,
                listener.protocol, listener.protocol_port,
                listener.default_pool_id,
                s_pers, c_pers, 1, **kargs)
            LOG.debug(
                "l7policy %s detached from port %s successfully.", l7policy.id, listener.id)
        except Exception as e:
            LOG.warning("Failed to detach l7policy: %s", str(e))
            raise

        try:
            self.axapi_client.slb.aflex_policy.delete(l7policy.id)
            LOG.debug("l7policy deleted successfully: %s", l7policy.id)
        except Exception as e:
            LOG.warning("Failed to delete l7policy: %s", str(e))
