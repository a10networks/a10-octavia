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

from octavia.common import constants
from octavia.controller.worker.v2.tasks import lifecycle_tasks

from a10_octavia.common import openstack_mappings
from a10_octavia.controller.worker.tasks.decorators import axapi_client_decorator
from a10_octavia.controller.worker.tasks.decorators import axapi_client_decorator_for_revert
from a10_octavia.controller.worker.tasks.policy import PolicyUtil
from a10_octavia.controller.worker.tasks import utils

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class L7PolicyParent(object):

    def set(self, l7policy, listeners):
        filename = l7policy[constants.L7POLICY_ID]
        p = PolicyUtil()
        script = p.createPolicy(l7policy)
        size = len(script.encode('utf-8'))
        listener = listeners[0]
        c_pers, s_pers = utils.get_sess_pers_templates(listener.get('default_pool'))
        tcp_proxy, aflex = utils.get_tcp_proxy_template(listener, listener.get('default_pool'))
        kargs = {}
        listener[constants.PROTOCOL] = openstack_mappings.virtual_port_protocol(self.axapi_client,
                                                                     listener[constants.PROTOCOL])
        try:
            self.axapi_client.slb.aflex_policy.create(
                file=filename, script=script, size=size, action="import")
            LOG.debug("Successfully created l7policy: %s", l7policy[constants.L7POLICY_ID])
        except (acos_errors.ACOSException, exceptions.ConnectionError) as e:
            LOG.exception("Failed to create/update l7policy: %s", l7policy[constants.L7POLICY_ID])
            raise e

        try:
            lb_id =  listener.get(constants.LOADBALANCER_ID) or listener.get(constants.LOAD_BALANCER_ID)
            get_listener = self.axapi_client.slb.virtual_server.vport.get(
                lb_id, listener[constants.LISTENER_ID],
                listener[constants.PROTOCOL], listener['protocol_port'])
            LOG.debug("Successfully fetched listener %s for l7policy %s", listener[constants.LISTENER_ID], l7policy[constants.L7POLICY_ID])
        except (acos_errors.ACOSException, exceptions.ConnectionError) as e:
            LOG.exception("Failed to get listener %s for l7policy: %s", listener[constants.LISTENER_ID], l7policy[constants.L7POLICY_ID])
            raise e

        if 'aflex-scripts' in get_listener['port']:
            aflex_scripts = get_listener['port']['aflex-scripts']
            aflex_scripts.append({"aflex": filename})
        else:
            aflex_scripts = [{"aflex": filename}]
        kargs["aflex_scripts"] = aflex_scripts

        try:
            self.axapi_client.slb.virtual_server.vport.update(
                lb_id, listener[constants.LISTENER_ID],
                listener[constants.PROTOCOL], listener['protocol_port'],
                listener['default_pool_id'], s_pers,
                c_pers, 1, tcp_proxy_name=tcp_proxy, **kargs)
            LOG.debug(
                "Successfully associated l7policy %s to listener %s",
                l7policy[constants.L7POLICY_ID],
                listener[constants.LISTENER_ID])
        except (acos_errors.ACOSException, exceptions.ConnectionError) as e:
            LOG.exception(
                "Failed to associate l7policy %s to listener %s",
                l7policy[constants.L7POLICY_ID],
                listener[constants.LISTENER_ID])
            raise e


class CreateL7Policy(L7PolicyParent, task.Task):
    """Task to create a L7Policy"""

    @axapi_client_decorator
    def execute(self, l7policy, listeners, vthunder):
        self.set(l7policy, listeners)

    @axapi_client_decorator_for_revert
    def revert(self, l7policy, listeners, vthunder, *args, **kwargs):
        try:
            self.axapi_client.slb.aflex_policy.delete(l7policy[constants.L7POLICY_ID])
        except exceptions.ConnectionError:
            LOG.exception("Failed to connect A10 Thunder device: %s", vthunder.ip_address)
        except Exception as e:
            LOG.warning(
                "Failed to revert creation of l7policy %s due to %s",
                l7policy[constants.L7POLICY_ID], str(e))


