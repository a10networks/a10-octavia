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

import json
from sqlalchemy.orm import exc as db_exceptions
import tenacity
import time
import urllib3

from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import excutils
from taskflow.listeners import logging as tf_logging

from octavia.common import base_taskflow
from octavia.common import constants
from octavia.common import exceptions
from octavia.db import api as db_apis
from octavia.db import repositories as repo

from a10_octavia.common import a10constants
from a10_octavia.common import exceptions as a10_ex
from a10_octavia.common import utils
from a10_octavia.controller.worker.flows import a10_health_monitor_flows
from a10_octavia.controller.worker.flows import a10_l7policy_flows
from a10_octavia.controller.worker.flows import a10_l7rule_flows
from a10_octavia.controller.worker.flows import a10_listener_flows
from a10_octavia.controller.worker.flows import a10_load_balancer_flows
from a10_octavia.controller.worker.flows import a10_member_flows
from a10_octavia.controller.worker.flows import a10_pool_flows
from a10_octavia.controller.worker.flows import vthunder_flows
from a10_octavia.db import repositories as a10repo

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

RETRY_ATTEMPTS = 15
RETRY_INITIAL_DELAY = 1
RETRY_BACKOFF = 1
RETRY_MAX = 5

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


def ctx_cnt_dec(ctx_lock, ctx_map, key, is_reload_thread, flags):
    LOG.debug('--------------------------ctx_cnt_dec-----------------------------')
    if flags is not None and flags[0] is False:
        return

    ctx_lock.acquire()
    try:
        ctx = ctx_map.get(key)
        if ctx is None:
            raise

        normal_thrd_num, reload_thrd_num = ctx
        LOG.debug('vthunder %s ctx: normal_thrd(%d), reload_thrd(%d)',
                  key, normal_thrd_num, reload_thrd_num)

        if is_reload_thread:
            if reload_thrd_num > 0:
                reload_thrd_num = reload_thrd_num - 1
        else:
            if normal_thrd_num > 0:
                normal_thrd_num = normal_thrd_num - 1
        if flags is not None:
            flags[0] = False
        LOG.debug('vthunder %s ctx: normal_thrd(%d), reload_thrd(%d)',
                  key, normal_thrd_num, reload_thrd_num)
        ctx_map[key] = (normal_thrd_num, reload_thrd_num)
    except Exception:
        # unexpected error should not happen, reset counters here.
        LOG.error("Unable to find vThunder instance (%s) context, reset counters.", key)
        ctx_map[key] = (0, 0)
    ctx_lock.release()


def flow_notification_handler(state, details, **kwargs):
    LOG.debug('[flow_notification_handler] state: %s', state)
    key = kwargs.get('ctx_key', None)
    if state == 'SUCCESS' or state == 'REVERTED' or state == 'FAILURE':
        is_reload_thread = kwargs.get('is_reload_thread')
        ctx_lock = kwargs.get('ctx_lock')
        ctx_map = kwargs.get('ctx_map')
        ctx_flags = kwargs.get('ctx_flags')
        if ctx_lock is None or ctx_map is None:
            raise
        ctx_cnt_dec(ctx_lock, ctx_map, key, is_reload_thread, ctx_flags)


