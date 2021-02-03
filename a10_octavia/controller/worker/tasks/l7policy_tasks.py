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
from acos_client import errors as acos_errors
from oslo_config import cfg
from oslo_log import log as logging
from requests import exceptions
from taskflow import task

from a10_octavia.common import openstack_mappings
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
        listener.protocol = openstack_mappings.virtual_port_protocol(self.axapi_client,
                                                                     listener.protocol)
        try:
            self.axapi_client.slb.aflex_policy.create(
                file=filename, script=script, size=size, action="import")
            LOG.debug("Successfully created l7policy: %s", l7policy.id)
        except (acos_errors.ACOSException, exceptions.ConnectionError) as e:
            LOG.exception("Failed to create/update l7policy: %s", l7policy.id)
            raise e

        try:
            get_listener = self.axapi_client.slb.virtual_server.vport.get(
                listener.load_balancer_id, listener.id,
                listener.protocol, listener.protocol_port)
            LOG.debug("Successfully fetched listener %s for l7policy %s", listener.id, l7policy.id)
        except (acos_errors.ACOSException, exceptions.ConnectionError) as e:
            LOG.exception("Failed to get listener %s for l7policy: %s", listener.id, l7policy.id)
            raise e

        if 'aflex-scripts' in get_listener['port']:
            aflex_scripts = get_listener['port']['aflex-scripts']
            aflex_scripts.append({"aflex": filename})
        else:
            aflex_scripts = [{"aflex": filename}]
        kargs["aflex_scripts"] = aflex_scripts

        try:
            self.axapi_client.slb.virtual_server.vport.update(
                listener.load_balancer_id, listener.id,
                listener.protocol, listener.protocol_port,
                listener.default_pool_id, s_pers,
                c_pers, 1, **kargs)
            LOG.debug(
                "Successfully associated l7policy %s to listener %s",
                l7policy.id,
                listener.id)
        except (acos_errors.ACOSException, exceptions.ConnectionError) as e:
            LOG.exception(
                "Failed to associate l7policy %s to listener %s",
                l7policy.id,
                listener.id)
            raise e


class CreateL7Policy(L7PolicyParent, task.Task):
    """Task to create a L7Policy"""

    @axapi_client_decorator
    def execute(self, l7policy, listeners, vthunder):
        self.set(l7policy, listeners)

    @axapi_client_decorator
    def revert(self, l7policy, listeners, vthunder, *args, **kwargs):
        try:
            self.axapi_client.slb.aflex_policy.delete(l7policy.id)
        except exceptions.ConnectionError:
            LOG.exception("Failed to connect A10 Thunder device: %s", vthunder.ip_address)
        except Exception as e:
            LOG.warning(
                "Failed to revert creation of l7policy %s due to %s",
                l7policy.id, str(e))


class UpdateL7Policy(L7PolicyParent, task.Task):
    """Task to update L7Policy"""

    @axapi_client_decorator
    def execute(self, l7policy, listeners, vthunder, update_dict):
        l7policy.update(update_dict)
        self.set(l7policy, listeners)


class DeleteL7Policy(task.Task):
    """Task to delete L7Policy"""

    @axapi_client_decorator
    def execute(self, l7policy, vthunder):
        listener = l7policy.listener
        c_pers, s_pers = utils.get_sess_pers_templates(
            listener.default_pool)
        kargs = {}
        listener.protocol = openstack_mappings.virtual_port_protocol(self.axapi_client,
                                                                     listener.protocol)
        try:
            get_listener = self.axapi_client.slb.virtual_server.vport.get(
                listener.load_balancer_id, listener.id,
                listener.protocol, listener.protocol_port)
            LOG.debug("Successfully fetched listener %s for l7policy %s", listener.id, l7policy.id)
        except (acos_errors.ACOSException, exceptions.ConnectionError) as e:
            LOG.exception("Failed to get listener %s for l7policy: %s", listener.id, l7policy.id)
            raise e

        new_aflex_scripts = []
        if 'aflex-scripts' in get_listener['port']:
            aflex_scripts = get_listener['port']['aflex-scripts']
            for aflex in aflex_scripts:
                if aflex['aflex'] != l7policy.id:
                    new_aflex_scripts.append(aflex)
        kargs["aflex_scripts"] = new_aflex_scripts

        try:
            self.axapi_client.slb.virtual_server.vport.replace(
                listener.load_balancer_id, listener.id,
                listener.protocol, listener.protocol_port,
                listener.default_pool_id,
                s_pers, c_pers, 1, **kargs)
            LOG.debug(
                "Successfully dissociated l7policy %s from listener %s",
                l7policy.id,
                listener.id)
        except (acos_errors.ACOSException, exceptions.ConnectionError) as e:
            LOG.exception(
                "Failed to dissociate l7policy %s from listener %s",
                l7policy.id,
                listener.id)
            raise e

        try:
            self.axapi_client.slb.aflex_policy.delete(l7policy.id)
            LOG.debug("Successfully deleted l7policy: %s", l7policy.id)
        except (acos_errors.ACOSException, exceptions.ConnectionError) as e:
            LOG.exception("Failed to delete l7policy: %s", l7policy.id)
            raise e
