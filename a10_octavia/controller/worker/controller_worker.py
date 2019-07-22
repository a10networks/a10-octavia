# Copyright 2015 Hewlett-Packard Development Company, L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
#


#from oslo_config import cfg
#from oslo_log import log as logging

#from octavia.common import base_taskflow
#from octavia.api.drivers import exceptions

from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import excutils
from sqlalchemy.orm import exc as db_exceptions

from octavia.api.drivers import driver_lib
from octavia.common import constants
from octavia.common import base_taskflow
from taskflow.listeners import logging as tf_logging
from octavia.db import api as db_apis
from octavia.db import repositories as repo
from a10_octavia.db import repositories as a10repo
from a10_octavia.controller.worker.flows import a10_load_balancer_flows
from a10_octavia.controller.worker.flows import a10_listener_flows
from a10_octavia.controller.worker.flows import a10_pool_flows
from a10_octavia.controller.worker.flows import a10_member_flows
from a10_octavia.controller.worker.flows import a10_health_monitor_flows
from a10_octavia.controller.worker.flows import a10_l7policy_flows
from a10_octavia.controller.worker.flows import a10_l7rule_flows


import acos_client
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class A10ControllerWorker(base_taskflow.BaseTaskFlowEngine):

    def __init__(self):
        self._lb_repo = repo.LoadBalancerRepository()
        self._listener_repo = repo.ListenerRepository()
        self._pool_repo = repo.PoolRepository()
        self._member_repo = repo.MemberRepository()
        self._health_mon_repo = repo.HealthMonitorRepository()
        self._l7policy_repo = repo.L7PolicyRepository()
        self._l7rule_repo = repo.L7RuleRepository()
        self._octavia_driver_db = driver_lib.DriverLibrary()
        self._lb_flows = a10_load_balancer_flows.LoadBalancerFlows()
        self._listener_flows = a10_listener_flows.ListenerFlows()
        self._pool_flows = a10_pool_flows.PoolFlows()
        self._member_flows = a10_member_flows.MemberFlows()
        self._health_monitor_flows = a10_health_monitor_flows.HealthMonitorFlows()
        self._l7policy_flows = a10_l7policy_flows.L7PolicyFlows()
        self._l7rule_flows = a10_l7rule_flows.L7RuleFlows()
        self._vthunder_repo = a10repo.VThunderRepository()
        
        self._exclude_result_logging_tasks = ()
        super(A10ControllerWorker, self).__init__()
        

    def create_amphora(self):
        """Creates an Amphora.

        This is used to create spare amphora.

        :returns: amphora_id
        """
        raise exceptions.NotImplementedError(
            user_fault_string='This provider does not support creating Amphora'
                              'yet.',
            operator_fault_string='This provider does not support creating '
                                  'Amphora. We will use preconfigured '
                                  'devices.')

    def delete_amphora(self, amphora_id):
        """Deletes an existing Amphora.

        :param amphora_id: ID of the amphora to delete
        :returns: None
        :raises AmphoraNotFound: The referenced Amphora was not found
        """
        raise exceptions.NotImplementedError(
            user_fault_string='This provider does not support deleting Amphora'
                              'yet.',
            operator_fault_string='This provider does not support deleting '
                                  'Amphora. We will use preconfigured '
                                  'devices.')

    def create_health_monitor(self, health_monitor_id):
        """Creates a health monitor.

        :param pool_id: ID of the pool to create a health monitor on
        :returns: None
        :raises NoResultFound: Unable to find the object
        """
        health_mon = self._health_mon_repo.get(db_apis.get_session(),
                                               id=health_monitor_id)
        if not health_mon:
            LOG.warning('Failed to fetch %s %s from DB. Retrying for up to '
                        '60 seconds.', 'health_monitor', health_monitor_id)
            raise db_exceptions.NoResultFound

        pool = health_mon.pool
        listeners = pool.listeners
        pool.health_monitor = health_mon
        load_balancer = pool.load_balancer

        create_hm_tf = self._taskflow_load(
            self._health_monitor_flows.get_create_health_monitor_flow(),
            store={constants.HEALTH_MON: health_mon,
                   constants.POOL: pool,
                   constants.LISTENERS: listeners,
                   constants.LOADBALANCER: load_balancer})
        with tf_logging.DynamicLoggingListener(create_hm_tf,
                                               log=LOG):
            create_hm_tf.run()

    def delete_health_monitor(self, health_monitor_id):
        """Deletes a health monitor.

        :param pool_id: ID of the pool to delete its health monitor
        :returns: None
        :raises HMNotFound: The referenced health monitor was not found
        """
        health_mon = self._health_mon_repo.get(db_apis.get_session(),
                                               id=health_monitor_id)

        pool = health_mon.pool
        listeners = pool.listeners
        load_balancer = pool.load_balancer

        delete_hm_tf = self._taskflow_load(
            self._health_monitor_flows.get_delete_health_monitor_flow(),
            store={constants.HEALTH_MON: health_mon,
                   constants.POOL: pool,
                   constants.LISTENERS: listeners,
                   constants.LOADBALANCER: load_balancer})
        with tf_logging.DynamicLoggingListener(delete_hm_tf,
                                               log=LOG):
            delete_hm_tf.run()

    def update_health_monitor(self, health_monitor_id, health_monitor_updates):
        """Updates a health monitor.

        :param pool_id: ID of the pool to have it's health monitor updated
        :param health_monitor_updates: Dict containing updated health monitor
        :returns: None
        :raises HMNotFound: The referenced health monitor was not found
        """
        health_mon = None
        try:
            health_mon = self._get_db_obj_until_pending_update(
                self._health_mon_repo, health_monitor_id)
        except tenacity.RetryError as e:
            LOG.warning('Health monitor did not go into %s in 60 seconds. '
                        'This either due to an in-progress Octavia upgrade '
                        'or an overloaded and failing database. Assuming '
                        'an upgrade is in progress and continuing.',
                        constants.PENDING_UPDATE)
            health_mon = e.last_attempt.result()

        pool = health_mon.pool
        listeners = pool.listeners
        pool.health_monitor = health_mon
        load_balancer = pool.load_balancer

        update_hm_tf = self._taskflow_load(
            self._health_monitor_flows.get_update_health_monitor_flow(),
            store={constants.HEALTH_MON: health_mon,
                   constants.POOL: pool,
                   constants.LISTENERS: listeners,
                   constants.LOADBALANCER: load_balancer,
                   constants.UPDATE_DICT: health_monitor_updates})
        with tf_logging.DynamicLoggingListener(update_hm_tf,
                                               log=LOG):
            update_hm_tf.run()

    def create_listener(self, listener_id):
        """Creates a listener.

        :param listener_id: ID of the listener to create
        :returns: None
        :raises NoResultFound: Unable to find the object
        """
        listener = self._listener_repo.get(db_apis.get_session(),
                                           id=listener_id)
        if not listener:
            LOG.warning('Failed to fetch %s %s from DB. Retrying for up to '
                        '60 seconds.', 'listener', listener_id)
            raise db_exceptions.NoResultFound

        load_balancer = listener.load_balancer

        create_listener_tf = self._taskflow_load(self._listener_flows.
                                                 get_create_listener_flow(),
                                                 store={constants.LOADBALANCER:
                                                        load_balancer,
                                                        constants.LISTENERS:
                                                            [listener]})
        with tf_logging.DynamicLoggingListener(create_listener_tf,
                                               log=LOG):
            create_listener_tf.run()


    def delete_listener(self, listener_id):
        """Deletes a listener.

        :param listener_id: ID of the listener to delete
        :returns: None
        :raises ListenerNotFound: The referenced listener was not found
        """
        listener = self._listener_repo.get(db_apis.get_session(),
                                           id=listener_id)
        load_balancer = listener.load_balancer

        delete_listener_tf = self._taskflow_load(
            self._listener_flows.get_delete_listener_flow(),
            store={constants.LOADBALANCER: load_balancer,
                   constants.LISTENER: listener})
        with tf_logging.DynamicLoggingListener(delete_listener_tf,
                                               log=LOG):
            delete_listener_tf.run()


    def update_listener(self, listener_id, listener_updates):
        """Updates a listener.

        :param listener_id: ID of the listener to update
        :param listener_updates: Dict containing updated listener attributes
        :returns: None
        :raises ListenerNotFound: The referenced listener was not found
        """

        raise exceptions.NotImplementedError(
            user_fault_string='This provider does not support updating '
                              'listeners yet',
            operator_fault_string='This provider does not support updating '
                                  'listeners yet')

    def create_load_balancer(self, load_balancer_id):
        """Creates a load balancer by allocating Amphorae.

        :param load_balancer_id: ID of the load balancer to create
        :returns: None
        :raises NoResultFound: Unable to find the object
        """
        lb = self._lb_repo.get(db_apis.get_session(), id=load_balancer_id)
        if not lb:
            LOG.warning('Failed to fetch %s %s from DB. Retrying for up to '
                        '60 seconds.', 'load_balancer', load_balancer_id)
            raise db_exceptions.NoResultFound

        LOG.info("A10ControllerWorker.create_load_balancer called. self: %s load_balancer_id: %s lb: %s vip: %s" % (self.__dict__, load_balancer_id, lb.__dict__, lb.vip.__dict__))
        LOG.info("A10ControllerWorker.create_load_balancer called. lb name: %s lb id: %s vip ip: %s" % (lb.name, load_balancer_id, lb.vip.ip_address))

        store = {constants.LOADBALANCER_ID: load_balancer_id,
                 constants.BUILD_TYPE_PRIORITY:
                 constants.LB_CREATE_NORMAL_PRIORITY}

        topology = CONF.controller_worker.loadbalancer_topology

        store[constants.UPDATE_DICT] = {
            constants.LOADBALANCER_TOPOLOGY: topology
        }

        create_lb_flow = self._lb_flows.get_create_load_balancer_flow(
            topology=topology, listeners=lb.listeners)
        create_lb_tf = self._taskflow_load(create_lb_flow, store=store)
        with tf_logging.DynamicLoggingListener(
                create_lb_tf, log=LOG,
                hide_inputs_outputs_of=self._exclude_result_logging_tasks):
            create_lb_tf.run()
        

    def delete_load_balancer(self, load_balancer_id, cascade=False):
        """Deletes a load balancer by de-allocating Amphorae.

        :param load_balancer_id: ID of the load balancer to delete
        :returns: None
        :raises LBNotFound: The referenced load balancer was not found
        """
        lb = self._lb_repo.get(db_apis.get_session(),
                               id=load_balancer_id)
        vthunder = self._vthunder_repo.getVThunderFromLB(db_apis.get_session(),
                               load_balancer_id)
        deleteCompute = self._vthunder_repo.getDeleteComputeFlag(db_apis.get_session(),
                               vthunder.compute_id)
        (flow, store) = self._lb_flows.get_delete_load_balancer_flow(lb, deleteCompute)
        store.update({constants.LOADBALANCER: lb,
                      constants.SERVER_GROUP_ID: lb.server_group_id})

        delete_lb_tf = self._taskflow_load(flow, store=store)

        with tf_logging.DynamicLoggingListener(delete_lb_tf,
                                               log=LOG):
            delete_lb_tf.run()


        #IMP: Jacobs code
        # No exception even when acos fails...
        #try:
        #    r = self.c.slb.virtual_server.delete(load_balancer_id)
        #    status = { 'loadbalancers': [{"id": load_balancer_id,
        #               "provisioning_status": constants.DELETED}]}
        #except Exception as e:
        #    r = str(e)
        #    status = { 'loadbalancers': [{"id": load_balancer_id,
        #               "provisioning_status": consts.ERROR }]}
        #LOG.info("vThunder response: %s" % (r))
        #LOG.info("Updating db with this status: %s" % (status))
        #self._octavia_driver_db.update_loadbalancer_status(status)

    def update_load_balancer(self, load_balancer_id, load_balancer_updates):
        """Updates a load balancer.

        :param load_balancer_id: ID of the load balancer to update
        :param load_balancer_updates: Dict containing updated load balancer
        :returns: None
        :raises LBNotFound: The referenced load balancer was not found
        """
        LOG.info("A10ControllerWorker.update_load_balancer called. self: %s load_balancer_id: %s load_balancer_updates: %s" % (self.__dict__, load_balancer_id, load_balancer_updates))

        try:
            #r = self.c.slb.virtual_server.update(load_balancer_id, lb.vip.ip_address)
            status = { 'loadbalancers': [{"id": load_balancer_id,
                       "provisioning_status": constants.ACTIVE }]}
        except Exception as e:
            r = str(e)
            status = { 'loadbalancers': [{"id": load_balancer_id,
                       "provisioning_status": constants.ERROR }]}
        LOG.info("Updating db with this status: %s" % (status))
        lb.update(db_apis.get_session(), loadbalancer.id,
                                      **update_dict)



    def create_member(self, member_id):
        """Creates a pool member.

        :param member_id: ID of the member to create
        :returns: None
        :raises NoSuitablePool: Unable to find the node pool
        """
        member = self._member_repo.get(db_apis.get_session(),
                                       id=member_id)
        if not member:
            LOG.warning('Failed to fetch %s %s from DB. Retrying for up to '
                        '60 seconds.', 'member', member_id)
            raise db_exceptions.NoResultFound

        pool = member.pool
        listeners = pool.listeners
        load_balancer = pool.load_balancer

        create_member_tf = self._taskflow_load(self._member_flows.
                                               get_create_member_flow(),
                                               store={constants.MEMBER: member,
                                                      constants.LISTENERS:
                                                          listeners,
                                                      constants.LOADBALANCER:
                                                          load_balancer,
                                                      constants.POOL: pool})
        with tf_logging.DynamicLoggingListener(create_member_tf,
                                               log=LOG):
            create_member_tf.run()



    def delete_member(self, member_id):
        """Deletes a pool member.

        :param member_id: ID of the member to delete
        :returns: None
        :raises MemberNotFound: The referenced member was not found
        """
        member = self._member_repo.get(db_apis.get_session(),
                                       id=member_id)
        pool = member.pool
        listeners = pool.listeners
        load_balancer = pool.load_balancer

        delete_member_tf = self._taskflow_load(
            self._member_flows.get_delete_member_flow(),
            store={constants.MEMBER: member, constants.LISTENERS: listeners,
                   constants.LOADBALANCER: load_balancer, constants.POOL: pool}
        )
        with tf_logging.DynamicLoggingListener(delete_member_tf,
                                               log=LOG):
            delete_member_tf.run()



    def batch_update_members(self, old_member_ids, new_member_ids,
                             updated_members):

        raise exceptions.NotImplementedError(
            user_fault_string='This provider does not support members yet',
            operator_fault_string='This provider does not support members yet')

    def update_member(self, member_id, member_updates):
        """Updates a pool member.

        :param member_id: ID of the member to update
        :param member_updates: Dict containing updated member attributes
        :returns: None
        :raises MemberNotFound: The referenced member was not found
        """

        raise exceptions.NotImplementedError(
            user_fault_string='This provider does not support members yet',
            operator_fault_string='This provider does not support members yet')

    def create_pool(self, pool_id):
        """Creates a node pool.

        :param pool_id: ID of the pool to create
        :returns: None
        :raises NoResultFound: Unable to find the object
        """
        pool = self._pool_repo.get(db_apis.get_session(),
                                   id=pool_id)
        if not pool:
            LOG.warning('Failed to fetch %s %s from DB. Retrying for up to '
                        '60 seconds.', 'pool', pool_id)
            raise db_exceptions.NoResultFound

        listeners = pool.listeners
        load_balancer = pool.load_balancer

        create_pool_tf = self._taskflow_load(self._pool_flows.
                                             get_create_pool_flow(),
                                             store={constants.POOL: pool,
                                                    constants.LISTENERS:
                                                        listeners,
                                                    constants.LOADBALANCER:
                                                        load_balancer})
        with tf_logging.DynamicLoggingListener(create_pool_tf,
                                               log=LOG):
            create_pool_tf.run()


    def delete_pool(self, pool_id):
        """Deletes a node pool.

        :param pool_id: ID of the pool to delete
        :returns: None
        :raises PoolNotFound: The referenced pool was not found
        """
        pool = self._pool_repo.get(db_apis.get_session(),
                                   id=pool_id)

        load_balancer = pool.load_balancer
        listeners = pool.listeners

        delete_pool_tf = self._taskflow_load(
            self._pool_flows.get_delete_pool_flow(),
            store={constants.POOL: pool, constants.LISTENERS: listeners,
                   constants.LOADBALANCER: load_balancer})
        with tf_logging.DynamicLoggingListener(delete_pool_tf,
                                               log=LOG):
            delete_pool_tf.run()

    def update_pool(self, pool_id, pool_updates):
        """Updates a node pool.

        :param pool_id: ID of the pool to update
        :param pool_updates: Dict containing updated pool attributes
        :returns: None
        :raises PoolNotFound: The referenced pool was not found
        """

        raise exceptions.NotImplementedError(
            user_fault_string='This provider does not support pools yet',
            operator_fault_string='This provider does not support pools yet')

    def create_l7policy(self, l7policy_id):
        """Creates an L7 Policy.

        :param l7policy_id: ID of the l7policy to create
        :returns: None
        :raises NoResultFound: Unable to find the object
        """
        l7policy = self._l7policy_repo.get(db_apis.get_session(),
                                           id=l7policy_id)
        if not l7policy:
            LOG.warning('Failed to fetch %s %s from DB. Retrying for up to '
                        '60 seconds.', 'l7policy', l7policy_id)
            raise db_exceptions.NoResultFound

        listeners = [l7policy.listener]
        load_balancer = l7policy.listener.load_balancer

        create_l7policy_tf = self._taskflow_load(
            self._l7policy_flows.get_create_l7policy_flow(),
            store={constants.L7POLICY: l7policy,
                   constants.LISTENERS: listeners,
                   constants.LOADBALANCER: load_balancer})
        with tf_logging.DynamicLoggingListener(create_l7policy_tf,
                                               log=LOG):
            create_l7policy_tf.run()


    def delete_l7policy(self, l7policy_id):
        """Deletes an L7 policy.
        :param l7policy_id: ID of the l7policy to delete
        :returns: None
        :raises L7PolicyNotFound: The referenced l7policy was not found
        """
        l7policy = self._l7policy_repo.get(db_apis.get_session(),
                                           id=l7policy_id)

        load_balancer = l7policy.listener.load_balancer
        listeners = [l7policy.listener]

        delete_l7policy_tf = self._taskflow_load(
            self._l7policy_flows.get_delete_l7policy_flow(),
            store={constants.L7POLICY: l7policy,
                   constants.LISTENERS: listeners,
                   constants.LOADBALANCER: load_balancer})
        with tf_logging.DynamicLoggingListener(delete_l7policy_tf,
                                               log=LOG):
            delete_l7policy_tf.run()

    def update_l7policy(self, l7policy_id, l7policy_updates):
        """Updates an L7 policy.

        :param l7policy_id: ID of the l7policy to update
        :param l7policy_updates: Dict containing updated l7policy attributes
        :returns: None
        :raises L7PolicyNotFound: The referenced l7policy was not found
        """

        raise exceptions.NotImplementedError(
            user_fault_string='This provider does not support L7 yet',
            operator_fault_string='This provider does not support L7 yet')

    def create_l7rule(self, l7rule_id):
        """Creates an L7 Rule.

        :param l7rule_id: ID of the l7rule to create
        :returns: None
        :raises NoResultFound: Unable to find the object
        """
        l7rule = self._l7rule_repo.get(db_apis.get_session(),
                                       id=l7rule_id)
        if not l7rule:
            LOG.warning('Failed to fetch %s %s from DB. Retrying for up to '
                        '60 seconds.', 'l7rule', l7rule_id)
            raise db_exceptions.NoResultFound

        l7policy = l7rule.l7policy
        listeners = [l7policy.listener]
        load_balancer = l7policy.listener.load_balancer

        create_l7rule_tf = self._taskflow_load(
            self._l7rule_flows.get_create_l7rule_flow(),
            store={constants.L7RULE: l7rule,
                   constants.L7POLICY: l7policy,
                   constants.LISTENERS: listeners,
                   constants.LOADBALANCER: load_balancer})
        with tf_logging.DynamicLoggingListener(create_l7rule_tf,
                                               log=LOG):
            create_l7rule_tf.run()

    def delete_l7rule(self, l7rule_id):
        """Deletes an L7 rule.
        :param l7rule_id: ID of the l7rule to delete
        :returns: None
        :raises L7RuleNotFound: The referenced l7rule was not found
        """
        l7rule = self._l7rule_repo.get(db_apis.get_session(),
                                       id=l7rule_id)
        l7policy = l7rule.l7policy
        load_balancer = l7policy.listener.load_balancer
        listeners = [l7policy.listener]

        delete_l7rule_tf = self._taskflow_load(
            self._l7rule_flows.get_delete_l7rule_flow(),
            store={constants.L7RULE: l7rule,
                   constants.L7POLICY: l7policy,
                   constants.LISTENERS: listeners,
                   constants.LOADBALANCER: load_balancer})
        with tf_logging.DynamicLoggingListener(delete_l7rule_tf,
                                               log=LOG):
            delete_l7rule_tf.run()


    def update_l7rule(self, l7rule_id, l7rule_updates):
        """Updates an L7 rule.

        :param l7rule_id: ID of the l7rule to update
        :param l7rule_updates: Dict containing updated l7rule attributes
        :returns: None
        :raises L7RuleNotFound: The referenced l7rule was not found
        """

        raise exceptions.NotImplementedError(
            user_fault_string='This provider does not support L7 yet',
            operator_fault_string='This provider does not support L7 yet')

    def failover_amphora(self, amphora_id):
        """Perform failover operations for an amphora.

        :param amphora_id: ID for amphora to failover
        :returns: None
        :raises AmphoraNotFound: The referenced amphora was not found
        """

        raise exceptions.NotImplementedError(
            user_fault_string='This provider does not support Amphora '
                              'failover.',
            operator_fault_string='This provider does not support Amphora '
                                  'failover.')

    def failover_loadbalancer(self, load_balancer_id):
        """Perform failover operations for a load balancer.

        :param load_balancer_id: ID for load balancer to failover
        :returns: None
        :raises LBNotFound: The referenced load balancer was not found
        """

        raise exceptions.NotImplementedError(
            user_fault_string='This provider does not support loadbalancer '
                              'failover yet.',
            operator_fault_string='This provider does not support loadbalancer '
                                  'failover yet.')

    def amphora_cert_rotation(self, amphora_id):
        """Perform cert rotation for an amphora.

        :param amphora_id: ID for amphora to rotate
        :returns: None
        :raises AmphoraNotFound: The referenced amphora was not found
        """

        raise exceptions.NotImplementedError(
            user_fault_string='This provider does not support rotating Amphora '
                              'certs.',
            operator_fault_string='This provider does not support rotating '
                                  'Amphora certs. We will use preconfigured '
                                  'devices.')
