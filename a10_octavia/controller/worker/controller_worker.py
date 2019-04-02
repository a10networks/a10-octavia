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
from a10_octavia.controller.worker.flows import a10_load_balancer_flows

import acos_client
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class A10ControllerWorker(base_taskflow.BaseTaskFlowEngine):

    def __init__(self):
        self.c = acos_client.Client('138.197.107.20', acos_client.AXAPI_21, 'admin', 'a10')
        self._lb_repo = repo.LoadBalancerRepository()
        self._octavia_driver_db = driver_lib.DriverLibrary()
        self._lb_flows = a10_load_balancer_flows.LoadBalancerFlows()
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
        raise exceptions.NotImplementedError(
            user_fault_string='This provider does not support creating health'
                              'monitors yet.',
            operator_fault_string='This provider does not support creating '
                                  'health monitor yet.')

    def delete_health_monitor(self, health_monitor_id):
        """Deletes a health monitor.

        :param pool_id: ID of the pool to delete its health monitor
        :returns: None
        :raises HMNotFound: The referenced health monitor was not found
        """
        raise exceptions.NotImplementedError(
            user_fault_string='This provider does not support deleting health'
                              'monitors yet.',
            operator_fault_string='This provider does not support deleting '
                                  'health monitor yet.')

    def update_health_monitor(self, health_monitor_id, health_monitor_updates):
        """Updates a health monitor.

        :param pool_id: ID of the pool to have it's health monitor updated
        :param health_monitor_updates: Dict containing updated health monitor
        :returns: None
        :raises HMNotFound: The referenced health monitor was not found
        """
        raise exceptions.NotImplementedError(
            user_fault_string='This provider does not support updating health'
                              'monitors yet.',
            operator_fault_string='This provider does not support updating '
                                  'health monitor yet.')


    def create_listener(self, listener_id):
        """Creates a listener.

        :param listener_id: ID of the listener to create
        :returns: None
        :raises NoResultFound: Unable to find the object
        """

        raise exceptions.NotImplementedError(
            user_fault_string='This provider does not support creating '
                              'listeners yet',
            operator_fault_string='This provider does not support creating '
                                  'listeners yet')

    def delete_listener(self, listener_id):
        """Deletes a listener.

        :param listener_id: ID of the listener to delete
        :returns: None
        :raises ListenerNotFound: The referenced listener was not found
        """

        raise exceptions.NotImplementedError(
            user_fault_string='This provider does not support deleting '
                              'listeners yet',
            operator_fault_string='This provider does not support deleting '
                                  'listeners yet')

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
                 constants.LB_CREATE_NORMAL_PRIORITY,
                 constants.LOADBALANCER : lb,
                 }
        topology = CONF.controller_worker.loadbalancer_topology
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
        # No exception even when acos fails...
        try:
            r = self.c.slb.virtual_server.delete(load_balancer_id)
            status = { 'loadbalancers': [{"id": load_balancer_id,
                       "provisioning_status": constants.DELETED}]}
        except Exception as e:
            r = str(e)
            status = { 'loadbalancers': [{"id": load_balancer_id,
                       "provisioning_status": consts.ERROR }]}
        LOG.info("vThunder response: %s" % (r))
        LOG.info("Updating db with this status: %s" % (status))
        self._octavia_driver_db.update_loadbalancer_status(status)

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
                       "provisioning_status": consts.ERROR }]}
        LOG.info("Updating db with this status: %s" % (status))
        lb.update(db_apis.get_session(), loadbalancer.id,
                                      **update_dict)



    def create_member(self, member_id):
        """Creates a pool member.

        :param member_id: ID of the member to create
        :returns: None
        :raises NoSuitablePool: Unable to find the node pool
        """

        raise exceptions.NotImplementedError(
            user_fault_string='This provider does not support members yet',
            operator_fault_string='This provider does not support members yet')

    def delete_member(self, member_id):
        """Deletes a pool member.

        :param member_id: ID of the member to delete
        :returns: None
        :raises MemberNotFound: The referenced member was not found
        """

        raise exceptions.NotImplementedError(
            user_fault_string='This provider does not support members yet',
            operator_fault_string='This provider does not support members yet')

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

        raise exceptions.NotImplementedError(
            user_fault_string='This provider does not support pools yet',
            operator_fault_string='This provider does not support pools yet')

    def delete_pool(self, pool_id):
        """Deletes a node pool.

        :param pool_id: ID of the pool to delete
        :returns: None
        :raises PoolNotFound: The referenced pool was not found
        """

        raise exceptions.NotImplementedError(
            user_fault_string='This provider does not support pools yet',
            operator_fault_string='This provider does not support pools yet')

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

        raise exceptions.NotImplementedError(
            user_fault_string='This provider does not support L7 yet',
            operator_fault_string='This provider does not support L7 yet')

    def delete_l7policy(self, l7policy_id):
        """Deletes an L7 policy.

        :param l7policy_id: ID of the l7policy to delete
        :returns: None
        :raises L7PolicyNotFound: The referenced l7policy was not found
        """

        raise exceptions.NotImplementedError(
            user_fault_string='This provider does not support L7 yet',
            operator_fault_string='This provider does not support L7 yet')

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

        raise exceptions.NotImplementedError(
            user_fault_string='This provider does not support L7 yet',
            operator_fault_string='This provider does not support L7 yet')

    def delete_l7rule(self, l7rule_id):
        """Deletes an L7 rule.

        :param l7rule_id: ID of the l7rule to delete
        :returns: None
        :raises L7RuleNotFound: The referenced l7rule was not found
        """

        raise exceptions.NotImplementedError(
            user_fault_string='This provider does not support L7 yet',
            operator_fault_string='This provider does not support L7 yet')

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