class A10ControllerWorker(base_taskflow.BaseTaskFlowEngine):

    def __init__(self):
        self._lb_repo = repo.LoadBalancerRepository()
        self._listener_repo = repo.ListenerRepository()
        self._pool_repo = repo.PoolRepository()
        self._member_repo = a10repo.MemberRepository()
        self._health_mon_repo = repo.HealthMonitorRepository()
        self._l7policy_repo = repo.L7PolicyRepository()
        self._l7rule_repo = repo.L7RuleRepository()
        self._lb_flows = a10_load_balancer_flows.LoadBalancerFlows()
        self._listener_flows = a10_listener_flows.ListenerFlows()
        self._pool_flows = a10_pool_flows.PoolFlows()
        self._member_flows = a10_member_flows.MemberFlows()
        self._health_monitor_flows = a10_health_monitor_flows.HealthMonitorFlows()
        self._l7policy_flows = a10_l7policy_flows.L7PolicyFlows()
        self._l7rule_flows = a10_l7rule_flows.L7RuleFlows()
        self._vthunder_flows = vthunder_flows.VThunderFlows()
        self._vthunder_repo = a10repo.VThunderRepository()
        self._flavor_repo = repo.FlavorRepository()
        self._flavor_profile_repo = repo.FlavorProfileRepository()
        self._exclude_result_logging_tasks = ()
        self.ctx_map = None
        self.ctx_lock = None
        super(A10ControllerWorker, self).__init__()

    def create_amphora(self):
        """Creates an Amphora.

        This is used to create spare amphora.

        :returns: amphora_id
        """
        create_vthunder_tf = self._taskflow_load(
            self._vthunder_flows.get_create_vthunder_flow(),
            store={constants.BUILD_TYPE_PRIORITY:
                   constants.LB_CREATE_SPARES_POOL_PRIORITY}
        )
        with tf_logging.DynamicLoggingListener(create_vthunder_tf, log=LOG):

            create_vthunder_tf.run()

        return create_vthunder_tf.storage.fetch('amphora')

    @tenacity.retry(
        retry=tenacity.retry_if_exception_type(db_exceptions.NoResultFound),
        wait=tenacity.wait_incrementing(
            RETRY_INITIAL_DELAY, RETRY_BACKOFF, RETRY_MAX),
        stop=tenacity.stop_after_attempt(RETRY_ATTEMPTS))
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

        topology = CONF.a10_controller_worker.loadbalancer_topology

        ctx_flags = [False]
        # rack flow _vthunder_busy_check() will always return False
        busy = self._vthunder_busy_check(health_mon.project_id, False, ctx_flags, load_balancer)
        try:
            create_hm_tf = self._taskflow_load(
                self._health_monitor_flows.get_create_health_monitor_flow(topology=topology),
                store={constants.HEALTH_MON: health_mon,
                       constants.POOL: pool,
                       constants.LISTENERS: listeners,
                       constants.LOADBALANCER: load_balancer,
                       a10constants.COMPUTE_BUSY: busy,
                       a10constants.WRITE_MEM_SHARED_PART: True})
            self._register_flow_notify_handler(create_hm_tf, health_mon.project_id, False,
                                               busy, ctx_flags, load_balancer)
            with tf_logging.DynamicLoggingListener(create_hm_tf,
                                                   log=LOG):
                create_hm_tf.run()
        finally:
            self._set_vthunder_available(health_mon.project_id, False, ctx_flags, load_balancer)

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

        topology = CONF.a10_controller_worker.loadbalancer_topology

        ctx_flags = [False]
        # rack flow _vthunder_busy_check() will always return False
        busy = self._vthunder_busy_check(health_mon.project_id, False, ctx_flags, load_balancer)
        try:
            delete_hm_tf = self._taskflow_load(
                self._health_monitor_flows.get_delete_health_monitor_flow(topology=topology),
                store={constants.HEALTH_MON: health_mon,
                       constants.POOL: pool,
                       constants.LISTENERS: listeners,
                       constants.LOADBALANCER: load_balancer,
                       a10constants.COMPUTE_BUSY: busy,
                       a10constants.WRITE_MEM_SHARED_PART: True})
            self._register_flow_notify_handler(delete_hm_tf, health_mon.project_id, False,
                                               busy, ctx_flags, load_balancer)
            with tf_logging.DynamicLoggingListener(delete_hm_tf,
                                                   log=LOG):
                delete_hm_tf.run()
        finally:
            self._set_vthunder_available(health_mon.project_id, False, ctx_flags, load_balancer)

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

        topology = CONF.a10_controller_worker.loadbalancer_topology

        ctx_flags = [False]
        # rack flow _vthunder_busy_check() will always return False
        busy = self._vthunder_busy_check(health_mon.project_id, False, ctx_flags, load_balancer)
        try:
            update_hm_tf = self._taskflow_load(
                self._health_monitor_flows.get_update_health_monitor_flow(topology=topology),
                store={constants.HEALTH_MON: health_mon,
                       constants.POOL: pool,
                       constants.LISTENERS: listeners,
                       constants.LOADBALANCER: load_balancer,
                       a10constants.COMPUTE_BUSY: busy,
                       constants.UPDATE_DICT: health_monitor_updates,
                       a10constants.WRITE_MEM_SHARED_PART: True})
            self._register_flow_notify_handler(update_hm_tf, health_mon.project_id, False,
                                               busy, ctx_flags, load_balancer)
            with tf_logging.DynamicLoggingListener(update_hm_tf,
                                                   log=LOG):
                update_hm_tf.run()
        finally:
            self._set_vthunder_available(health_mon.project_id, False, ctx_flags, load_balancer)

    @tenacity.retry(
        retry=tenacity.retry_if_exception_type(db_exceptions.NoResultFound),
        wait=tenacity.wait_incrementing(
            RETRY_INITIAL_DELAY, RETRY_BACKOFF, RETRY_MAX),
        stop=tenacity.stop_after_attempt(RETRY_ATTEMPTS))
    def create_listener(self, listener_id):
        """Function to create listener for A10 provider"""

        listener = self._listener_repo.get(db_apis.get_session(),
                                           id=listener_id)
        if not listener:
            LOG.warning('Failed to fetch %s %s from DB. Retrying for up to '
                        '60 seconds.', 'listener', listener_id)
            raise db_exceptions.NoResultFound

        load_balancer = listener.load_balancer
        parent_project_list = utils.get_parent_project_list()
        listener_parent_proj = utils.get_parent_project(listener.project_id)

        topology = CONF.a10_controller_worker.loadbalancer_topology

        ctx_flags = [False]
        try:
            if (listener.project_id in parent_project_list or
                    (listener_parent_proj and listener_parent_proj in parent_project_list)
                    or self._is_rack_flow(listener.project_id, loadbalancer=load_balancer)):
                create_listener_tf = self._taskflow_load(self._listener_flows.
                                                         get_rack_vthunder_create_listener_flow(
                                                             listener.project_id),
                                                         store={constants.LOADBALANCER:
                                                                load_balancer,
                                                                constants.LISTENER:
                                                                listener})
            else:
                busy = self._vthunder_busy_check(listener.project_id, False, ctx_flags,
                                                 load_balancer)
                create_listener_tf = self._taskflow_load(
                    self._listener_flows.get_create_listener_flow(topology=topology),
                    store={constants.LOADBALANCER: load_balancer,
                           a10constants.COMPUTE_BUSY: busy,
                           constants.LISTENER: listener})
                self._register_flow_notify_handler(create_listener_tf, listener.project_id, False,
                                                   busy, ctx_flags, load_balancer)

            with tf_logging.DynamicLoggingListener(create_listener_tf,
                                                   log=LOG):
                create_listener_tf.run()
        finally:
            self._set_vthunder_available(listener.project_id, False, ctx_flags, load_balancer)

    def delete_listener(self, listener_id):
        """Function to delete a listener for A10 provider"""

        listener = self._listener_repo.get(db_apis.get_session(),
                                           id=listener_id)
        load_balancer = listener.load_balancer

        topology = CONF.a10_controller_worker.loadbalancer_topology

        ctx_flags = [False]
        try:
            if self._is_rack_flow(listener.project_id, loadbalancer=load_balancer):
                delete_listener_tf = self._taskflow_load(
                    self._listener_flows.get_delete_rack_listener_flow(),
                    store={constants.LOADBALANCER: load_balancer,
                           constants.LISTENER: listener})
            else:
                busy = self._vthunder_busy_check(listener.project_id, False, ctx_flags,
                                                 load_balancer)
                delete_listener_tf = self._taskflow_load(
                    self._listener_flows.get_delete_listener_flow(topology),
                    store={constants.LOADBALANCER: load_balancer,
                           a10constants.COMPUTE_BUSY: busy,
                           constants.LISTENER: listener})
                self._register_flow_notify_handler(delete_listener_tf, listener.project_id, False,
                                                   busy, ctx_flags, load_balancer)
            with tf_logging.DynamicLoggingListener(delete_listener_tf,
                                                   log=LOG):
                delete_listener_tf.run()
        finally:
            self._set_vthunder_available(listener.project_id, False, ctx_flags, load_balancer)

    def update_listener(self, listener_id, listener_updates):
        """Function to Update a listener for A10 provider"""

        listener = None
        try:
            listener = self._get_db_obj_until_pending_update(
                self._listener_repo, listener_id)
        except tenacity.RetryError as e:
            LOG.warning('Listener did not go into %s in 60 seconds. '
                        'This either due to an in-progress Octavia upgrade '
                        'or an overloaded and failing database. Assuming '
                        'an upgrade is in progress and continuing.',
                        constants.PENDING_UPDATE)
            listener = e.last_attempt.result()

        load_balancer = listener.load_balancer

        topology = CONF.a10_controller_worker.loadbalancer_topology

        ctx_flags = [False]
        # rack flow _vthunder_busy_check() will always return False
        busy = self._vthunder_busy_check(listener.project_id, False, ctx_flags, load_balancer)
        try:
            update_listener_tf = self._taskflow_load(self._listener_flows.
                                                     get_update_listener_flow(topology),
                                                     store={constants.LISTENER:
                                                            listener,
                                                            a10constants.COMPUTE_BUSY: busy,
                                                            constants.LOADBALANCER:
                                                                load_balancer,
                                                            constants.UPDATE_DICT:
                                                                listener_updates
                                                            })
            self._register_flow_notify_handler(update_listener_tf, listener.project_id, False,
                                               busy, ctx_flags, load_balancer)
            with tf_logging.DynamicLoggingListener(update_listener_tf, log=LOG):
                update_listener_tf.run()
        finally:
            self._set_vthunder_available(listener.project_id, False, ctx_flags, load_balancer)

    @tenacity.retry(
        retry=tenacity.retry_if_exception_type(db_exceptions.NoResultFound),
        wait=tenacity.wait_incrementing(
            RETRY_INITIAL_DELAY, RETRY_BACKOFF, RETRY_MAX),
        stop=tenacity.stop_after_attempt(RETRY_ATTEMPTS))
    def create_load_balancer(self, load_balancer_id, flavor=None, ctx_map=None, ctx_lock=None):
        """Function to create load balancer for A10 provider"""

        lb = self._lb_repo.get(db_apis.get_session(), id=load_balancer_id)
        if not lb:
            LOG.warning('Failed to fetch %s %s from DB. Retrying for up to '
                        '60 seconds.', 'load_balancer', load_balancer_id)
            raise db_exceptions.NoResultFound

        flavor_id = lb.flavor_id if lb.flavor_id else CONF.a10_global.default_flavor_id
        if not flavor and flavor_id:
            flavor = self._get_flavor_data(flavor_id)

        store = {constants.LOADBALANCER_ID: load_balancer_id,
                 constants.VIP: lb.vip,
                 constants.BUILD_TYPE_PRIORITY:
                 constants.LB_CREATE_NORMAL_PRIORITY,
                 constants.FLAVOR: flavor,
                 constants.AMPS_DATA: []}

        topology = CONF.a10_controller_worker.loadbalancer_topology

        store[constants.UPDATE_DICT] = {
            constants.TOPOLOGY: topology,
            a10constants.FLAVOR_ID: flavor_id
        }

        ctx_flags = [False]
        try:
            if self._is_rack_flow(lb.project_id, flavor=flavor):
                vthunder_conf = CONF.hardware_thunder.devices.get(lb.project_id, None)
                device_dict = CONF.hardware_thunder.devices
                create_lb_flow = self._lb_flows.get_create_rack_vthunder_load_balancer_flow(
                    vthunder_conf=vthunder_conf, device_dict=device_dict,
                    topology=topology, listeners=lb.listeners)
                create_lb_tf = self._taskflow_load(create_lb_flow, store=store)
            else:
                busy = self._vthunder_busy_check(lb.project_id, True, ctx_flags, lb, store)
                create_lb_flow = self._lb_flows.get_create_load_balancer_flow(
                    load_balancer_id, topology, lb.project_id, listeners=lb.listeners)
                store.update([
                    (a10constants.COMPUTE_BUSY, busy),
                    (a10constants.VTHUNDER_CONFIG, None),
                    (a10constants.USE_DEVICE_FLAVOR, False)])
                create_lb_tf = self._taskflow_load(create_lb_flow, store=store)
                self._register_flow_notify_handler(create_lb_tf, lb.project_id, True,
                                                   busy, ctx_flags, lb)

            with tf_logging.DynamicLoggingListener(
                    create_lb_tf, log=LOG,
                    hide_inputs_outputs_of=self._exclude_result_logging_tasks):
                create_lb_tf.run()
        finally:
            self._set_vthunder_available(lb.project_id, True, ctx_flags, lb)

    def delete_load_balancer(self, load_balancer_id, cascade=False):
        """Function to delete load balancer for A10 provider"""
        lb = self._lb_repo.get(db_apis.get_session(),
                               id=load_balancer_id)
        vthunder = self._vthunder_repo.get_vthunder_from_lb(db_apis.get_session(),
                                                            load_balancer_id)
        deleteCompute = False
        ctx_flags = [False]
        busy = self._vthunder_busy_check(lb.project_id, True, ctx_flags, lb)
        try:
            if vthunder:
                deleteCompute = self._vthunder_repo.get_delete_compute_flag(db_apis.get_session(),
                                                                            vthunder.compute_id)

            if cascade:
                cascade = True
            if self._is_rack_flow(lb.project_id, loadbalancer=lb):
                vthunder_conf = CONF.hardware_thunder.devices.get(lb.project_id, None)
                device_dict = CONF.hardware_thunder.devices
                (flow, store) = self._lb_flows.get_delete_rack_vthunder_load_balancer_flow(
                    lb, cascade,
                    vthunder_conf=vthunder_conf, device_dict=device_dict)
                store.update({constants.LOADBALANCER: lb,
                              a10constants.COMPUTE_BUSY: busy,
                              constants.VIP: lb.vip,
                              constants.SERVER_GROUP_ID: lb.server_group_id})
            else:
                (flow, store) = self._lb_flows.get_delete_load_balancer_flow(
                    lb, deleteCompute, cascade)
                store.update({constants.LOADBALANCER: lb,
                              a10constants.COMPUTE_BUSY: busy,
                              constants.VIP: lb.vip,
                              constants.SERVER_GROUP_ID: lb.server_group_id,
                              a10constants.VTHUNDER_CONFIG: None,
                              a10constants.USE_DEVICE_FLAVOR: False,
                              a10constants.LB_COUNT_THUNDER: None,
                              a10constants.MEMBER_COUNT_THUNDER: None})

            delete_lb_tf = self._taskflow_load(flow, store=store)
            self._register_flow_notify_handler(delete_lb_tf, lb.project_id, True, busy,
                                               ctx_flags, lb)

            with tf_logging.DynamicLoggingListener(delete_lb_tf,
                                                   log=LOG):
                delete_lb_tf.run()
        finally:
            self._set_vthunder_available(lb.project_id, True, ctx_flags, lb)

    def update_load_balancer(self, load_balancer_id, load_balancer_updates):
        """Function to update load balancer for A10 provider"""

        lb = None
        try:
            lb = self._get_db_obj_until_pending_update(
                self._lb_repo, load_balancer_id)
        except tenacity.RetryError as e:
            LOG.warning('Load balancer did not go into %s in 60 seconds. '
                        'This either due to an in-progress Octavia upgrade '
                        'or an overloaded and failing database. Assuming '
                        'an upgrade is in progress and continuing.',
                        constants.PENDING_UPDATE)
            lb = e.last_attempt.result()

        listeners, _ = self._listener_repo.get_all(
            db_apis.get_session(),
            load_balancer_id=load_balancer_id)

        topology = CONF.a10_controller_worker.loadbalancer_topology

        ctx_flags = [False]
        try:
            if self._is_rack_flow(lb.project_id, loadbalancer=lb):
                vthunder_conf = CONF.hardware_thunder.devices.get(lb.project_id, None)
                device_dict = CONF.hardware_thunder.devices
                update_lb_tf = self._taskflow_load(
                    self._lb_flows.get_update_rack_load_balancer_flow(vthunder_conf=vthunder_conf,
                                                                      device_dict=device_dict,
                                                                      topology=topology),
                    store={constants.LOADBALANCER: lb,
                           constants.VIP: lb.vip,
                           constants.LISTENERS: listeners,
                           constants.UPDATE_DICT: load_balancer_updates})
            else:
                busy = self._vthunder_busy_check(lb.project_id, False, ctx_flags, lb)
                update_lb_tf = self._taskflow_load(
                    self._lb_flows.get_update_load_balancer_flow(topology=topology),
                    store={constants.LOADBALANCER: lb,
                           constants.LOADBALANCER_ID: lb.id,
                           constants.VIP: lb.vip,
                           a10constants.COMPUTE_BUSY: busy,
                           constants.LISTENERS: listeners,
                           constants.UPDATE_DICT: load_balancer_updates,
                           a10constants.VTHUNDER_CONFIG: None,
                           a10constants.USE_DEVICE_FLAVOR: False})
                self._register_flow_notify_handler(update_lb_tf, lb.project_id, False,
                                                   busy, ctx_flags, lb)

            with tf_logging.DynamicLoggingListener(update_lb_tf,
                                                   log=LOG):
                update_lb_tf.run()
        finally:
            self._set_vthunder_available(lb.project_id, False, ctx_flags, lb)

    @tenacity.retry(
        retry=tenacity.retry_if_exception_type(db_exceptions.NoResultFound),
        wait=tenacity.wait_incrementing(
            RETRY_INITIAL_DELAY, RETRY_BACKOFF, RETRY_MAX),
        stop=tenacity.stop_after_attempt(RETRY_ATTEMPTS))
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

        topology = CONF.a10_controller_worker.loadbalancer_topology
        parent_project_list = utils.get_parent_project_list()
        member_parent_proj = utils.get_parent_project(
            member.project_id)

        ctx_flags = [False]
        try:
            if (member.project_id in parent_project_list or
                    (member_parent_proj and member_parent_proj in parent_project_list)
                    or self._is_rack_flow(member.project_id, loadbalancer=load_balancer)):
                vthunder_conf = CONF.hardware_thunder.devices.get(load_balancer.project_id, None)
                device_dict = CONF.hardware_thunder.devices
                create_member_tf = self._taskflow_load(
                    self._member_flows.get_rack_vthunder_create_member_flow(
                        vthunder_conf=vthunder_conf, device_dict=device_dict),
                    store={
                        constants.MEMBER: member,
                        constants.LISTENERS: listeners,
                        constants.LOADBALANCER: load_balancer,
                        constants.POOL: pool})
            else:
                busy = self._vthunder_busy_check(member.project_id, True, ctx_flags, load_balancer)
                create_member_tf = self._taskflow_load(
                    self._member_flows.get_create_member_flow(topology=topology),
                    store={constants.MEMBER: member,
                           constants.LISTENERS:
                           listeners,
                           constants.LOADBALANCER:
                           load_balancer,
                           a10constants.COMPUTE_BUSY: busy,
                           constants.POOL: pool,
                           a10constants.VTHUNDER_CONFIG: None,
                           a10constants.USE_DEVICE_FLAVOR: False})
                self._register_flow_notify_handler(create_member_tf, member.project_id, True,
                                                   busy, ctx_flags, load_balancer)

            with tf_logging.DynamicLoggingListener(create_member_tf,
                                                   log=LOG):
                create_member_tf.run()
        finally:
            self._set_vthunder_available(member.project_id, True, ctx_flags, load_balancer)

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
        topology = CONF.a10_controller_worker.loadbalancer_topology

        ctx_flags = [False]
        try:
            if self._is_rack_flow(member.project_id, loadbalancer=load_balancer):
                vthunder_conf = CONF.hardware_thunder.devices.get(load_balancer.project_id, None)
                device_dict = CONF.hardware_thunder.devices
                delete_member_tf = self._taskflow_load(
                    self._member_flows.get_rack_vthunder_delete_member_flow(
                        vthunder_conf=vthunder_conf, device_dict=device_dict),
                    store={constants.MEMBER: member, constants.LISTENERS: listeners,
                           constants.LOADBALANCER: load_balancer, constants.POOL: pool}
                )
            else:
                busy = self._vthunder_busy_check(member.project_id, True, ctx_flags, load_balancer)
                delete_member_tf = self._taskflow_load(
                    self._member_flows.get_delete_member_flow(topology=topology),
                    store={constants.MEMBER: member, constants.LISTENERS: listeners,
                           constants.LOADBALANCER: load_balancer, a10constants.COMPUTE_BUSY: busy,
                           constants.POOL: pool, a10constants.VTHUNDER_CONFIG: None,
                           a10constants.USE_DEVICE_FLAVOR: False,
                           a10constants.LB_COUNT_THUNDER: None,
                           a10constants.MEMBER_COUNT_THUNDER: None}
                )
                self._register_flow_notify_handler(delete_member_tf, member.project_id, True,
                                                   busy, ctx_flags, load_balancer)
            with tf_logging.DynamicLoggingListener(delete_member_tf,
                                                   log=LOG):
                delete_member_tf.run()
        finally:
            self._set_vthunder_available(member.project_id, True, ctx_flags, load_balancer)

    def _is_batch_valid(self, old_member_ids, new_member_ids,
                        updated_member_ids, member_collision_map):
        valid = True
        for mem_id, member_col in member_collision_map.items():
            member, mem_cnt = member_col
            mem_ip = member.ip_address
            mem_port = member.protocol_port
            if mem_cnt > 1:
                if mem_id in old_member_ids:
                    error_msg = ("Duplicate members with id {} and IP {} and port {} "
                                 "found in member database.".format(mem_id, mem_ip, mem_port))
                if mem_id in new_member_ids or mem_id in updated_member_ids:
                    error_msg = ("Duplicate members with id {} and IP {} and port {} "
                                 "found in batch update request.".format(mem_id, mem_ip, mem_port))
                LOG.warning(error_msg)
                valid = False
        return valid

    def _rollback_members(self, old_member_ids, new_member_ids,
                          updated_member_ids, load_balancer,
                          listeners, pool):
        set_o_ids = set(old_member_ids)
        set_u_ids = set(updated_member_ids)
        set_n_ids = set(new_member_ids)

        current_member_ids = set_o_ids.union(set_u_ids)

        current_members = [self._member_repo.get(db_apis.get_session(), id=mid)
                           for mid in current_member_ids]

        for mem in current_members:
            # Rollback status to prevent pending state lock
            self._member_repo.update(db_apis.get_session(), mem.id,
                                     provisioning_status=constants.ACTIVE)
            LOG.info("Member with id {} and ip {} and port {} slated for "
                     "batch update have been set to ACTIVE state.".format(
                         mem.id, mem.ip_address, mem.protocol_port))

        new_members = [self._member_repo.get(db_apis.get_session(), id=mid)
                       for mid in set_n_ids]

        for mem in new_members:
            current_member_ids.add(mem.id)
            LOG.info("Member with id {} and ip {} and port {} "
                     "slated for creation under batch update "
                     "has been deleted.".format(mem.id, mem.ip_address, mem.protocol_port))
        self._member_repo.delete_members(db_apis.get_session(), set_n_ids)

        if pool is not None:
            self._pool_repo.update(db_apis.get_session(), pool.id,
                                   provisioning_status=constants.ACTIVE)
        if listeners is not None:
            for listener in listeners:
                self._listener_repo.update(db_apis.get_session(),
                                           listener.id,
                                           provisioning_status=constants.ACTIVE)
        if load_balancer is not None:
            self._lb_repo.update(db_apis.get_session(),
                                 load_balancer.id,
                                 provisioning_status=constants.ACTIVE)

    @tenacity.retry(
        retry=tenacity.retry_if_exception_type(db_exceptions.NoResultFound),
        wait=tenacity.wait_incrementing(
            RETRY_INITIAL_DELAY, RETRY_BACKOFF, RETRY_MAX),
        stop=tenacity.stop_after_attempt(RETRY_ATTEMPTS))
    def batch_update_members(self, old_member_ids, new_member_ids,
                             updated_members_req):

        updated_member_ids = [m.get('id') for m in updated_members_req]
        updated_member_models = [self._member_repo.get(db_apis.get_session(), id=mid)
                                 for mid in updated_member_ids]

        old_members = [self._member_repo.get(db_apis.get_session(), id=mid)
                       for mid in old_member_ids]

        new_members = [self._member_repo.get(db_apis.get_session(), id=mid)
                       for mid in new_member_ids]

        if old_members:
            pool = old_members[0].pool
        elif new_members:
            pool = new_members[0].pool
        else:
            pool = updated_member_models[0].pool

        load_balancer = pool.load_balancer
        listeners = pool.listeners

        modified_members = old_members + updated_member_models + new_members
        member_collision_map = {}
        for mem in modified_members:
            mem_id = mem[0] if type(mem) == tuple else mem.id
            if member_collision_map.get(mem_id):
                member_collision_map[mem_id][1] += 1
            else:
                member_collision_map[mem_id] = [mem, 1]

        if not self._is_batch_valid(old_member_ids, new_member_ids,
                                    updated_member_ids, member_collision_map):
            self._rollback_members(old_member_ids, new_member_ids,
                                   updated_member_ids, load_balancer,
                                   listeners, pool)
            LOG.warning("Due to a failed batch update caused by duplicate member definitions, "
                        "the members defined in the update are now out-of-sync with the "
                        "ACOS device. Please issue a corrected update or "
                        "delete the affected members.")
            raise a10_ex.DuplicateMembersInBatchUpdate

        # The API may not have commited all of the new member records yet.
        # Make sure we retry looking them up.
        if None in new_members or len(new_members) != len(new_member_ids):
            LOG.warning('Failed to fetch one of the new members from DB. '
                        'Retrying for up to 60 seconds.')
            raise db_exceptions.NoResultFound

        updated_members = []
        for i in range(len(updated_members_req)):
            updated_members.append((updated_member_models[i], updated_members_req[i]))

        ctx_flags = [False]
        try:
            if self._is_rack_flow(pool.project_id, loadbalancer=load_balancer):
                vthunder_conf = CONF.hardware_thunder.devices.get(load_balancer.project_id, None)
                device_dict = CONF.hardware_thunder.devices
                batch_update_members_tf = self._taskflow_load(
                    self._member_flows.get_rack_vthunder_batch_update_members_flow(
                        old_members, new_members, updated_members,
                        vthunder_conf, device_dict),
                    store={constants.LISTENERS: listeners,
                           constants.LOADBALANCER: load_balancer,
                           constants.POOL: pool})
            else:
                topology = CONF.a10_controller_worker.loadbalancer_topology
                busy = self._vthunder_busy_check(load_balancer.project_id, True,
                                                 ctx_flags, load_balancer)
                batch_update_members_tf = self._taskflow_load(
                    self._member_flows.get_batch_update_members_flow(
                        old_members, new_members, updated_members, topology),
                    store={constants.LISTENERS: listeners,
                           constants.LOADBALANCER: load_balancer,
                           a10constants.COMPUTE_BUSY: busy,
                           constants.POOL: pool,
                           a10constants.VTHUNDER_CONFIG: None,
                           a10constants.USE_DEVICE_FLAVOR: False,
                           a10constants.LB_COUNT_THUNDER: None,
                           a10constants.MEMBER_COUNT_THUNDER: None}
                )
                self._register_flow_notify_handler(batch_update_members_tf,
                                                   load_balancer.project_id, True,
                                                   busy, ctx_flags, load_balancer)

            with tf_logging.DynamicLoggingListener(batch_update_members_tf,
                                                   log=LOG):
                batch_update_members_tf.run()
        finally:
            self._set_vthunder_available(pool.project_id, True, ctx_flags, load_balancer)

    def update_member(self, member_id, member_updates):
        """Updates a pool member.

        :param member_id: ID of the member to update
        :param member_updates: Dict containing updated member attributes
        :returns: None
        :raises MemberNotFound: The referenced member was not found
        """
        member = None
        try:
            member = self._get_db_obj_until_pending_update(
                self._member_repo, member_id)
        except tenacity.RetryError as e:
            LOG.warning('Member did not go into %s in 60 seconds. '
                        'This either due to an in-progress Octavia upgrade '
                        'or an overloaded and failing database. Assuming '
                        'an upgrade is in progress and continuing.',
                        constants.PENDING_UPDATE)
            member = e.last_attempt.result()

        pool = member.pool
        listeners = pool.listeners
        load_balancer = pool.load_balancer

        topology = CONF.a10_controller_worker.loadbalancer_topology

        ctx_flags = [False]
        try:
            if self._is_rack_flow(member.project_id, loadbalancer=load_balancer):
                vthunder_conf = CONF.hardware_thunder.devices.get(load_balancer.project_id, None)
                device_dict = CONF.hardware_thunder.devices
                update_member_tf = self._taskflow_load(
                    self._member_flows.get_rack_vthunder_update_member_flow(
                        vthunder_conf=vthunder_conf, device_dict=device_dict),
                    store={constants.MEMBER: member,
                           constants.LISTENERS: listeners,
                           constants.LOADBALANCER: load_balancer,
                           constants.POOL: pool,
                           constants.UPDATE_DICT: member_updates})
            else:
                busy = self._vthunder_busy_check(member.project_id, False, ctx_flags,
                                                 load_balancer)
                update_member_tf = self._taskflow_load(
                    self._member_flows.get_update_member_flow(topology=topology),
                    store={constants.MEMBER: member,
                           constants.LISTENERS: listeners,
                           constants.LOADBALANCER: load_balancer,
                           constants.LOADBALANCER_ID: load_balancer.id,
                           a10constants.COMPUTE_BUSY: busy,
                           constants.POOL: pool,
                           constants.UPDATE_DICT: member_updates,
                           a10constants.VTHUNDER_CONFIG: None,
                           a10constants.USE_DEVICE_FLAVOR: False})
                self._register_flow_notify_handler(update_member_tf, member.project_id, False,
                                                   busy, ctx_flags, load_balancer)

            with tf_logging.DynamicLoggingListener(update_member_tf,
                                                   log=LOG):
                update_member_tf.run()
        finally:
            self._set_vthunder_available(member.project_id, False, ctx_flags, load_balancer)

    @tenacity.retry(
        retry=tenacity.retry_if_exception_type(db_exceptions.NoResultFound),
        wait=tenacity.wait_incrementing(
            RETRY_INITIAL_DELAY, RETRY_BACKOFF, RETRY_MAX),
        stop=tenacity.stop_after_attempt(RETRY_ATTEMPTS))
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
        default_listener = None
        if listeners:
            default_listener = pool.listeners[0]
        load_balancer = pool.load_balancer

        topology = CONF.a10_controller_worker.loadbalancer_topology

        ctx_flags = [False]
        # rack flow _vthunder_busy_check() will always return False
        busy = self._vthunder_busy_check(pool.project_id, False, ctx_flags, load_balancer)
        try:
            create_pool_tf = self._taskflow_load(self._pool_flows.
                                                 get_create_pool_flow(topology=topology),
                                                 store={constants.POOL: pool,
                                                        constants.LISTENERS:
                                                            listeners,
                                                        constants.LISTENER: default_listener,
                                                        constants.LOADBALANCER:
                                                            load_balancer,
                                                        a10constants.COMPUTE_BUSY: busy})
            self._register_flow_notify_handler(create_pool_tf, pool.project_id, False,
                                               busy, ctx_flags, load_balancer)
            with tf_logging.DynamicLoggingListener(create_pool_tf,
                                                   log=LOG):
                create_pool_tf.run()
        finally:
            self._set_vthunder_available(pool.project_id, False, ctx_flags, load_balancer)

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
        default_listener = None
        if listeners:
            default_listener = pool.listeners[0]
        members = pool.members
        health_monitor = pool.health_monitor
        mem_count = self._member_repo.get_member_count(
            db_apis.get_session(),
            project_id=pool.project_id)
        mem_count = mem_count - len(members) + 1
        store = {constants.POOL: pool, constants.LISTENERS: listeners,
                 constants.LISTENER: default_listener,
                 constants.LOADBALANCER: load_balancer,
                 constants.HEALTH_MON: health_monitor,
                 a10constants.MEMBER_COUNT: mem_count}

        ctx_flags = [False]
        try:
            if self._is_rack_flow(pool.project_id, loadbalancer=load_balancer):
                vthunder_conf = CONF.hardware_thunder.devices.get(load_balancer.project_id, None)
                device_dict = CONF.hardware_thunder.devices
                store.update([(a10constants.VTHUNDER_CONFIG, vthunder_conf),
                              (a10constants.DEVICE_CONFIG_DICT, device_dict)])
                delete_pool_tf = self._taskflow_load(
                    self._pool_flows.get_delete_pool_rack_flow(
                        members, health_monitor, store), store=store)
            else:
                topology = CONF.a10_controller_worker.loadbalancer_topology
                store.update({a10constants.USE_DEVICE_FLAVOR: False,
                              a10constants.POOLS: None})
                busy = self._vthunder_busy_check(pool.project_id, False, ctx_flags,
                                                 load_balancer, store)
                delete_pool_tf = self._taskflow_load(
                    self._pool_flows.get_delete_pool_flow(
                        members, health_monitor, store, topology), store=store)
                self._register_flow_notify_handler(delete_pool_tf, pool.project_id, False,
                                                   busy, ctx_flags, load_balancer)

            with tf_logging.DynamicLoggingListener(delete_pool_tf,
                                                   log=LOG):
                delete_pool_tf.run()
        finally:
            self._set_vthunder_available(pool.project_id, False, ctx_flags, load_balancer)

    def update_pool(self, pool_id, pool_updates):
        """Updates a node pool.

        :param pool_id: ID of the pool to update
        :param pool_updates: Dict containing updated pool attributes
        :returns: None
        :raises PoolNotFound: The referenced pool was not found
        """

        pool = None
        try:
            pool = self._get_db_obj_until_pending_update(
                self._pool_repo, pool_id)
        except tenacity.RetryError as e:
            LOG.warning('Pool did not go into %s in 60 seconds. '
                        'This either due to an in-progress Octavia upgrade '
                        'or an overloaded and failing database. Assuming '
                        'an upgrade is in progress and continuing.',
                        constants.PENDING_UPDATE)
            pool = e.last_attempt.result()

        listeners = pool.listeners
        default_listener = None
        if listeners:
            default_listener = pool.listeners[0]
        load_balancer = pool.load_balancer

        topology = CONF.a10_controller_worker.loadbalancer_topology

        ctx_flags = [False]
        # rack flow _vthunder_busy_check() will always return False
        busy = self._vthunder_busy_check(pool.project_id, False, ctx_flags, load_balancer)
        try:
            update_pool_tf = self._taskflow_load(self._pool_flows.
                                                 get_update_pool_flow(topology),
                                                 store={constants.POOL: pool,
                                                        constants.LISTENERS:
                                                            listeners,
                                                        constants.LISTENER: default_listener,
                                                        constants.LOADBALANCER:
                                                            load_balancer,
                                                        a10constants.COMPUTE_BUSY: busy,
                                                        constants.UPDATE_DICT:
                                                            pool_updates})
            self._register_flow_notify_handler(update_pool_tf, pool.project_id, False,
                                               busy, ctx_flags, load_balancer)
            with tf_logging.DynamicLoggingListener(update_pool_tf,
                                                   log=LOG):
                update_pool_tf.run()
        finally:
            self._set_vthunder_available(pool.project_id, False, ctx_flags, load_balancer)

    @tenacity.retry(
        retry=tenacity.retry_if_exception_type(db_exceptions.NoResultFound),
        wait=tenacity.wait_incrementing(
            RETRY_INITIAL_DELAY, RETRY_BACKOFF, RETRY_MAX),
        stop=tenacity.stop_after_attempt(RETRY_ATTEMPTS))
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

        topology = CONF.a10_controller_worker.loadbalancer_topology

        ctx_flags = [False]
        # rack flow _vthunder_busy_check() will always return False
        busy = self._vthunder_busy_check(l7policy.project_id, False, ctx_flags, load_balancer)
        try:
            create_l7policy_tf = self._taskflow_load(
                self._l7policy_flows.get_create_l7policy_flow(topology=topology),
                store={constants.L7POLICY: l7policy,
                       constants.LISTENERS: listeners,
                       constants.LOADBALANCER: load_balancer,
                       a10constants.COMPUTE_BUSY: busy})
            self._register_flow_notify_handler(create_l7policy_tf, l7policy.project_id, False,
                                               busy, ctx_flags, load_balancer)
            with tf_logging.DynamicLoggingListener(create_l7policy_tf,
                                                   log=LOG):
                create_l7policy_tf.run()
        finally:
            self._set_vthunder_available(l7policy.project_id, False, ctx_flags, load_balancer)

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

        topology = CONF.a10_controller_worker.loadbalancer_topology

        ctx_flags = [False]
        # rack flow _vthunder_busy_check() will always return False
        busy = self._vthunder_busy_check(l7policy.project_id, False, ctx_flags, load_balancer)
        try:
            delete_l7policy_tf = self._taskflow_load(
                self._l7policy_flows.get_delete_l7policy_flow(topology=topology),
                store={constants.L7POLICY: l7policy,
                       constants.LISTENERS: listeners,
                       constants.LOADBALANCER: load_balancer,
                       a10constants.COMPUTE_BUSY: busy})
            self._register_flow_notify_handler(delete_l7policy_tf, l7policy.project_id, False,
                                               busy, ctx_flags, load_balancer)
            with tf_logging.DynamicLoggingListener(delete_l7policy_tf,
                                                   log=LOG):
                delete_l7policy_tf.run()
        finally:
            self._set_vthunder_available(l7policy.project_id, False, ctx_flags, load_balancer)

    def update_l7policy(self, l7policy_id, l7policy_updates):
        """Updates an L7 policy.

        :param l7policy_id: ID of the l7policy to update
        :param l7policy_updates: Dict containing updated l7policy attributes
        :returns: None
        :raises L7PolicyNotFound: The referenced l7policy was not found
        """

        l7policy = None
        try:
            l7policy = self._get_db_obj_until_pending_update(
                self._l7policy_repo, l7policy_id)
        except tenacity.RetryError as e:
            LOG.warning('L7 policy did not go into %s in 60 seconds. '
                        'This either due to an in-progress Octavia upgrade '
                        'or an overloaded and failing database. Assuming '
                        'an upgrade is in progress and continuing.',
                        constants.PENDING_UPDATE)
            l7policy = e.last_attempt.result()

        listeners = [l7policy.listener]
        load_balancer = l7policy.listener.load_balancer

        topology = CONF.a10_controller_worker.loadbalancer_topology

        ctx_flags = [False]
        # rack flow _vthunder_busy_check() will always return False
        busy = self._vthunder_busy_check(l7policy.project_id, False, ctx_flags, load_balancer)
        try:
            update_l7policy_tf = self._taskflow_load(
                self._l7policy_flows.get_update_l7policy_flow(topology=topology),
                store={constants.L7POLICY: l7policy,
                       constants.LISTENERS: listeners,
                       constants.LOADBALANCER: load_balancer,
                       a10constants.COMPUTE_BUSY: busy,
                       constants.UPDATE_DICT: l7policy_updates})
            self._register_flow_notify_handler(update_l7policy_tf, l7policy.project_id, False,
                                               busy, ctx_flags, load_balancer)
            with tf_logging.DynamicLoggingListener(update_l7policy_tf,
                                                   log=LOG):
                update_l7policy_tf.run()
        finally:
            self._set_vthunder_available(l7policy.project_id, False, ctx_flags, load_balancer)

    @tenacity.retry(
        retry=tenacity.retry_if_exception_type(db_exceptions.NoResultFound),
        wait=tenacity.wait_incrementing(
            RETRY_INITIAL_DELAY, RETRY_BACKOFF, RETRY_MAX),
        stop=tenacity.stop_after_attempt(RETRY_ATTEMPTS))
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

        topology = CONF.a10_controller_worker.loadbalancer_topology

        ctx_flags = [False]
        # rack flow _vthunder_busy_check() will always return False
        busy = self._vthunder_busy_check(l7rule.project_id, False, ctx_flags, load_balancer)
        try:
            create_l7rule_tf = self._taskflow_load(
                self._l7rule_flows.get_create_l7rule_flow(topology=topology),
                store={constants.L7RULE: l7rule,
                       constants.L7POLICY: l7policy,
                       constants.LISTENERS: listeners,
                       constants.LOADBALANCER: load_balancer,
                       a10constants.COMPUTE_BUSY: busy})
            self._register_flow_notify_handler(create_l7rule_tf, l7rule.project_id, False,
                                               busy, ctx_flags, load_balancer)
            with tf_logging.DynamicLoggingListener(create_l7rule_tf,
                                                   log=LOG):
                create_l7rule_tf.run()
        finally:
            self._set_vthunder_available(l7rule.project_id, False, ctx_flags, load_balancer)

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

        topology = CONF.a10_controller_worker.loadbalancer_topology

        ctx_flags = [False]
        # rack flow _vthunder_busy_check() will always return False
        busy = self._vthunder_busy_check(l7rule.project_id, False, ctx_flags, load_balancer)
        try:
            delete_l7rule_tf = self._taskflow_load(
                self._l7rule_flows.get_delete_l7rule_flow(topology=topology),
                store={constants.L7RULE: l7rule,
                       constants.L7POLICY: l7policy,
                       constants.LISTENERS: listeners,
                       constants.LOADBALANCER: load_balancer,
                       a10constants.COMPUTE_BUSY: busy})
            self._register_flow_notify_handler(delete_l7rule_tf, l7rule.project_id, False,
                                               busy, ctx_flags, load_balancer)
            with tf_logging.DynamicLoggingListener(delete_l7rule_tf,
                                                   log=LOG):
                delete_l7rule_tf.run()
        finally:
            self._set_vthunder_available(l7rule.project_id, False, ctx_flags, load_balancer)

    def update_l7rule(self, l7rule_id, l7rule_updates):
        """Updates an L7 rule.

        :param l7rule_id: ID of the l7rule to update
        :param l7rule_updates: Dict containing updated l7rule attributes
        :returns: None
        :raises L7RuleNotFound: The referenced l7rule was not found
        """
        l7rule = None
        try:
            l7rule = self._get_db_obj_until_pending_update(
                self._l7rule_repo, l7rule_id)
        except tenacity.RetryError as e:
            LOG.warning('L7 rule did not go into %s in 60 seconds. '
                        'This either due to an in-progress Octavia upgrade '
                        'or an overloaded and failing database. Assuming '
                        'an upgrade is in progress and continuing.',
                        constants.PENDING_UPDATE)
            l7rule = e.last_attempt.result()

        l7policy = l7rule.l7policy
        listeners = [l7policy.listener]
        load_balancer = l7policy.listener.load_balancer

        topology = CONF.a10_controller_worker.loadbalancer_topology

        ctx_flags = [False]
        # rack flow _vthunder_busy_check() will always return False
        busy = self._vthunder_busy_check(l7rule.project_id, False, ctx_flags, load_balancer)
        try:
            update_l7rule_tf = self._taskflow_load(
                self._l7rule_flows.get_update_l7rule_flow(topology=topology),
                store={constants.L7RULE: l7rule,
                       constants.L7POLICY: l7policy,
                       constants.LISTENERS: listeners,
                       constants.LOADBALANCER: load_balancer,
                       a10constants.COMPUTE_BUSY: busy,
                       constants.UPDATE_DICT: l7rule_updates})
            self._register_flow_notify_handler(update_l7rule_tf, l7rule.project_id, False,
                                               busy, ctx_flags, load_balancer)
            with tf_logging.DynamicLoggingListener(update_l7rule_tf,
                                                   log=LOG):
                update_l7rule_tf.run()
        finally:
            self._set_vthunder_available(l7rule.project_id, False, ctx_flags, load_balancer)

    def _switch_roles_for_ha_flow(self, vthunder):
        lock_session = db_apis.get_session(autocommit=False)
        if vthunder.role == constants.ROLE_MASTER:
            LOG.info("Master vThunder %s has failed, searching for existing backup vThunder.",
                     vthunder.ip_address)
            backup_vthunder = self._vthunder_repo.get_backup_vthunder_from_lb(
                lock_session,
                lb_id=vthunder.loadbalancer_id)
            if backup_vthunder:
                LOG.info("Making Backup vThunder %s as MASTER NOW",
                         backup_vthunder.ip_address)
                self._vthunder_repo.update(
                    lock_session,
                    backup_vthunder.id, role=constants.ROLE_MASTER)

                LOG.info("Putting %s to failed vThunders",
                         vthunder.ip_address)

                self._vthunder_repo.update(
                    lock_session,
                    vthunder.id, role=constants.ROLE_BACKUP, status=a10constants.FAILED)

                lock_session.commit()
                LOG.info("vThunder %s's status is FAILED", vthunder.ip_address)
                status = {'vthunders': [{"id": vthunder.vthunder_id,
                                         "status": a10constants.FAILED,
                                         "ip_address": vthunder.ip_address}]}
                LOG.info(str(status))
            else:
                LOG.warning("No backup found for failed MASTER %s", vthunder.ip_address)

        elif vthunder.role == constants.ROLE_BACKUP:
            LOG.info("BACKUP vThunder %s has failed", vthunder.ip_address)
            self._vthunder_repo.update(
                lock_session,
                vthunder.id, status=a10constants.FAILED)
            LOG.info("vThunder %s's status is FAILED", vthunder.ip_address)
            status = {'vthunders': [{"id": vthunder.vthunder_id,
                                     "status": a10constants.FAILED,
                                     "ip_address": vthunder.ip_address}]}
            lock_session.commit()
            LOG.info(str(status))
        # TODO(ytsai-a10) check if we need to call lock_session.close() to release db lock

    def failover_amphora(self, vthunder_id):
        """Perform failover operations for an vThunder.
        :param vthunder_id: ID for vThunder to failover
        :returns: None
        """
        try:
            vthunder = self._vthunder_repo.get(db_apis.get_session(),
                                               vthunder_id=vthunder_id)
            if not vthunder:
                LOG.warning("Could not fetch vThunder %s from DB, ignoring "
                            "failover request.", vthunder.vthunder_id)
                return

            LOG.info("Starting Failover process on %s", vthunder.ip_address)
            # feature : db role switching for HA flow
            self._switch_roles_for_ha_flow(vthunder)

            # TODO(hthompson6) delete failed one
            # TODO(hthompson6) boot up new amps
            # TODO(hthompson6) vrrp sync

        except Exception as e:
            with excutils.save_and_reraise_exception():
                LOG.error("vThunder %(id)s failover exception: %(exc)s",
                          {'id': vthunder_id, 'exc': e})

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

    def _get_db_obj_until_pending_update(self, repo, id):
        return repo.get(db_apis.get_session(), id=id)

    def perform_write_memory(self, thunders):
        """Perform write memory operations for a thunders

        :param thunders: group of thunder objects
        :returns: None
        """
        store = {a10constants.WRITE_MEM_SHARED_PART: True}

        for vthunder in thunders:
            delete_compute = False
            if vthunder.status == 'DELETED' and vthunder.compute_id is not None:
                delete_compute = self._vthunder_repo.get_delete_compute_flag(db_apis.get_session(),
                                                                             vthunder.compute_id)
            try:
                write_mem_tf = self._taskflow_load(
                    self._vthunder_flows.get_write_memory_flow(vthunder, store, delete_compute),
                    store=store)

                with tf_logging.DynamicLoggingListener(write_mem_tf,
                                                       log=LOG):
                    write_mem_tf.run()
            except Exception:
                # continue on other thunders (assume exception is logged)
                pass

    def perform_reload_check(self, thunders):
        """Perform check for thunders see if thunder reload before write memory

        :param thunders: group of thunder objects
        :returns: None
        """
        store = {}
        for vthunder in thunders:
            try:
                reload_check_tf = self._taskflow_load(
                    self._vthunder_flows.get_reload_check_flow(vthunder, store),
                    store=store)
                with tf_logging.DynamicLoggingListener(reload_check_tf, log=LOG):
                    reload_check_tf.run()
            except Exception:
                # continue on other thunders (assume exception is logged)
                pass

    def a10_worker_ctx_init(self, ctx_map, ctx_lock):
        self.ctx_map = ctx_map
        self.ctx_lock = ctx_lock

    def _is_rack_flow(self, key, loadbalancer=None, flavor=None):
        if self.ctx_map is None or self.ctx_lock is None:
            return True
        if key in CONF.hardware_thunder.devices:
            return True

        # rack flow with device flavor
        device_name = None
        if flavor:
            device_name = flavor.get('device-name', None)
        elif loadbalancer:
            flavor_data = utils.get_loadbalancer_flavor(loadbalancer)
            if flavor_data is not None:
                device_name = flavor_data.get('device-name', None)
        if device_name is not None and isinstance(CONF.hardware_thunder.devices, dict):
            for device in CONF.hardware_thunder.devices.values():
                if device.device_name == device_name:
                    return True

        return False

    def _vthunder_busy_check(self, key, is_reload_thread, flags, loadbalancer, store=None):
        busy = False
        if self._is_rack_flow(key, loadbalancer=loadbalancer):
            return busy

        timeout = CONF.a10_controller_worker.amp_busy_wait_sec
        while timeout >= 0:
            # amp_busy_wait_sec 0 for wait forever
            if CONF.a10_controller_worker.amp_busy_wait_sec != 0:
                timeout = timeout - 5

            self.ctx_lock.acquire()
            ctx = self.ctx_map.get(key, None)
            if ctx is None:
                ctx = (0, 0)
            normal_thrd_num, reload_thrd_num = ctx
            LOG.debug('[busy_check] vthunder %s ctx: normal_thrd(%d), reload_thrd(%d)',
                      key, normal_thrd_num, reload_thrd_num)
            if is_reload_thread:
                if reload_thrd_num > 0 or normal_thrd_num > 0:
                    busy = True
                else:
                    reload_thrd_num = reload_thrd_num + 1
                    self.ctx_map[key] = (normal_thrd_num, reload_thrd_num)
                    busy = False
            else:
                if reload_thrd_num > 0:
                    busy = True
                else:
                    normal_thrd_num = normal_thrd_num + 1
                    self.ctx_map[key] = (normal_thrd_num, reload_thrd_num)
                    busy = False
            self.ctx_lock.release()

            if not busy:
                LOG.debug('[busy_check] vthunder %s ctx: normal_thrd(%d), reload_thrd(%d)',
                          key, normal_thrd_num, reload_thrd_num)
                flags[0] = True
                break
            time.sleep(5)

        if store is not None:
            store[a10constants.COMPUTE_BUSY] = busy

        return busy

    def _set_vthunder_available(self, key, is_reload_thread, flags, loadbalancer):
        if self._is_rack_flow(key, loadbalancer=loadbalancer):
            return
        ctx_cnt_dec(self.ctx_lock, self.ctx_map, key, is_reload_thread, flags)

    def _register_flow_notify_handler(self, engine, key, is_reload_thread, instance_busy,
                                      flags, loadbalancer):
        if self._is_rack_flow(key, loadbalancer=loadbalancer) or instance_busy:
            return
        kwargs = {'ctx_key': key, 'ctx_lock': self.ctx_lock, 'ctx_map': self.ctx_map,
                  'is_reload_thread': is_reload_thread, 'ctx_flags': flags}
        engine.notifier.register('*', flow_notification_handler, kwargs=kwargs)

    def _get_flavor_data(self, flavor_id):
        flavor = self._flavor_repo.get(db_apis.get_session(), id=flavor_id)
        if flavor and flavor.flavor_profile_id:
            flavor_profile = self._flavor_profile_repo.get(
                db_apis.get_session(),
                id=flavor.flavor_profile_id)
            flavor_data = json.loads(flavor_profile.flavor_data)
            return flavor_data
        return None
