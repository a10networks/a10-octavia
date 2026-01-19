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
#from stevedore import driver as stevedore_driver

from octavia.common import constants

from a10_octavia.controller.worker import controller_worker

CONF = cfg.CONF

LOG = logging.getLogger(__name__)


class Endpoint(object):

    # API version history:
    #   1.0 - Initial version.
    #   2.0 - Provider driver format.
    target = messaging.Target(
        namespace=constants.RPC_NAMESPACE_CONTROLLER_AGENT,
        version='1.0')

    def __init__(self, ctx_map, ctx_lock):
        # self.worker = stevedore_driver.DriverManager(
        #     namespace='a10.plugins',
        #     name='a10_octavia_plugin',
        #     invoke_on_load=True
        # ).driver
        self.worker = controller_worker.A10ControllerWorker()
        self.worker.a10_worker_ctx_init(ctx_map, ctx_lock)

    def create_load_balancer(self, context, loadbalancer, flavor=None):
        LOG.info('Creating load balancer \'%s\'...', loadbalancer[constants.LOADBALANCER_ID])
        self.worker.create_load_balancer(loadbalancer, flavor)

    def update_load_balancer(self, context, original_load_balancer,
                             load_balancer_updates):
        LOG.info('Updating load balancer \'%s\'...', original_load_balancer[constants.LOADBALANCER_ID])
        self.worker.update_load_balancer(original_load_balancer,
                                         load_balancer_updates)

    def delete_load_balancer(self, context, loadbalancer, cascade=False):
        LOG.info('Deleting load balancer \'%s\'...', loadbalancer[constants.LOADBALANCER_ID])
        self.worker.delete_load_balancer(loadbalancer, cascade)

    def failover_load_balancer(self, context, load_balancer_id):
        LOG.info('Failing over amphora in load balancer \'%s\'...',
                 load_balancer_id)
        self.worker.failover_loadbalancer(load_balancer_id)

    def failover_amphora(self, context, amphora_id):
        LOG.info('Failing over amphora \'%s\'...',
                 amphora_id)
        self.worker.failover_amphora(amphora_id)

    def create_listener(self, context, listener):
        LOG.info('Creating listener \'%s\'...', listener[constants.LISTENER_ID])
        self.worker.create_listener(listener)

    def update_listener(self, context, original_listener, listener_updates):
        LOG.info('Updating listener \'%s\'...', original_listener[constants.LISTENER_ID])
        self.worker.update_listener(original_listener, listener_updates)

    def delete_listener(self, context, listener):
        LOG.info('Deleting listener \'%s\'...', listener[constants.LISTENER_ID])
        self.worker.delete_listener(listener)

    def create_pool(self, context, pool):
        LOG.info('Creating pool \'%s\'...', pool.get(constants.POOL_ID))
        self.worker.create_pool(pool)

    def update_pool(self, context, original_pool, pool_updates):
        LOG.info('Updating pool \'%s\'...', original_pool.get(constants.POOL_ID))
        self.worker.update_pool(original_pool, pool_updates)

    def delete_pool(self, context, pool):
        LOG.info('Deleting pool \'%s\'...', pool.get(constants.POOL_ID))
        self.worker.delete_pool(pool)

    def create_health_monitor(self, context, health_monitor):
        LOG.info('Creating health monitor \'%s\'...', health_monitor.get(
            constants.HEALTHMONITOR_ID))
        self.worker.create_health_monitor(health_monitor)

    def update_health_monitor(self, context, original_health_monitor,
                              health_monitor_updates):
        LOG.info('Updating health monitor \'%s\'...', original_health_monitor.get(
            constants.HEALTHMONITOR_ID))
        self.worker.update_health_monitor(original_health_monitor,
                                          health_monitor_updates)

    def delete_health_monitor(self, context, health_monitor):
        LOG.info('Deleting health monitor \'%s\'...', health_monitor.get(
            constants.HEALTHMONITOR_ID))
        self.worker.delete_health_monitor(health_monitor)

    def create_member(self, context, member):
        LOG.info('Creating member \'%s\'...', member.get(constants.MEMBER_ID))
        self.worker.create_member(member)

    def update_member(self, context, original_member, member_updates):
        LOG.info('Updating member \'%s\'...', original_member.get(constants.MEMBER_ID))
        self.worker.update_member(original_member, member_updates)

    def batch_update_members(self, context, old_members, new_members,
                             updated_members):
        updated_member_ids = [m.get(constants.ID) for m in updated_members]
        new_member_ids = [m.get(constants.ID) for m in new_members]
        old_member_ids = [m.get(constants.ID) for m in old_members]
        LOG.info(
            'Batch updating members: old=\'%(old)s\', new=\'%(new)s\', '
            'updated=\'%(updated)s\'...',
            {'old': old_member_ids, 'new': new_member_ids,
             'updated': updated_member_ids})
        self.worker.batch_update_members(
            old_members, new_members, updated_members)

    def delete_member(self, context, member):
        LOG.info('Deleting member \'%s\'...', member.get(constants.MEMBER_ID))
        self.worker.delete_member(member)

    def create_l7policy(self, context, l7policy):
        LOG.info('Creating l7policy \'%s\'...', l7policy.get(constants.L7POLICY_ID))
        self.worker.create_l7policy(l7policy)

    def update_l7policy(self, context, original_l7policy, l7policy_updates):
        LOG.info('Updating l7policy \'%s\'...', original_l7policy.get(constants.L7POLICY_ID))
        self.worker.update_l7policy(original_l7policy, l7policy_updates)

    def delete_l7policy(self, context, l7policy):
        LOG.info('Deleting l7policy \'%s\'...', l7policy.get(constants.L7POLICY_ID))
        self.worker.delete_l7policy(l7policy)

    def create_l7rule(self, context, l7rule):
        LOG.info('Creating l7rule \'%s\'...', l7rule.get(constants.L7RULE_ID))
        self.worker.create_l7rule(l7rule)

    def update_l7rule(self, context, original_l7rule, l7rule_updates):
        LOG.info('Updating l7rule \'%s\'...', original_l7rule.get(constants.L7RULE_ID))
        self.worker.update_l7rule(original_l7rule, l7rule_updates)

    def delete_l7rule(self, context, l7rule):
        LOG.info('Deleting l7rule \'%s\'...', l7rule.get(constants.L7RULE_ID))
        self.worker.delete_l7rule(l7rule)