class UpdateL7Policy(L7PolicyParent, task.Task):
    """Task to update L7Policy"""

    @axapi_client_decorator
    def execute(self, l7policy, listeners, vthunder, update_dict):
        l7policy.update(update_dict)
        self.set(l7policy, listeners)


class DeleteL7Policy(task.Task):
    """Task to delete L7Policy"""

    @axapi_client_decorator
    def execute(self, l7policy, listeners, vthunder):
        if self.axapi_client and self.axapi_client.slb:
            listener = listeners[0]
            c_pers, s_pers = utils.get_sess_pers_templates(
                listener.get('default_pool'))
            tcp_proxy, aflex = utils.get_tcp_proxy_template(listener, listener.get('default_pool'))
            kargs = {}
            snat_pool = None
            if not (listener[constants.PROTOCOL]).islower():
                listener[constants.PROTOCOL] = openstack_mappings.virtual_port_protocol(
                    self.axapi_client, listener[constants.PROTOCOL])
            try:
                get_listener = self.axapi_client.slb.virtual_server.vport.get(
                    (listener.get(constants.LOADBALANCER_ID) or listener.get(constants.LOAD_BALANCER_ID)),
                    listener[constants.LISTENER_ID],
                    listener[constants.PROTOCOL], listener['protocol_port'])
                if get_listener and 'port' in get_listener and 'pool' in get_listener['port']:
                    snat_pool = get_listener['port']['pool']
                LOG.debug("Successfully fetched listener %s for l7policy %s", listener[constants.LISTENER_ID], l7policy[constants.L7POLICY_ID])
            except (acos_errors.ACOSException, exceptions.ConnectionError) as e:
                LOG.exception("Failed to get listener %s for l7policy: %s", listener[constants.LISTENER_ID], l7policy[constants.L7POLICY_ID])
                raise e

            new_aflex_scripts = []
            if 'aflex-scripts' in get_listener['port']:
                aflex_scripts = get_listener['port']['aflex-scripts']
                for aflex in aflex_scripts:
                    if aflex['aflex'] != l7policy[constants.L7POLICY_ID]:
                        new_aflex_scripts.append(aflex)
            kargs["aflex_scripts"] = new_aflex_scripts

            try:
                self.axapi_client.slb.virtual_server.vport.replace(
                    (listener.get(constants.LOADBALANCER_ID)or listener.get(constants.LOAD_BALANCER_ID)),
                    listener[constants.LISTENER_ID],
                    listener[constants.PROTOCOL], listener['protocol_port'],
                    listener['default_pool_id'],
                    s_pers, c_pers, 1,
                    source_nat_pool=snat_pool,
                    tcp_proxy_name=tcp_proxy, **kargs)
                LOG.debug(
                    "Successfully dissociated l7policy %s from listener %s",
                    l7policy[constants.L7POLICY_ID],
                    listener[constants.LISTENER_ID])
            except (acos_errors.ACOSException, exceptions.ConnectionError) as e:
                LOG.exception(
                    "Failed to dissociate l7policy %s from listener %s",
                    l7policy[constants.L7POLICY_ID],
                    listener[constants.LISTENER_ID])
                raise e

            try:
                l7policy_exists = self.axapi_client.slb.aflex_policy.exists(l7policy[constants.L7POLICY_ID])
                if l7policy_exists:
                    self.axapi_client.slb.aflex_policy.delete(l7policy[constants.L7POLICY_ID])
                    LOG.debug("Successfully deleted l7policy: %s", l7policy[constants.L7POLICY_ID])
            except (acos_errors.ACOSException, exceptions.ConnectionError) as e:
                LOG.exception("Failed to delete l7policy: %s", l7policy[constants.L7POLICY_ID])
                raise e


class L7PolicyToErrorOnRevertTask(lifecycle_tasks.BaseLifecycleTask):
    """Task to set a l7policy to ERROR on revert."""

    def execute(self, l7policy):
        pass

    def revert(self, l7policy, *args, **kwargs):
        try:
            self.task_utils.mark_l7policy_prov_status_error(l7policy[constants.L7POLICY_ID])
        except Exception as e:
            LOG.exception("Failed to change status due to: %s", e)
