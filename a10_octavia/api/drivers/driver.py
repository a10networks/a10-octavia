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
import oslo_messaging as messaging

from octavia.api.drivers import exceptions
from octavia.api.drivers import provider_base as driver_base
from octavia.api.drivers import utils as driver_utils
from octavia.common import constants 
from octavia.common import data_models
from octavia.common import utils
from octavia.db import api as db_apis
from octavia.db import repositories
from octavia.network import base as network_base

CONF = cfg.CONF
CONF.import_group('oslo_messaging', 'octavia.common.config')
LOG = logging.getLogger(__name__)


class A10ProviderDriver(driver_base.ProviderDriver):
    def __init__(self):
        super(A10ProviderDriver, self).__init__()
        self._args = {}
        self.namespace = constants.RPC_NAMESPACE_CONTROLLER_AGENT
        self.topic = CONF.oslo_messaging.topic
        self.version = '1.0'
        self.transport = messaging.get_rpc_transport(cfg.CONF)
        self._args['fanout'] = False
        self._args['namespace'] = self.namespace
        self._args['topic'] = self.topic
        self._args['version'] = self.version
        self.target = messaging.Target(**self._args)
        self.client = messaging.RPCClient(self.transport, target=self.target)

    # Load Balancer
    # loadbalancer_create needs to be implemented
    def loadbalancer_create(self, loadbalancer):
        LOG.info('A10 provider load balancer loadbalancer: %s.', loadbalancer.__dict__)
        payload = {constants.LOAD_BALANCER_ID: loadbalancer.loadbalancer_id}
        self.client.cast({}, 'create_load_balancer', **payload)

    def loadbalancer_delete(self, loadbalancer, cascade=False):
        payload = {constants.LOAD_BALANCER_ID: loadbalancer.loadbalancer_id, 'cascade': cascade}
        self.client.cast({}, 'delete_load_balancer', **payload)

    def loadbalancer_update(self, old_loadbalancer, new_loadbalancer):
        # Adapt the provider data model to the queue schema
        lb_dict = new_loadbalancer.to_dict()
        if 'admin_state_up' in lb_dict:
            lb_dict['enabled'] = lb_dict.pop('admin_state_up')
        lb_id = lb_dict.pop('loadbalancer_id')
        # Put the qos_policy_id back under the vip element the controller
        # expects
        vip_qos_policy_id = lb_dict.pop('vip_qos_policy_id', None)
        if vip_qos_policy_id:
            vip_dict = {"qos_policy_id": vip_qos_policy_id}
            lb_dict["vip"] = vip_dict

        payload = {constants.LOAD_BALANCER_ID: lb_id,
                   constants.LOAD_BALANCER_UPDATES: lb_dict}
        self.client.cast({}, 'update_load_balancer', **payload)

    # Many other methods may be inheritted from Amphora

    def listener_create(self, listener):
        LOG.info('A10 provider load_balancer loadbalancer: %s.', listener.__dict__)
        payload = {constants.LISTENER_ID: listener.listener_id}
        self.client.cast({}, 'create_listener', **payload)

    def listener_delete(self, listener):
        listener_id = listener.listener_id
        payload = {constants.LISTENER_ID: listener_id}
        self.client.cast({}, 'delete_listener', **payload)

    def pool_create(self, pool):
        payload = {constants.POOL_ID: pool.pool_id}
        self.client.cast({}, 'create_pool', **payload)

    def pool_delete(self, pool):
        pool_id = pool.pool_id
        payload = {constants.POOL_ID: pool_id}
        self.client.cast({}, 'delete_pool', **payload)

    def member_create(self, member):
        payload = {constants.MEMBER_ID: member.member_id}
        self.client.cast({}, 'create_member', **payload)

    def member_delete(self, member):
        member_id = member.member_id
        payload = {constants.MEMBER_ID: member_id}
        self.client.cast({}, 'delete_member', **payload)

    # Health Monitor
    def health_monitor_create(self, healthmonitor):
        payload = {constants.HEALTH_MONITOR_ID: healthmonitor.healthmonitor_id}
        self.client.cast({}, 'create_health_monitor', **payload)

    def health_monitor_delete(self, healthmonitor):
        healthmonitor_id = healthmonitor.healthmonitor_id
        payload = {constants.HEALTH_MONITOR_ID: healthmonitor_id}
        self.client.cast({}, 'delete_health_monitor', **payload) 

    #L7Policy 

    def l7policy_create(self, l7policy):
        payload = {constants.L7POLICY_ID: l7policy.l7policy_id}
        self.client.cast({}, 'create_l7policy', **payload)

    def l7policy_delete(self, l7policy):
        l7policy_id = l7policy.l7policy_id
        payload = {constants.L7POLICY_ID: l7policy_id}
        self.client.cast({}, 'delete_l7policy', **payload)

    # L7 Rule
    def l7rule_create(self, l7rule):
        payload = {constants.L7RULE_ID: l7rule.l7rule_id}
        self.client.cast({}, 'create_l7rule', **payload)

    def l7rule_delete(self, l7rule):
        l7rule_id = l7rule.l7rule_id
        payload = {constants.L7RULE_ID: l7rule_id}
        self.client.cast({}, 'delete_l7rule', **payload)
