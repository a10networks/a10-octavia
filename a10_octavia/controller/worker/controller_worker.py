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
from octavia.db import models as db_models

from a10_octavia.common import a10constants
from a10_octavia.common import exceptions as a10_ex
from a10_octavia.common import utils
# from a10_octavia.controller.worker.flows import a10_health_monitor_flows
# from a10_octavia.controller.worker.flows import a10_l7policy_flows
# from a10_octavia.controller.worker.flows import a10_l7rule_flows
# from a10_octavia.controller.worker.flows import a10_listener_flows
# from a10_octavia.controller.worker.flows import a10_load_balancer_flows
# from a10_octavia.controller.worker.flows import a10_member_flows
# from a10_octavia.controller.worker.flows import a10_pool_flows
# from a10_octavia.controller.worker.flows import vthunder_flows
from a10_octavia.db import repositories as a10repo

# from stevedore import driver as stevedore_driver
# from octavia.amphorae.driver_exceptions import exceptions as driver_exc
from octavia.api.drivers import utils as provider_utils
from a10_octavia.controller.worker.flows import flow_utils


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CONF = cfg.CONF
LOG = logging.getLogger(__name__)

RETRY_ATTEMPTS = CONF.a10_controller_worker.retry_attempts
RETRY_INITIAL_DELAY = CONF.a10_controller_worker.retry_initial_delay
RETRY_BACKOFF = CONF.a10_controller_worker.retry_bakcoff
RETRY_MAX = CONF.a10_controller_worker.retry_max


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


class A10ControllerWorker(object):

    def __init__(self):
        self._lb_repo = repo.LoadBalancerRepository()
        self._listener_repo = repo.ListenerRepository()
        self._pool_repo = repo.PoolRepository()
        self._member_repo = a10repo.MemberRepository()
        self._health_mon_repo = repo.HealthMonitorRepository()
        self._l7policy_repo = repo.L7PolicyRepository()
        self._l7rule_repo = repo.L7RuleRepository()
        # self._lb_flows = a10_load_balancer_flows.LoadBalancerFlows()
        # self._listener_flows = a10_listener_flows.ListenerFlows()
        # self._pool_flows = a10_pool_flows.PoolFlows()
        # self._member_flows = a10_member_flows.MemberFlows()
        # self._health_monitor_flows = a10_health_monitor_flows.HealthMonitorFlows()
        # self._l7policy_flows = a10_l7policy_flows.L7PolicyFlows()
        # self._l7rule_flows = a10_l7rule_flows.L7RuleFlows()
        # self._vthunder_flows = vthunder_flows.VThunderFlows()
        self._vthunder_repo = a10repo.VThunderRepository()
        self._flavor_repo = repo.FlavorRepository()
        self._flavor_profile_repo = repo.FlavorProfileRepository()
        self._exclude_result_logging_tasks = ()
        self.ctx_map = None
        self.ctx_lock = None
        self.tf_engine = base_taskflow.BaseTaskFlowEngine()
        super(A10ControllerWorker, self).__init__()

    def run_flow(self, func, *args, **kwargs):
        if CONF.task_flow.jobboard_enabled:
            self.services_controller.run_poster(func, *args, **kwargs)
        else:
            store = kwargs.pop('store', None)
            flow_result = func(*args, **kwargs)

            if isinstance(flow_result, tuple):
                flow = flow_result[0]
            else:
                flow = flow_result
            
            tf = self.tf_engine.taskflow_load(flow, store=store)

            with tf_logging.DynamicLoggingListener(tf, log=LOG):
                tf.run()
            
            return tf

    def create_amphora(self):
        store={constants.BUILD_TYPE_PRIORITY:
                a10constants.LB_CREATE_SPARES_POOL_PRIORITY,
                constants.FLAVOR: None}
        create_vthunder_tf = self.run_flow(flow_utils.get_create_vthunder_flow, store=store)
        create_vthunder_tf.run()

        return create_vthunder_tf.storage.fetch('amphora')

    @tenacity.retry(
        retry=tenacity.retry_if_exception_type(db_exceptions.NoResultFound),
        wait=tenacity.wait_incrementing(
            RETRY_INITIAL_DELAY, RETRY_BACKOFF, RETRY_MAX),
        stop=tenacity.stop_after_attempt(RETRY_ATTEMPTS))
    def create_health_monitor(self, health_monitor):
        """Creates a health monitor.

        :param health_monitor: Provider health monitor dict
        :returns: None
        :raises NoResultFound: Unable to find the object
        """
        session = db_apis.get_session()
        with session.begin():
            db_health_monitor = self._health_mon_repo.get(
                session,
                id=health_monitor[constants.HEALTHMONITOR_ID])
        if not db_health_monitor:
            LOG.warning('Failed to fetch %s %s from DB. Retrying for up to '
                        '60 seconds.', 'healthmonitor',
                        health_monitor[constants.HEALTHMONITOR_ID])
            raise db_exceptions.NoResultFound
        pool = db_health_monitor.pool
        pool.health_monitor = db_health_monitor
        load_balancer = pool.load_balancer
        flavor_id = load_balancer.to_dict().get(constants.FLAVOR_ID) if load_balancer.to_dict().get(constants.FLAVOR_ID) else CONF.a10_global.default_flavor_id
        pool = pool.to_dict(recurse=True)
        topology = CONF.a10_controller_worker.loadbalancer_topology
        
        provider_lb = provider_utils.db_loadbalancer_to_provider_loadbalancer(
            load_balancer).to_dict(recurse=True)
        listeners_dicts = provider_lb.get('listeners', [])
        
        ctx_flags = [False]
        # rack flow _vthunder_busy_check() will always return False
        busy = self._vthunder_busy_check(health_monitor[constants.PROJECT_ID], False, ctx_flags, provider_lb)

        store = {
            constants.HEALTH_MON: health_monitor,
            constants.POOL_ID: pool[constants.ID],
            constants.POOL: pool,
            constants.LISTENERS: listeners_dicts,
            constants.LOADBALANCER_ID: provider_lb[constants.LOADBALANCER_ID],
            constants.LOADBALANCER: provider_lb,
            a10constants.COMPUTE_BUSY: busy,
            a10constants.WRITE_MEM_SHARED_PART: True,
            constants.FLAVOR_ID: flavor_id,
            constants.PROVISIONING_STATUS : db_health_monitor.to_dict()[constants.PROVISIONING_STATUS]
        }

        try:
            create_hm_tf = self.run_flow(flow_utils.get_create_health_monitor_flow,topology=topology,
                                        store= store)
            self._register_flow_notify_handler(create_hm_tf, health_monitor[constants.PROJECT_ID],
                                            False, busy, ctx_flags, provider_lb)
            create_hm_tf.run()
        finally:
            self._set_vthunder_available(health_monitor[constants.PROJECT_ID], False, ctx_flags, provider_lb)

    def delete_health_monitor(self, health_monitor):
        """Deletes a health monitor.

        :param health_monitor: Provider health monitor dict
        :returns: None
        :raises HMNotFound: The referenced health monitor was not found
        """
        session = db_apis.get_session()
        with session.begin():
            db_health_monitor = self._health_mon_repo.get(
                session,
                id=health_monitor[constants.HEALTHMONITOR_ID])

        pool = db_health_monitor.pool
        # listeners = pool.listeners
        load_balancer = pool.load_balancer
        flavor_id = load_balancer.to_dict().get(constants.FLAVOR_ID) if load_balancer.to_dict().get(constants.FLAVOR_ID) else CONF.a10_global.default_flavor_id
        provider_lb = provider_utils.db_loadbalancer_to_provider_loadbalancer(
            load_balancer).to_dict(recurse=True)
        listeners_dicts = provider_lb.get('listeners', [])
        
        pool = pool.to_dict(recurse=True)
        topology = CONF.a10_controller_worker.loadbalancer_topology

        ctx_flags = [False]
        # rack flow _vthunder_busy_check() will always return False
        busy = self._vthunder_busy_check(health_monitor[constants.PROJECT_ID], False, ctx_flags, provider_lb)
        
        store={constants.HEALTH_MON: health_monitor,
                    constants.POOL_ID: pool[constants.ID],
                    constants.LISTENERS: listeners_dicts,
                    constants.LOADBALANCER_ID: provider_lb[constants.LOADBALANCER_ID],
                    constants.LOADBALANCER: provider_lb,
                    constants.PROJECT_ID: health_monitor[constants.PROJECT_ID],
                    a10constants.COMPUTE_BUSY: busy,
                    a10constants.WRITE_MEM_SHARED_PART: True,
                    constants.FLAVOR_ID: flavor_id,
                    constants.PROVISIONING_STATUS : db_health_monitor.to_dict()[constants.PROVISIONING_STATUS]}
        
        try:
            delete_hm_tf = self.run_flow(flow_utils.get_delete_health_monitor_flow,topology=topology,
                                        store=store)
            self._register_flow_notify_handler(delete_hm_tf, health_monitor[constants.PROJECT_ID], False,
                                            busy, ctx_flags, provider_lb)
            delete_hm_tf.run()
        finally:
            self._set_vthunder_available(health_monitor[constants.PROJECT_ID], False, ctx_flags, provider_lb)

    def update_health_monitor(self, original_health_monitor, health_monitor_updates):
        """Updates a health monitor.

        :param original_health_monitor: Provider health monitor dict
        :param health_monitor_updates: Dict containing updated health monitor
        :returns: None
        :raises HMNotFound: The referenced health monitor was not found
        """
        try:
            db_health_monitor = self._get_db_obj_until_pending_update(
                self._health_mon_repo,
                original_health_monitor[constants.HEALTHMONITOR_ID])
        except tenacity.RetryError as e:
            LOG.warning('Health monitor did not go into %s in 60 seconds. '
                        'This either due to an in-progress Octavia upgrade '
                        'or an overloaded and failing database. Assuming '
                        'an upgrade is in progress and continuing.',
                        constants.PENDING_UPDATE)
            db_health_monitor = e.last_attempt.result()

        pool = db_health_monitor.pool
        load_balancer = pool.load_balancer
        flavor_id = load_balancer.to_dict().get(constants.FLAVOR_ID) if load_balancer.to_dict().get(constants.FLAVOR_ID) else CONF.a10_global.default_flavor_id
        provider_lb = provider_utils.db_loadbalancer_to_provider_loadbalancer(
            load_balancer).to_dict(recurse=True)
        listeners_dicts = provider_lb.get('listeners', [])

        pool = pool.to_dict(recurse=True)
        topology = CONF.a10_controller_worker.loadbalancer_topology

        ctx_flags = [False]
        # rack flow _vthunder_busy_check() will always return False
        busy = self._vthunder_busy_check(original_health_monitor[constants.PROJECT_ID], False, ctx_flags, provider_lb)
        
        store={constants.HEALTH_MON: original_health_monitor,
            constants.POOL_ID: pool[constants.ID],
            constants.LISTENERS: listeners_dicts,
            constants.LOADBALANCER_ID: provider_lb[constants.LOADBALANCER_ID],
            constants.LOADBALANCER: provider_lb,
            constants.UPDATE_DICT: health_monitor_updates,
            a10constants.COMPUTE_BUSY: busy,
            a10constants.WRITE_MEM_SHARED_PART: True,
            constants.FLAVOR_ID: flavor_id,
            constants.PROVISIONING_STATUS : db_health_monitor.to_dict()[constants.PROVISIONING_STATUS]}
        
        try:
            update_hm_tf = self.run_flow(flow_utils.get_update_health_monitor_flow, topology=topology,
                                        store= store)
            self._register_flow_notify_handler(update_hm_tf, original_health_monitor[constants.PROJECT_ID], False,
                                            busy, ctx_flags, provider_lb)
            update_hm_tf.run()
        finally:
            self._set_vthunder_available(original_health_monitor[constants.PROJECT_ID], False, ctx_flags, provider_lb)

    @tenacity.retry(
        retry=tenacity.retry_if_exception_type(db_exceptions.NoResultFound),
        wait=tenacity.wait_incrementing(
            RETRY_INITIAL_DELAY, RETRY_BACKOFF, RETRY_MAX),
        stop=tenacity.stop_after_attempt(RETRY_ATTEMPTS))
    def create_listener(self, listener):
        """Function to create listener for A10 provider
        :param listener: A listener provider dictionary.
        :returns: None
        :raises NoResultFound: Unable to find the object
        """
        # listener = self._listener_repo.get(db_apis.get_session(),
        #                                    id=listener_id)
        # if not listener:
        #     LOG.warning('Failed to fetch %s %s from DB. Retrying for up to '
        #                 '60 seconds.', 'listener', listener_id)
        #     raise db_exceptions.NoResultFound
        
        session = db_apis.get_session()
        with session.begin():
            db_listener = self._listener_repo.get(
                session, id=listener[constants.LISTENER_ID])
        if not db_listener:
            LOG.warning('Failed to fetch %s %s from DB. Retrying for up to '
                        '60 seconds.', 'listener',
                        listener[constants.LISTENER_ID])
            raise db_exceptions.NoResultFound
        # load_balancer = listener.load_balancer
        parent_project_list = utils.get_parent_project_list()
        listener_parent_proj = utils.get_parent_project(listener[constants.PROJECT_ID])

        topology = CONF.a10_controller_worker.loadbalancer_topology

        ctx_flags = [False]
        load_balancer = db_listener.load_balancer
        
        provider_lb = provider_utils.db_loadbalancer_to_provider_loadbalancer(
            load_balancer).to_dict(recurse=True)
        flavor_id = load_balancer.to_dict().get(constants.FLAVOR_ID) if load_balancer.to_dict().get(constants.FLAVOR_ID) else CONF.a10_global.default_flavor_id
        store = {constants.LISTENERS: provider_lb['listeners'],
                constants.LOADBALANCER: provider_lb,
                constants.LOADBALANCER_ID: provider_lb[constants.LOADBALANCER_ID],
                constants.LISTENER: db_listener.to_dict(recurse=True),
                constants.FLAVOR_ID: flavor_id,
                constants.PROVISIONING_STATUS : db_listener.to_dict()[constants.PROVISIONING_STATUS]}
        try:
            if (listener[constants.PROJECT_ID] in parent_project_list or
                    (listener_parent_proj and listener_parent_proj in parent_project_list)
                    or self._is_rack_flow(listener[constants.PROJECT_ID], loadbalancer=provider_lb)):
                create_listener_tf = self.run_flow(flow_utils.get_rack_vthunder_create_listener_flow,
                                                listener[constants.PROJECT_ID],store=store)
            else:
                busy = self._vthunder_busy_check(listener[constants.PROJECT_ID], False, ctx_flags,
                                                provider_lb)
                store.update({a10constants.COMPUTE_BUSY: busy})
                create_listener_tf = self.run_flow(flow_utils.get_create_listener_flow,
                                                topology=topology,store=store)
                self._register_flow_notify_handler(create_listener_tf, listener[constants.PROJECT_ID], False,
                                                busy, ctx_flags, provider_lb)
            create_listener_tf.run()
        finally:
            self._set_vthunder_available(listener[constants.PROJECT_ID], False, ctx_flags, provider_lb)

    def delete_listener(self, listener):
        """Function to delete a listener for A10 provider
        
        :param listener: A listener provider dictionary to delete
        :returns: None
        :raises ListenerNotFound: The referenced listener was not found
        """

        try:
            db_lb = self._get_db_obj_until_pending_update(
                self._lb_repo, listener[constants.LOADBALANCER_ID])
        except tenacity.RetryError as e:
            LOG.warning('Loadbalancer did not go into %s in 60 seconds. '
                        'This either due to an in-progress Octavia upgrade '
                        'or an overloaded and failing database. Assuming '
                        'an upgrade is in progress and continuing.',
                        constants.PENDING_UPDATE)
            db_lb = e.last_attempt.result()

        db_lb = provider_utils.db_loadbalancer_to_provider_loadbalancer(
            db_lb).to_dict(recurse=True)
        topology = CONF.a10_controller_worker.loadbalancer_topology

        ctx_flags = [False]
        try:
            if self._is_rack_flow(listener[constants.PROJECT_ID], loadbalancer=db_lb):
                store={constants.LOADBALANCER: db_lb,
                    constants.LISTENER: listener,
                    constants.PROJECT_ID: listener[constants.PROJECT_ID]}
                delete_listener_tf = self.run_flow(flow_utils.get_delete_rack_listener_flow,
                                                store= store)
            else:
                busy = self._vthunder_busy_check(listener[constants.PROJECT_ID], False, ctx_flags,
                                                db_lb)
                store={constants.LOADBALANCER: db_lb,
                    a10constants.COMPUTE_BUSY: busy,
                    constants.LISTENER: listener,
                    constants.LOADBALANCER_ID: listener[constants.LOADBALANCER_ID],
                    constants.PROJECT_ID: listener[constants.PROJECT_ID]}
                delete_listener_tf = self.run_flow(flow_utils.get_delete_listener_flow,topology,
                                                store = store)
                self._register_flow_notify_handler(delete_listener_tf, listener[constants.PROJECT_ID], False,
                                                busy, ctx_flags, db_lb)
            
            delete_listener_tf.run()
        finally:
            self._set_vthunder_available(listener[constants.PROJECT_ID], False, ctx_flags, db_lb)

    def update_listener(self, listener, listener_updates):
        """Function to Update a listener for A10 provider
        
        :param listener: A listener provider dictionary to update
        :param listener_updates: Dict containing updated listener attributes
        :returns: None
        :raises ListenerNotFound: The referenced listener was not found
        """
        try:
            db_lb = self._get_db_obj_until_pending_update(
                self._lb_repo, listener[constants.LOADBALANCER_ID])
        except tenacity.RetryError as e:
            LOG.warning('Loadbalancer did not go into %s in 60 seconds. '
                        'This either due to an in-progress Octavia upgrade '
                        'or an overloaded and failing database. Assuming '
                        'an upgrade is in progress and continuing.',
                        constants.PENDING_UPDATE)
            db_lb = e.last_attempt.result()

        flavor_id = db_lb.to_dict().get(constants.FLAVOR_ID) if db_lb.to_dict().get(constants.FLAVOR_ID) else CONF.a10_global.default_flavor_id

        topology = CONF.a10_controller_worker.loadbalancer_topology

        db_lb = provider_utils.db_loadbalancer_to_provider_loadbalancer(
            db_lb).to_dict(recurse=True)

        ctx_flags = [False]
        # rack flow _vthunder_busy_check() will always return False
        busy = self._vthunder_busy_check(listener[constants.PROJECT_ID], False, ctx_flags, db_lb)
        try:
            store={constants.LISTENER: listener,
                    a10constants.COMPUTE_BUSY: busy,
                    constants.LOADBALANCER: db_lb,
                    constants.UPDATE_DICT: listener_updates,
                    constants.FLAVOR_ID: flavor_id,
                    constants.PROVISIONING_STATUS : constants.PENDING_UPDATE}
            update_listener_tf = self.run_flow(flow_utils.get_update_listener_flow,
                                               topology,store=store)
            self._register_flow_notify_handler(update_listener_tf, listener[constants.PROJECT_ID], False,
                                            busy, ctx_flags, db_lb)
            
            
            update_listener_tf.run()
        finally:
            self._set_vthunder_available(listener[constants.PROJECT_ID], False, ctx_flags, db_lb)

    @tenacity.retry(
        retry=tenacity.retry_if_exception_type(db_exceptions.NoResultFound),
        wait=tenacity.wait_incrementing(
            RETRY_INITIAL_DELAY, RETRY_BACKOFF, RETRY_MAX),
        stop=tenacity.stop_after_attempt(RETRY_ATTEMPTS))
    def create_load_balancer(self, loadbalancer, flavor=None, ctx_map=None, ctx_lock=None):
        """Function to create load balancer for A10 provider
        
        :param loadbalancer: The dict of load balancer to create
        :returns: None
        :raises NoResultFound: Unable to find the object
        """
        session = db_apis.get_session()
        with session.begin():
            lb = self._lb_repo.get(session,
                                id=loadbalancer[constants.LOADBALANCER_ID])
        lb = lb.to_dict(recurse=True)
        if not lb:
            LOG.warning('Failed to fetch %s %s from DB. Retrying for up to '
                        '60 seconds.', 'load_balancer',
                        loadbalancer[constants.LOADBALANCER_ID])
            raise db_exceptions.NoResultFound

        flavor_id = lb.get(constants.FLAVOR_ID) if lb.get(constants.FLAVOR_ID) else CONF.a10_global.default_flavor_id
        if not flavor and flavor_id:
            flavor = self._get_flavor_data(flavor_id)

        topology = CONF.a10_controller_worker.loadbalancer_topology
        
        # listeners_dicts = (
        #     provider_utils.db_listeners_to_provider_dicts_list_of_dicts(
        #         lb.listeners)
        # )

        store = {constants.LOADBALANCER_ID: loadbalancer[constants.LOADBALANCER_ID],
        constants.BUILD_TYPE_PRIORITY: constants.LB_CREATE_NORMAL_PRIORITY,
        constants.FLAVOR: flavor,
        constants.PROJECT_ID: loadbalancer[constants.PROJECT_ID],
        constants.VIP: lb.get(constants.VIP),
        constants.FLAVOR_ID: flavor_id,
        constants.PROVISIONING_STATUS : lb[constants.PROVISIONING_STATUS],
        constants.AMPS_DATA: []}

        store[constants.UPDATE_DICT] = {
            constants.TOPOLOGY: topology
        }

        ctx_flags = [False]
        try:
            if self._is_rack_flow(loadbalancer[constants.PROJECT_ID], flavor=flavor):
                vthunder_conf = CONF.hardware_thunder.devices.get(loadbalancer[constants.PROJECT_ID], None)
                device_dict = CONF.hardware_thunder.devices
                create_lb_tf = self.run_flow(
                    flow_utils.get_create_rack_vthunder_load_balancer_flow,
                    vthunder_conf=vthunder_conf,
                    device_dict=device_dict,
                    topology=topology,
                    listeners=lb.get(constants.LISTENERS),
                    pools=lb.get(constants.POOLS),
                    store=store
                )
            else:
                busy = self._vthunder_busy_check(loadbalancer[constants.PROJECT_ID], True, ctx_flags, loadbalancer, store)
                store.update([
                    (a10constants.COMPUTE_BUSY, busy),
                    (a10constants.VTHUNDER_CONFIG, None),
                    (a10constants.USE_DEVICE_FLAVOR, False)])
                create_lb_tf = self.run_flow(flow_utils.get_create_load_balancer_flow, loadbalancer, topology, project_id=loadbalancer[constants.PROJECT_ID], listeners=lb.get(constants.LISTENERS), pools=lb.get(constants.POOLS), store=store)
                self._register_flow_notify_handler(create_lb_tf, loadbalancer[constants.PROJECT_ID], True,
                                                busy, ctx_flags, loadbalancer)

            create_lb_tf.run()
        finally:
            self._set_vthunder_available(loadbalancer[constants.PROJECT_ID], True, ctx_flags, loadbalancer)

    def delete_load_balancer(self, load_balancer, cascade=False):
        """Function to delete load balancer for A10 provider
        
        :param load_balancer: Dict of the load balancer to delete
        :returns: None
        :raises LBNotFound: The referenced load balancer was not found
        """
        loadbalancer_id = load_balancer[constants.LOADBALANCER_ID]
        session = db_apis.get_session()
        with session.begin():
            db_lb = self._lb_repo.get(session, id=loadbalancer_id)
        store={}
        listener_dicts = []
        if cascade:
            for listener in db_lb.listeners:
                prov_listener = provider_utils.db_listener_to_provider_listener(
                    listener, True)
                listener_dicts.append(prov_listener.to_dict())
            store[constants.LISTENERS] = listener_dicts
        db_lb=db_lb.to_dict(recurse=True)

        vthunder = self._vthunder_repo.get_vthunder_from_lb(db_apis.get_session(),
                                                            loadbalancer_id)
        deleteCompute = False
        ctx_flags = [False]
        busy = self._vthunder_busy_check(load_balancer[constants.PROJECT_ID], True, ctx_flags, load_balancer)
        flavor_id = db_lb.get(constants.FLAVOR_ID) if db_lb.get(constants.FLAVOR_ID) else CONF.a10_global.default_flavor_id
        try:
            if vthunder:
                deleteCompute = self._vthunder_repo.get_delete_compute_flag(db_apis.get_session(),
                                                                            vthunder.compute_id)
            store = {
                constants.LOADBALANCER: load_balancer,
                a10constants.COMPUTE_BUSY: busy,
                constants.VIP: db_lb.get(constants.VIP),
                constants.SERVER_GROUP_ID: db_lb.get(constants.SERVER_GROUP_ID),
                constants.LOADBALANCER_ID: loadbalancer_id,
                a10constants.MASTER_AMPHORA_STATUS: True,
                a10constants.VTHUNDER_CONFIG: None,
                a10constants.USE_DEVICE_FLAVOR: False,
                a10constants.LB_COUNT_THUNDER: None,
                a10constants.MEMBER_COUNT_THUNDER: None,
                constants.PROJECT_ID: load_balancer[constants.PROJECT_ID],
                constants.FLAVOR_ID: flavor_id,
                constants.PROVISIONING_STATUS : db_lb[constants.PROVISIONING_STATUS]
            }

            if self._is_rack_flow(load_balancer[constants.PROJECT_ID], loadbalancer=load_balancer):
                vthunder_conf = CONF.hardware_thunder.devices.get(load_balancer[constants.PROJECT_ID], None)
                device_dict = CONF.hardware_thunder.devices
                delete_lb_tf = self.run_flow(
                    flow_utils.get_delete_rack_vthunder_load_balancer_flow,
                    db_lb,
                    cascade,
                    listener_dicts,
                    vthunder_conf=vthunder_conf,
                    device_dict=device_dict,
                    store=store
                )
            else:
                delete_lb_tf = self.run_flow(
                    flow_utils.get_delete_load_balancer_flow,
                    db_lb,
                    listener_dicts,
                    deleteCompute,
                    cascade,
                    store=store
                )

            self._register_flow_notify_handler(
                delete_lb_tf, load_balancer[constants.PROJECT_ID], True, busy, ctx_flags, load_balancer)

            delete_lb_tf.run()

        finally:
            self._set_vthunder_available(load_balancer[constants.PROJECT_ID], True, ctx_flags, load_balancer)

    def update_load_balancer(self, original_load_balancer, load_balancer_updates):
        """Function to update load balancer for A10 provider
        
        :param original_load_balancer: Dict of the load balancer to update
        :param load_balancer_updates: Dict containing updated load balancer
        :returns: None
        :raises LBNotFound: The referenced load balancer was not found
        """
        try:
            self._get_db_obj_until_pending_update(
                self._lb_repo,
                original_load_balancer[constants.LOADBALANCER_ID])
        except tenacity.RetryError:
            LOG.warning('Load balancer did not go into %s in 60 seconds. '
                        'This either due to an in-progress Octavia upgrade '
                        'or an overloaded and failing database. Assuming '
                        'an upgrade is in progress and continuing.',
                        constants.PENDING_UPDATE)
        session = db_apis.get_session()
        with session.begin():
            db_lb = self._lb_repo.get(session, id=original_load_balancer[constants.LOADBALANCER_ID]).to_dict(recurse=True)
        topology = CONF.a10_controller_worker.loadbalancer_topology

        ctx_flags = [False]
        if constants.VIP not in original_load_balancer:
            original_load_balancer['vip'] = {
                constants.VIP_ADDRESS: original_load_balancer.get(constants.VIP_ADDRESS),
                constants.VIP_NETWORK_ID: original_load_balancer.get(constants.VIP_NETWORK_ID),
                constants.VIP_PORT_ID: original_load_balancer.get(constants.VIP_PORT_ID),
                constants.VIP_SUBNET_ID: original_load_balancer.get(constants.VIP_SUBNET_ID),
                constants.VIP_QOS_POLICY_ID: original_load_balancer.get(constants.VIP_QOS_POLICY_ID)
            }
        flavor_id = db_lb.get(constants.FLAVOR_ID) if db_lb.get(constants.FLAVOR_ID) else CONF.a10_global.default_flavor_id
        try:
            if self._is_rack_flow(original_load_balancer[constants.PROJECT_ID], loadbalancer=original_load_balancer):
                vthunder_conf = CONF.hardware_thunder.devices.get(original_load_balancer[constants.PROJECT_ID], None)
                device_dict = CONF.hardware_thunder.devices
                store={constants.LOADBALANCER: original_load_balancer,
                        constants.VIP: original_load_balancer[constants.VIP],
                        constants.UPDATE_DICT: load_balancer_updates,
                        constants.FLAVOR_ID: flavor_id,
                        constants.PROVISIONING_STATUS : db_lb[constants.PROVISIONING_STATUS]}
                update_lb_tf = self.run_flow(flow_utils.get_update_rack_load_balancer_flow,
                                            vthunder_conf=vthunder_conf,device_dict=device_dict,
                                            topology=topology,
                                            store=store)
            else:
                busy = self._vthunder_busy_check(original_load_balancer[constants.PROJECT_ID], False, ctx_flags, original_load_balancer)
                store={constants.LOADBALANCER: original_load_balancer,
                        constants.LOADBALANCER_ID: original_load_balancer[constants.LOADBALANCER_ID],
                        constants.VIP: original_load_balancer[constants.VIP],
                        a10constants.COMPUTE_BUSY: busy,
                        constants.UPDATE_DICT: load_balancer_updates,
                        a10constants.VTHUNDER_CONFIG: None,
                        a10constants.USE_DEVICE_FLAVOR: False,
                        constants.FLAVOR_ID: flavor_id,
                        constants.PROVISIONING_STATUS : db_lb[constants.PROVISIONING_STATUS]}
                update_lb_tf = self.run_flow(flow_utils.get_update_load_balancer_flow,
                                            topology=topology,
                                            store=store)
                self._register_flow_notify_handler(update_lb_tf, original_load_balancer[constants.PROJECT_ID], False,
                                                busy, ctx_flags, original_load_balancer)

            update_lb_tf.run()
        finally:
            self._set_vthunder_available(original_load_balancer[constants.PROJECT_ID], False, ctx_flags, original_load_balancer)

    @tenacity.retry(
        retry=tenacity.retry_if_exception_type(db_exceptions.NoResultFound),
        wait=tenacity.wait_incrementing(
            RETRY_INITIAL_DELAY, RETRY_BACKOFF, RETRY_MAX),
        stop=tenacity.stop_after_attempt(RETRY_ATTEMPTS))
    def create_member(self, member):
        """Creates a pool member.

        :param member: A member provider dictionary to create
        :returns: None
        :raises NoSuitablePool: Unable to find the node pool
        """

        session = db_apis.get_session()
        with session.begin():
            db_member = self._member_repo.get(session,
                                            id=member[constants.MEMBER_ID])
        if not db_member:
            LOG.warning('Failed to fetch %s %s from DB. Retrying for up to '
                        '60 seconds.', 'l7member',
                        member[constants.MEMBER_ID])
            raise db_exceptions.NoResultFound
        member['enabled'] = db_member.enabled
        pool = db_member.pool
        load_balancer = pool.load_balancer
        flavor_id = load_balancer.to_dict().get(constants.FLAVOR_ID) if load_balancer.to_dict().get(constants.FLAVOR_ID) else CONF.a10_global.default_flavor_id
        provider_lb = provider_utils.db_loadbalancer_to_provider_loadbalancer(
            load_balancer).to_dict(recurse=True)
        listeners_dicts = provider_lb.get('listeners', [])

        topology = CONF.a10_controller_worker.loadbalancer_topology
        parent_project_list = utils.get_parent_project_list()
        member_parent_proj = utils.get_parent_project(
            member[constants.PROJECT_ID])

        ctx_flags = [False]
        try:
            if (member[constants.PROJECT_ID] in parent_project_list or
                    (member_parent_proj and member_parent_proj in parent_project_list)
                    or self._is_rack_flow(member[constants.PROJECT_ID], loadbalancer=provider_lb)):
                vthunder_conf = CONF.hardware_thunder.devices.get(provider_lb[constants.PROJECT_ID], None)
                device_dict = CONF.hardware_thunder.devices
                store={constants.MEMBER: member,
                        constants.LISTENERS: listeners_dicts,
                        constants.LOADBALANCER: provider_lb,
                        constants.LOADBALANCER_ID: provider_lb[constants.LOADBALANCER_ID],
                        constants.POOL_ID: pool.id,
                        constants.POOL: pool.to_dict(recurse=True),
                        constants.FLAVOR_ID: flavor_id,
                        constants.PROVISIONING_STATUS : db_member.to_dict()[constants.PROVISIONING_STATUS]}
                create_member_tf = self.run_flow(flow_utils.get_rack_vthunder_create_member_flow,
                                                vthunder_conf=vthunder_conf, device_dict=device_dict,
                                                store= store)

            else:
                busy = self._vthunder_busy_check(member[constants.PROJECT_ID], True, ctx_flags, provider_lb)
                store={constants.MEMBER: member,
                        constants.LISTENERS:listeners_dicts,
                        constants.LOADBALANCER:provider_lb,
                        constants.LOADBALANCER_ID: provider_lb[constants.LOADBALANCER_ID],
                        a10constants.COMPUTE_BUSY: busy,
                        constants.POOL: pool.to_dict(recurse=True),
                        constants.POOL_ID: pool.id,
                        a10constants.VTHUNDER_CONFIG: None,
                        a10constants.USE_DEVICE_FLAVOR: False,
                        constants.FLAVOR_ID: flavor_id,
                        constants.PROVISIONING_STATUS : db_member.to_dict()[constants.PROVISIONING_STATUS]}
                create_member_tf = self.run_flow(flow_utils.get_create_member_flow,
                                                topology=topology,store= store)
                self._register_flow_notify_handler(create_member_tf, member[constants.PROJECT_ID], True,
                                                busy, ctx_flags, provider_lb)

            
            create_member_tf.run()
        finally:
            self._set_vthunder_available(member[constants.PROJECT_ID], True, ctx_flags, provider_lb)

    def delete_member(self, member):
        """Deletes a pool member.

        :param member: A member provider dictionary to delete
        :returns: None
        :raises MemberNotFound: The referenced member was not found
        """
        session = db_apis.get_session()
        with session.begin():
            pool = self._pool_repo.get(session,id=member[constants.POOL_ID])

        load_balancer = pool.load_balancer
        provider_lb = provider_utils.db_loadbalancer_to_provider_loadbalancer(
            load_balancer).to_dict(recurse=True)
        listeners_dicts = provider_lb.get('listeners', [])
        pool = pool.to_dict(recurse=True)
        flavor_id = load_balancer.to_dict().get(constants.FLAVOR_ID) if load_balancer.to_dict().get(constants.FLAVOR_ID) else CONF.a10_global.default_flavor_id

        topology = CONF.a10_controller_worker.loadbalancer_topology

        ctx_flags = [False]
        try:
            if self._is_rack_flow(provider_lb[constants.PROJECT_ID], loadbalancer=provider_lb):
                vthunder_conf = CONF.hardware_thunder.devices.get(provider_lb[constants.PROJECT_ID], None)
                device_dict = CONF.hardware_thunder.devices
                store={constants.MEMBER: member, 
                       constants.LOADBALANCER_ID: provider_lb[constants.LOADBALANCER_ID],
                       constants.LISTENERS: listeners_dicts,
                       constants.PROJECT_ID: provider_lb[constants.PROJECT_ID],
                       constants.LOADBALANCER: provider_lb,
                       constants.POOL_ID: pool[constants.ID],
                       constants.POOL: pool,
                       constants.FLAVOR_ID: flavor_id,
                       constants.PROVISIONING_STATUS : pool[constants.PROVISIONING_STATUS]}
                delete_member_tf = self.run_flow(flow_utils.get_rack_vthunder_delete_member_flow,
                                                vthunder_conf,device_dict,store=store)
            else:
                busy = self._vthunder_busy_check(provider_lb[constants.PROJECT_ID], True, ctx_flags, provider_lb)
                store={constants.MEMBER: member, 
                       constants.LISTENERS: listeners_dicts,
                       constants.LOADBALANCER: provider_lb,
                       constants.LOADBALANCER_ID: provider_lb[constants.LOADBALANCER_ID],
                       constants.POOL_ID: pool[constants.ID],
                       a10constants.COMPUTE_BUSY: busy,
                       constants.POOL: pool,
                       constants.PROJECT_ID: provider_lb[constants.PROJECT_ID],
                       a10constants.VTHUNDER_CONFIG: None,
                       a10constants.USE_DEVICE_FLAVOR: False,
                       a10constants.LB_COUNT_THUNDER: None,
                       a10constants.MEMBER_COUNT_THUNDER: None,
                       constants.LOADBALANCER_ID: provider_lb[constants.LOADBALANCER_ID],
                       constants.FLAVOR_ID: flavor_id,
                       constants.PROVISIONING_STATUS : pool[constants.PROVISIONING_STATUS]}
                delete_member_tf = self.run_flow(flow_utils.get_delete_member_flow,
                                                topology,store=store)
                self._register_flow_notify_handler(delete_member_tf, provider_lb[constants.PROJECT_ID], True,
                                                busy, ctx_flags, provider_lb)
            
            delete_member_tf.run()
        finally:
            self._set_vthunder_available(provider_lb[constants.PROJECT_ID], True, ctx_flags, provider_lb)

    def _is_batch_valid(self, old_member_ids, new_member_ids,
                        updated_member_ids, member_collision_map):
        valid = True
        for mem_id, member_col in member_collision_map.items():
            member, mem_cnt = member_col
            mem_ip = member.get(constants.ADDRESS) or member.get('ip_address')
            mem_port = member.get('protocol_port')
            if mem_cnt > 1:
                if mem_id in old_member_ids:
                    error_msg = f"Duplicate members with id {mem_id} and IP {mem_ip} and port {mem_port} found in member database."
                elif mem_id in new_member_ids or mem_id in updated_member_ids:
                    error_msg = f"Duplicate members with id {mem_id} and IP {mem_ip} and port {mem_port} found in batch update request."
                else:
                    error_msg = f"Duplicate members with unknown id and IP {mem_ip} and port {mem_port} found."
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
                     "has been deleted.".format(mem[constants.MEMBER_ID], mem[constants.ADDRESS], mem.get('protocol_port')))
        self._member_repo.delete_members(db_apis.get_session(), set_n_ids)

        if pool is not None:
            self._pool_repo.update(db_apis.get_session(), pool.id,
                                    provisioning_status=constants.ACTIVE)
        if listeners is not None:
            for listener in listeners:
                self._listener_repo.update(db_apis.get_session(),
                                            listener.get(constants.LISTENER_ID),
                                            provisioning_status=constants.ACTIVE)
        if load_balancer is not None:
            self._lb_repo.update(db_apis.get_session(),
                                 load_balancer[constants.LOADBALANCER_ID],
                                 provisioning_status=constants.ACTIVE)

    @tenacity.retry(
        retry=tenacity.retry_if_exception_type(db_exceptions.NoResultFound),
        wait=tenacity.wait_incrementing(
            RETRY_INITIAL_DELAY, RETRY_BACKOFF, RETRY_MAX),
        stop=tenacity.stop_after_attempt(RETRY_ATTEMPTS))
    def batch_update_members(self, old_members, new_members, updated_members_req):

        old_member_ids = [m.get(constants.ID) for m in old_members]
        new_member_ids = [m.get(constants.MEMBER_ID) or m.get(constants.ID) for m in new_members]
        updated_member_ids = [m.get(constants.ID) for m in updated_members_req]
        session = db_apis.get_session()

        with session.begin():
            db_new_members = [self._member_repo.get(session, id=member[constants.MEMBER_ID]).to_dict()
                            for member in new_members]
        for i in range(len(new_members)):
            new_members[i]['enabled'] = db_new_members[i]['enabled']

        # The API may not have committed all of the new member records yet.
        # Make sure we retry looking them up.
        if None in db_new_members or len(db_new_members) != len(new_members):
            LOG.warning('Failed to fetch one of the new members from DB. '
                        'Retrying for up to 60 seconds.')
            raise db_exceptions.NoResultFound

        with session.begin():
            updated_member_models = [
                provider_utils.db_member_to_provider_member(
                    self._member_repo.get(session,id=m.get(constants.ID))).to_dict()
                for m in updated_members_req]
            provider_old_members = [
                provider_utils.db_member_to_provider_member(
                    self._member_repo.get(session,id=m.get(constants.ID))).to_dict()
                for m in old_members]
            if old_members:
                pool = self._pool_repo.get(
                    session, id=old_members[0][constants.POOL_ID])
            elif new_members:
                pool = self._pool_repo.get(
                    session, id=new_members[0][constants.POOL_ID])
            else:
                pool = self._pool_repo.get(
                    session,
                    id=updated_member_models[0][0][constants.POOL_ID])

        load_balancer = pool.load_balancer
        flavor_id = load_balancer.to_dict().get(constants.FLAVOR_ID) if load_balancer.to_dict().get(constants.FLAVOR_ID) else CONF.a10_global.default_flavor_id

        provider_lb = provider_utils.db_loadbalancer_to_provider_loadbalancer(
            load_balancer).to_dict(recurse=True)
        listeners_dicts = provider_lb.get('listeners', [])


        modified_members = provider_old_members + updated_member_models + db_new_members
        member_collision_map = {}
        for mem in modified_members:
            if isinstance(mem, tuple):
                member_data, mem_id = mem
            else:
                member_data = mem
                mem_id = member_data.get(constants.ID) or member_data.get(constants.MEMBER_ID)
            if not mem_id:
                mem_id = None
            if mem_id in member_collision_map:
                member_collision_map[mem_id][1] += 1
            else:
                member_collision_map[mem_id] = [member_data, 1]

        if not self._is_batch_valid(old_member_ids, new_member_ids,
                                    updated_member_ids, member_collision_map):
            self._rollback_members(old_member_ids, new_member_ids,
                                    updated_member_ids, load_balancer,
                                    listeners_dicts, pool)
            LOG.warning("Due to a failed batch update caused by duplicate member definitions, "
                        "the members defined in the update are now out-of-sync with the "
                        "ACOS device. Please issue a corrected update or "
                        "delete the affected members.")
            raise a10_ex.DuplicateMembersInBatchUpdate

        updated_members = []
        for i in range(len(updated_member_ids)):
            updated_members.append((updated_member_models[i], updated_members_req[i]))
        store={constants.LISTENERS: listeners_dicts,
                constants.PROJECT_ID: provider_lb[constants.PROJECT_ID],
                constants.LOADBALANCER: provider_lb,
                constants.LOADBALANCER_ID: provider_lb[constants.LOADBALANCER_ID],
                constants.POOL_ID : pool.id,
                constants.POOL: pool.to_dict(),
                constants.FLAVOR_ID: flavor_id,
                constants.PROVISIONING_STATUS : constants.PENDING_UPDATE}

        ctx_flags = [False]
        try:
            if self._is_rack_flow(provider_lb[constants.PROJECT_ID], loadbalancer=provider_lb):
                vthunder_conf = CONF.hardware_thunder.devices.get(provider_lb[constants.PROJECT_ID], None)
                device_dict = CONF.hardware_thunder.devices
                batch_update_members_tf = self.run_flow(flow_utils.get_rack_vthunder_batch_update_members_flow,
                                                        provider_old_members,new_members,updated_members,
                                                        vthunder_conf,device_dict,pool.to_dict(),store= store )
            else:
                topology = CONF.a10_controller_worker.loadbalancer_topology
                busy = self._vthunder_busy_check(provider_lb[constants.PROJECT_ID], True,
                                                 ctx_flags, provider_lb)
                store.update({a10constants.COMPUTE_BUSY: busy,
                              a10constants.VTHUNDER_CONFIG: None,
                              a10constants.USE_DEVICE_FLAVOR: False,
                              a10constants.LB_COUNT_THUNDER: None,
                              a10constants.MEMBER_COUNT_THUNDER: None})
                batch_update_members_tf = self.run_flow(flow_utils.get_batch_update_members_flow,
                                                        provider_old_members, new_members, updated_members, topology, pool.to_dict(),
                                                        store=store)
                self._register_flow_notify_handler(batch_update_members_tf,
                                                   provider_lb[constants.PROJECT_ID], True,
                                                   busy, ctx_flags, provider_lb)
            
            batch_update_members_tf.run()
        finally:
            self._set_vthunder_available(provider_lb[constants.PROJECT_ID], True, ctx_flags, provider_lb)

    def update_member(self, member, member_updates):
        """Updates a pool member.

        :param member: A member provider dictionary  to update
        :param member_updates: Dict containing updated member attributes
        :returns: None
        :raises MemberNotFound: The referenced member was not found
        """
        try:
            db_member = self._get_db_obj_until_pending_update(
                self._member_repo, member[constants.MEMBER_ID])
        except tenacity.RetryError as e:
            LOG.warning('Member did not go into %s in 60 seconds. '
                        'This either due to an in-progress Octavia upgrade '
                        'or an overloaded and failing database. Assuming '
                        'an upgrade is in progress and continuing.',
                        constants.PENDING_UPDATE)
            db_member = e.last_attempt.result()

        pool = db_member.pool
        load_balancer = pool.load_balancer
        pool = pool.to_dict(recurse=True)
        flavor_id = load_balancer.to_dict().get(constants.FLAVOR_ID) if load_balancer.to_dict().get(constants.FLAVOR_ID) else CONF.a10_global.default_flavor_id

        provider_lb = provider_utils.db_loadbalancer_to_provider_loadbalancer(
            load_balancer).to_dict(recurse=True)
        listeners_dicts = provider_lb.get('listeners', [])

        topology = CONF.a10_controller_worker.loadbalancer_topology

        ctx_flags = [False]
        try:
            if self._is_rack_flow(member[constants.PROJECT_ID], loadbalancer=provider_lb):
                vthunder_conf = CONF.hardware_thunder.devices.get(member[constants.PROJECT_ID], None)
                device_dict = CONF.hardware_thunder.devices
                store={constants.MEMBER: member,
                       constants.LISTENERS: listeners_dicts,
                       constants.LOADBALANCER: provider_lb,
                       constants.LOADBALANCER_ID: load_balancer.id,
                       constants.POOL_ID: pool[constants.ID],
                       constants.POOL: pool,
                       constants.UPDATE_DICT: member_updates,
                       constants.FLAVOR_ID: flavor_id,
                       constants.PROVISIONING_STATUS : db_member.to_dict()[constants.PROVISIONING_STATUS]}
                update_member_tf = self.run_flow(flow_utils.get_rack_vthunder_update_member_flow,
                                                vthunder_conf, device_dict,
                                                store=store)
            else:
                busy = self._vthunder_busy_check(member[constants.PROJECT_ID], False, ctx_flags,
                                                 provider_lb)
                store={constants.MEMBER: member,
                           constants.LISTENERS: listeners_dicts,
                           constants.LOADBALANCER: provider_lb,
                           constants.LOADBALANCER_ID: load_balancer.id,
                           a10constants.COMPUTE_BUSY: busy,
                           constants.POOL: pool,
                           constants.POOL_ID: pool[constants.ID],
                           constants.UPDATE_DICT: member_updates,
                           a10constants.VTHUNDER_CONFIG: None,
                           a10constants.USE_DEVICE_FLAVOR: False,
                           constants.FLAVOR_ID: flavor_id,
                           constants.PROVISIONING_STATUS : db_member.to_dict()[constants.PROVISIONING_STATUS]}
                update_member_tf = self.run_flow(flow_utils.get_update_member_flow,topology,
                                                store=store)
                self._register_flow_notify_handler(update_member_tf, member[constants.PROJECT_ID], False,
                                                   busy, ctx_flags, provider_lb)

            update_member_tf.run()
        finally:
            self._set_vthunder_available(member[constants.PROJECT_ID], False, ctx_flags, provider_lb)

    @tenacity.retry(
        retry=tenacity.retry_if_exception_type(db_exceptions.NoResultFound),
        wait=tenacity.wait_incrementing(
            RETRY_INITIAL_DELAY, RETRY_BACKOFF, RETRY_MAX),
        stop=tenacity.stop_after_attempt(RETRY_ATTEMPTS))
    def create_pool(self, pool):
        """Creates a node pool.

        :param pool: Provider pool dict to create
        :returns: None
        :raises NoResultFound: Unable to find the object
        """
        session = db_apis.get_session()
        with session.begin():
            db_pool = self._pool_repo.get(session,
                                          id=pool[constants.POOL_ID])
        if not db_pool:
            LOG.warning('Failed to fetch %s %s from DB. Retrying for up to '
                        '60 seconds.', 'pool', pool[constants.POOL_ID])
            raise db_exceptions.NoResultFound

        load_balancer = db_pool.load_balancer
        listeners = db_pool.listeners
        flavor_id = load_balancer.to_dict().get(constants.FLAVOR_ID) if load_balancer.to_dict().get(constants.FLAVOR_ID) else CONF.a10_global.default_flavor_id
        default_listener = None
        if listeners:
            default_listener = db_pool.listeners[0].to_dict(recurse=True)
        provider_lb = provider_utils.db_loadbalancer_to_provider_loadbalancer(
            load_balancer).to_dict(recurse=True)
        listeners_dicts = provider_lb.get('listeners', [])
        
        topology = CONF.a10_controller_worker.loadbalancer_topology

        ctx_flags = [False]
        # rack flow _vthunder_busy_check() will always return False
        busy = self._vthunder_busy_check(pool[constants.PROJECT_ID], False, ctx_flags, provider_lb)
        
        store={constants.POOL_ID: pool[constants.POOL_ID],
                constants.POOL: pool,
                constants.LISTENER: default_listener,
                constants.LISTENERS: listeners_dicts,
                constants.LOADBALANCER_ID: provider_lb[constants.LOADBALANCER_ID],
                constants.LOADBALANCER: provider_lb,
                a10constants.COMPUTE_BUSY: busy,
                constants.FLAVOR_ID: flavor_id,
                constants.PROVISIONING_STATUS : db_pool.to_dict()[constants.PROVISIONING_STATUS]}
        
        try:
            create_pool_tf = self.run_flow(flow_utils.get_create_pool_flow, topology,store=store)
            self._register_flow_notify_handler(create_pool_tf, pool[constants.PROJECT_ID], False,
                                               busy, ctx_flags, provider_lb)
            create_pool_tf.run()
        finally:
            self._set_vthunder_available(pool[constants.PROJECT_ID], False, ctx_flags, provider_lb)

    def delete_pool(self, pool):
        """Deletes a node pool.

        :param pool: Provider pool dict to delete
        :returns: None
        :raises PoolNotFound: The referenced pool was not found
        """
        session = db_apis.get_session()
        with session.begin():
            db_pool = self._pool_repo.get(session,
                                          id=pool[constants.POOL_ID])

        load_balancer = db_pool.load_balancer
        listeners = db_pool.listeners
        flavor_id = load_balancer.to_dict().get(constants.FLAVOR_ID) if load_balancer.to_dict().get(constants.FLAVOR_ID) else CONF.a10_global.default_flavor_id
        default_listener = None
        if listeners:
            default_listener = db_pool.listeners[0].to_dict(recurse=True)
        provider_lb = provider_utils.db_loadbalancer_to_provider_loadbalancer(
            load_balancer).to_dict(recurse=True)
        listeners_dicts = provider_lb.get('listeners', [])
        members = db_pool.members
        health_monitor = db_pool.health_monitor

        mem_count = self._member_repo.get_member_count(
            db_apis.get_session(),
            project_id=db_pool.project_id)
        mem_count = mem_count - len(members) + 1
        store = {constants.POOL_ID: pool[constants.POOL_ID],
                 constants.LISTENERS: listeners_dicts,
                 constants.POOL: pool,
                 constants.LISTENER: default_listener,
                 constants.LOADBALANCER: provider_lb,
                 constants.LOADBALANCER_ID: provider_lb[constants.LOADBALANCER_ID],
                 constants.PROJECT_ID: provider_lb[constants.PROJECT_ID],
                 a10constants.MEMBER_COUNT: mem_count,
                 constants.FLAVOR_ID: flavor_id,
                 constants.PROVISIONING_STATUS : db_pool.to_dict()[constants.PROVISIONING_STATUS]}

        ctx_flags = [False]
        try:
            if self._is_rack_flow(pool[constants.PROJECT_ID], loadbalancer=provider_lb):
                vthunder_conf = CONF.hardware_thunder.devices.get(pool[constants.PROJECT_ID], None)
                device_dict = CONF.hardware_thunder.devices
                store.update([(a10constants.VTHUNDER_CONFIG, vthunder_conf),
                              (a10constants.DEVICE_CONFIG_DICT, device_dict)])
                delete_pool_tf = self.run_flow(flow_utils.get_delete_pool_rack_flow,
                                            members, health_monitor, store,store=store)
            else:
                topology = CONF.a10_controller_worker.loadbalancer_topology
                store.update({a10constants.USE_DEVICE_FLAVOR: False,
                              a10constants.POOLS: None})
                busy = self._vthunder_busy_check(pool[constants.PROJECT_ID], False, ctx_flags,
                                                 provider_lb, store)
                delete_pool_tf = self.run_flow(flow_utils.get_delete_pool_flow,
                                            members, health_monitor, store, topology,
                                            store=store)
                self._register_flow_notify_handler(delete_pool_tf, pool[constants.PROJECT_ID], False,
                                                   busy, ctx_flags, provider_lb)
                
            delete_pool_tf.run()
        finally:
            self._set_vthunder_available(pool[constants.PROJECT_ID], False, ctx_flags, provider_lb)

    def update_pool(self, origin_pool, pool_updates):
        """Updates a node pool.

        :param origin_pool: Provider pool dict to update
        :param pool_updates: Dict containing updated pool attributes
        :returns: None
        :raises PoolNotFound: The referenced pool was not found
        """

        try:
            db_pool = self._get_db_obj_until_pending_update(
                self._pool_repo, origin_pool[constants.POOL_ID])
        except tenacity.RetryError as e:
            LOG.warning('Pool did not go into %s in 60 seconds. '
                        'This either due to an in-progress Octavia upgrade '
                        'or an overloaded and failing database. Assuming '
                        'an upgrade is in progress and continuing.',
                        constants.PENDING_UPDATE)
            db_pool = e.last_attempt.result()

        load_balancer = db_pool.load_balancer
        provider_lb = provider_utils.db_loadbalancer_to_provider_loadbalancer(
            load_balancer).to_dict(recurse=True)
        listeners_dicts = provider_lb.get('listeners', [])
        listeners = db_pool.listeners
        flavor_id = load_balancer.to_dict().get(constants.FLAVOR_ID) if load_balancer.to_dict().get(constants.FLAVOR_ID) else CONF.a10_global.default_flavor_id
        default_listener = None
        if listeners:
            default_listener = db_pool.listeners[0].to_dict(recurse=True)

        topology = CONF.a10_controller_worker.loadbalancer_topology

        ctx_flags = [False]
        # rack flow _vthunder_busy_check() will always return False
        busy = self._vthunder_busy_check(origin_pool[constants.PROJECT_ID], False, ctx_flags, provider_lb)
        
        store={constants.POOL_ID: db_pool.id,
                constants.LISTENERS: listeners_dicts,
                constants.POOL: origin_pool,
                constants.LISTENER: default_listener,
                constants.LOADBALANCER: provider_lb,
                constants.LOADBALANCER_ID: provider_lb[constants.LOADBALANCER_ID],
                constants.UPDATE_DICT: pool_updates,
                a10constants.COMPUTE_BUSY: busy,
                constants.FLAVOR_ID: flavor_id,
                constants.PROVISIONING_STATUS : db_pool.to_dict()[constants.PROVISIONING_STATUS]}
        
        try:
            update_pool_tf = self.run_flow(flow_utils.get_update_pool_flow,
                                        topology, store=store)
            self._register_flow_notify_handler(update_pool_tf, origin_pool[constants.PROJECT_ID], False,
                                               busy, ctx_flags, provider_lb)
            update_pool_tf.run()
        finally:
            self._set_vthunder_available(origin_pool[constants.PROJECT_ID], False, ctx_flags, provider_lb)

    @tenacity.retry(
        retry=tenacity.retry_if_exception_type(db_exceptions.NoResultFound),
        wait=tenacity.wait_incrementing(
            RETRY_INITIAL_DELAY, RETRY_BACKOFF, RETRY_MAX),
        stop=tenacity.stop_after_attempt(RETRY_ATTEMPTS))
    def create_l7policy(self, l7policy):
        """Creates an L7 Policy.

        :param l7policy: Provider dict of the l7policy to create
        :returns: None
        :raises NoResultFound: Unable to find the object
        """
        session = db_apis.get_session()
        with session.begin():
            db_l7policy = self._l7policy_repo.get(
                session, id=l7policy[constants.L7POLICY_ID])
        if not db_l7policy:
            LOG.warning('Failed to fetch %s %s from DB. Retrying for up to '
                        '60 seconds.', 'l7policy',
                        l7policy[constants.L7POLICY_ID])
            raise db_exceptions.NoResultFound

        db_listener = db_l7policy.listener

        listeners_dicts = (
            provider_utils.db_listeners_to_provider_dicts_list_of_dicts(
                [db_listener]))
        load_balancer = db_listener.load_balancer.to_dict(recurse=True)
        
        provider_lb = provider_utils.db_loadbalancer_to_provider_loadbalancer(
            db_listener.load_balancer).to_dict(recurse=True)

        topology = CONF.a10_controller_worker.loadbalancer_topology

        ctx_flags = [False]
        # rack flow _vthunder_busy_check() will always return False
        busy = self._vthunder_busy_check(l7policy[constants.PROJECT_ID], False, ctx_flags, load_balancer)
        
        store={constants.L7POLICY: l7policy,
               constants.LISTENERS: listeners_dicts,
               constants.LOADBALANCER_ID: load_balancer[constants.ID],
               constants.LOADBALANCER: provider_lb,
               a10constants.COMPUTE_BUSY: busy}
        
        try:
            create_l7policy_tf = self.run_flow(flow_utils.get_create_l7policy_flow,topology,
                                            store=store)
            self._register_flow_notify_handler(create_l7policy_tf, l7policy[constants.PROJECT_ID], False,
                                               busy, ctx_flags, load_balancer)
            
            create_l7policy_tf.run()
        finally:
            self._set_vthunder_available(l7policy[constants.PROJECT_ID], False, ctx_flags, load_balancer)

    def delete_l7policy(self, l7policy):
        """Deletes an L7 policy.
        :param l7policy: Provider dict of the l7policy to delete
        :returns: None
        :raises L7PolicyNotFound: The referenced l7policy was not found
        """
        session = db_apis.get_session()
        with session.begin():
            db_listener = self._listener_repo.get(
                session, id=l7policy[constants.LISTENER_ID])
        listeners_dicts = (
            provider_utils.db_listeners_to_provider_dicts_list_of_dicts(
                [db_listener]))
        load_balancer = db_listener.load_balancer.to_dict(recurse=True)
        provider_lb = provider_utils.db_loadbalancer_to_provider_loadbalancer(
            db_listener.load_balancer).to_dict(recurse=True)
        
        topology = CONF.a10_controller_worker.loadbalancer_topology

        ctx_flags = [False]
        # rack flow _vthunder_busy_check() will always return False
        busy = self._vthunder_busy_check(l7policy[constants.PROJECT_ID], False, ctx_flags, load_balancer)
        store={constants.L7POLICY: l7policy,
               constants.LISTENERS: listeners_dicts,
               constants.LOADBALANCER_ID: load_balancer[constants.ID],
               constants.LOADBALANCER: provider_lb,
               a10constants.COMPUTE_BUSY: busy}
        try:
            delete_l7policy_tf = self.run_flow(flow_utils.get_delete_l7policy_flow,topology,
                                            store=store)
            self._register_flow_notify_handler(delete_l7policy_tf, l7policy[constants.PROJECT_ID], False,
                                               busy, ctx_flags, load_balancer)
            
            delete_l7policy_tf.run()
        finally:
            self._set_vthunder_available(l7policy[constants.PROJECT_ID], False, ctx_flags, load_balancer)

    def update_l7policy(self, original_l7policy, l7policy_updates):
        """Updates an L7 policy.

        :param l7policy: Provider dict of the l7policy to update
        :param l7policy_updates: Dict containing updated l7policy attributes
        :returns: None
        :raises L7PolicyNotFound: The referenced l7policy was not found
        """

        try:
            db_l7policy = self._get_db_obj_until_pending_update(
                self._l7policy_repo, original_l7policy[constants.L7POLICY_ID])
        except tenacity.RetryError as e:
            LOG.warning('L7 policy did not go into %s in 60 seconds. '
                        'This either due to an in-progress Octavia upgrade '
                        'or an overloaded and failing database. Assuming '
                        'an upgrade is in progress and continuing.',
                        constants.PENDING_UPDATE)
            db_l7policy = e.last_attempt.result()

        db_listener = db_l7policy.listener
        
        listeners_dicts = (
            provider_utils.db_listeners_to_provider_dicts_list_of_dicts(
                [db_listener]))
        
        load_balancer = db_listener.load_balancer.to_dict(recurse=True)
        provider_lb = provider_utils.db_loadbalancer_to_provider_loadbalancer(
            db_listener.load_balancer).to_dict(recurse=True)

        topology = CONF.a10_controller_worker.loadbalancer_topology

        ctx_flags = [False]
        # rack flow _vthunder_busy_check() will always return False
        busy = self._vthunder_busy_check(original_l7policy[constants.PROJECT_ID], False, ctx_flags, load_balancer)
        
        store={constants.L7POLICY: original_l7policy,
                constants.LISTENERS: listeners_dicts,
                constants.LOADBALANCER_ID: load_balancer[constants.ID],
                constants.LOADBALANCER: provider_lb,
                constants.UPDATE_DICT: l7policy_updates,
                a10constants.COMPUTE_BUSY: busy}
        
        try:
            update_l7policy_tf = self.run_flow(flow_utils.get_update_l7policy_flow,topology,
                                            store=store)
            self._register_flow_notify_handler(update_l7policy_tf, original_l7policy[constants.PROJECT_ID], False,
                                               busy, ctx_flags, load_balancer)

            update_l7policy_tf.run()
        finally:
            self._set_vthunder_available(original_l7policy[constants.PROJECT_ID], False, ctx_flags, load_balancer)

    @tenacity.retry(
        retry=tenacity.retry_if_exception_type(db_exceptions.NoResultFound),
        wait=tenacity.wait_incrementing(
            RETRY_INITIAL_DELAY, RETRY_BACKOFF, RETRY_MAX),
        stop=tenacity.stop_after_attempt(RETRY_ATTEMPTS))
    def create_l7rule(self, l7rule):
        """Creates an L7 Rule.

        :param l7rule: Provider dict l7rule
        :returns: None
        :raises NoResultFound: Unable to find the object
        """
        session = db_apis.get_session()
        with session.begin():
            db_l7rule = self._l7rule_repo.get(session,
                                              id=l7rule[constants.L7RULE_ID])
        if not db_l7rule:
            LOG.warning('Failed to fetch %s %s from DB. Retrying for up to '
                        '60 seconds.', 'l7rule',
                        l7rule[constants.L7RULE_ID])
            raise db_exceptions.NoResultFound

        db_l7policy = db_l7rule.l7policy

        listeners_dicts = (
            provider_utils.db_listeners_to_provider_dicts_list_of_dicts(
                [db_l7policy.listener]))
        l7policy_dict = provider_utils.db_l7policy_to_provider_l7policy(
            db_l7policy)

        provider_lb = provider_utils.db_loadbalancer_to_provider_loadbalancer(
            db_l7policy.listener.load_balancer).to_dict(recurse=True)
        topology = CONF.a10_controller_worker.loadbalancer_topology

        ctx_flags = [False]
        # rack flow _vthunder_busy_check() will always return False
        busy = self._vthunder_busy_check(l7rule[constants.PROJECT_ID], False, ctx_flags, provider_lb)
        
        store={constants.L7RULE: l7rule,
               constants.L7POLICY: l7policy_dict.to_dict(recurse=True),
               constants.L7POLICY_ID: db_l7policy.id,
               constants.LISTENERS: listeners_dicts,
               constants.LOADBALANCER_ID: provider_lb[constants.LOADBALANCER_ID],
               constants.LOADBALANCER: provider_lb,
               a10constants.COMPUTE_BUSY: busy}
        
        try:
            create_l7rule_tf = self.run_flow(flow_utils.get_create_l7rule_flow,topology,
                                            store=store)
            self._register_flow_notify_handler(create_l7rule_tf, l7rule[constants.PROJECT_ID], False,
                                               busy, ctx_flags, provider_lb)
            create_l7rule_tf.run()
        finally:
            self._set_vthunder_available(l7rule[constants.PROJECT_ID], False, ctx_flags, provider_lb)

    def delete_l7rule(self, l7rule):
        """Deletes an L7 rule.
        :param l7rule: Provider dict of the l7rule to delete
        :returns: None
        :raises L7RuleNotFound: The referenced l7rule was not found
        """
        session = db_apis.get_session()
        with session.begin():
            db_l7policy = self._l7policy_repo.get(
                session, id=l7rule[constants.L7POLICY_ID])
        l7policy = provider_utils.db_l7policy_to_provider_l7policy(db_l7policy)

        listeners_dicts = (
            provider_utils.db_listeners_to_provider_dicts_list_of_dicts(
                [db_l7policy.listener]))
        provider_lb = provider_utils.db_loadbalancer_to_provider_loadbalancer(
            db_l7policy.listener.load_balancer).to_dict(recurse=True)

        topology = CONF.a10_controller_worker.loadbalancer_topology

        ctx_flags = [False]
        # rack flow _vthunder_busy_check() will always return False
        busy = self._vthunder_busy_check(l7rule[constants.PROJECT_ID], False, ctx_flags, provider_lb)
        
        store={constants.L7RULE: l7rule,
               constants.L7POLICY: l7policy.to_dict(recurse=True),
               constants.LISTENERS: listeners_dicts,
               constants.L7POLICY_ID: db_l7policy.id,
               constants.LOADBALANCER_ID: provider_lb[constants.LOADBALANCER_ID],
               constants.LOADBALANCER: provider_lb,
               a10constants.COMPUTE_BUSY: busy}
        
        try:
            delete_l7rule_tf = self.run_flow(flow_utils.get_delete_l7rule_flow,
                                            topology,store=store)
            self._register_flow_notify_handler(delete_l7rule_tf, l7rule[constants.PROJECT_ID], False,
                                               busy, ctx_flags, provider_lb)
            delete_l7rule_tf.run()
        finally:
            self._set_vthunder_available(l7rule[constants.PROJECT_ID], False, ctx_flags, provider_lb)

    def update_l7rule(self, original_l7rule, l7rule_updates):
        """Updates an L7 rule.

        :param original_l7rule: Origin dict of the l7rule to update
        :param l7rule_updates: Dict containing updated l7rule attributes
        :returns: None
        :raises L7RuleNotFound: The referenced l7rule was not found
        """
        try:
            db_l7rule = self._get_db_obj_until_pending_update(
                self._l7rule_repo, original_l7rule[constants.L7RULE_ID])
        except tenacity.RetryError as e:
            LOG.warning('L7 rule did not go into %s in 60 seconds. '
                        'This either due to an in-progress Octavia upgrade '
                        'or an overloaded and failing database. Assuming '
                        'an upgrade is in progress and continuing.',
                        constants.PENDING_UPDATE)
            db_l7rule = e.last_attempt.result()
        db_l7policy = db_l7rule.l7policy

        listeners_dicts = (
            provider_utils.db_listeners_to_provider_dicts_list_of_dicts(
                [db_l7policy.listener]))
        l7policy_dict = provider_utils.db_l7policy_to_provider_l7policy(
            db_l7policy)

        provider_lb = provider_utils.db_loadbalancer_to_provider_loadbalancer(
            db_l7policy.listener.load_balancer).to_dict(recurse=True)

        topology = CONF.a10_controller_worker.loadbalancer_topology

        ctx_flags = [False]
        # rack flow _vthunder_busy_check() will always return False
        busy = self._vthunder_busy_check(original_l7rule[constants.PROJECT_ID], False, ctx_flags, provider_lb)
        
        store={constants.L7RULE: original_l7rule,
                constants.L7POLICY: l7policy_dict.to_dict(recurse=True),
                constants.LISTENERS: listeners_dicts,
                constants.L7POLICY_ID: db_l7policy.id,
                constants.LOADBALANCER_ID: provider_lb[constants.LOADBALANCER_ID],
                constants.LOADBALANCER: provider_lb,
                constants.UPDATE_DICT: l7rule_updates,
                a10constants.COMPUTE_BUSY: busy}
        
        try:
            update_l7rule_tf = self.run_flow(flow_utils.get_update_l7rule_flow,topology,
                                            store= store)
            self._register_flow_notify_handler(update_l7rule_tf, original_l7rule[constants.PROJECT_ID], False,
                                               busy, ctx_flags, provider_lb)
            update_l7rule_tf.run()
        finally:
            self._set_vthunder_available(original_l7rule[constants.PROJECT_ID], False, ctx_flags, provider_lb)

    def failover_amphora(self, vthunder_id, reraise=False):
        """Perform failover operations for an vThunder.
        :param vthunder_id: ID for vThunder to failover
        :param reraise: If enabled reraise any caught exception
        :returns: None
        """
        try:
            vthunder = self._vthunder_repo.get(db_apis.get_session(),
                                               vthunder_id=vthunder_id)
            # session = db_apis.get_session()
            # with session.begin():
            #     amphora = self._vthunder_repo.get(session,
            #                                      id=vthunder_id)
            if not vthunder:
                LOG.warning("Could not fetch vThunder %s from DB, ignoring "
                            "failover request.", vthunder.vthunder_id)
                return

            LOG.info("Starting Failover process on %s", vthunder.ip_address)

            store = {a10constants.VTHUNDER: vthunder,
                     a10constants.FAILOVER_VTHUNDER: vthunder}
            failover_tf = None
            if vthunder.topology == a10constants.TOPOLOGY_SPARE:
                failover_tf = self.run_flow(
                    flow_utils.get_failover_spare_vthunder_flow,
                    store=store)
            elif vthunder.topology == constants.TOPOLOGY_ACTIVE_STANDBY:
                health_vthunder_count = self._vthunder_repo.get_health_vthunder_count_for_lb(
                    db_apis.get_session(), vthunder.loadbalancer_id)
                if health_vthunder_count > 0:
                    failover_tf = self.run_flow(
                        flow_utils.get_failover_vcs_vthunder_flow,store=store)
                else:
                    LOG.warning("Failover for a total HA Pair failure is not supported. "
                                "Pair will be kept in failed state.")
                    failover_tf = self.run_flow(
                        flow_utils.get_failover_restore_vthunder_flow,
                        store=store)

            if failover_tf:
                failover_tf.run()

        except Exception as e:
            with excutils.save_and_reraise_exception():
                LOG.error("vThunder %(id)s topology %(topology)s failover exception: %(exc)s",
                          {'id': vthunder_id, 'topology': vthunder.topology, 'exc': e})

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
        session = db_apis.get_session()
        with session.begin():
            return repo.get(session, id=id)

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
                write_mem_tf = self.run_flow(flow_utils.get_write_memory_flow,vthunder, store, delete_compute,store=store)
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
                reload_check_tf = self.run_flow(flow_utils.get_reload_check_flow,vthunder, store,store=store)
                reload_check_tf.run()
            except Exception:
                # continue on other thunders (assume exception is logged)
                pass

    def perform_vthunder_stats_update(self, ip):
        """Perform for listener statistics update"""

        store = {}
        try:
            thunders = self._vthunder_repo.get_all_vthunder_by_address(
                db_apis.get_session(),
                ip_address=ip)
            for vthunder in thunders:
                vthunder_stats_tf = self.run_flow(flow_utils.get_listener_stats_flow,vthunder, store,store=store)
                vthunder_stats_tf.run()
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

    def delete_load_balancer_with_housekeeping(self, pending_lb, cascade=True):
        """Function to delete load balancer for A10 provider using Housekeeper thread"""
        if pending_lb[constants.PROJECT_ID] in CONF.hardware_thunder.devices:
            try:
                vthunder = self._vthunder_repo.get_vthunder_from_lb(
                    db_apis.get_session(), pending_lb[constants.ID])
                if vthunder is not None:
                    if vthunder.compute_id is not None:
                        return
                    else:
                        self._vthunder_repo.update(
                            db_apis.get_session(),
                            vthunder.id,
                            status=constants.ACTIVE)
                self._lb_repo.update(db_apis.get_session(),
                                     pending_lb[constants.ID],
                                     provisioning_status=constants.ERROR)
            except Exception as e:
                LOG.exception("Failed to update load balancer %(lb) "
                              "provisioning status to ERROR due to: "
                              "%(except)s", {'lb': pending_lb[constants.ID], 'except': e})
                raise e
            lb = self._lb_repo.get(db_apis.get_session(), id=pending_lb[constants.ID])
            lb = lb.to_dict(recurse=True)
            lb[constants.LOADBALANCER_ID] = lb.pop(constants.ID)
            flavor_id = lb.get(constants.FLAVOR_ID) if lb.get(constants.FLAVOR_ID) else CONF.a10_global.default_flavor_id
            vthunder = self._vthunder_repo.get_vthunder_from_lb(db_apis.get_session(),
                                                                lb[constants.LOADBALANCER_ID])
            listener_dicts = lb.get(constants.LISTENERS)
            try:
                vthunder_conf = CONF.hardware_thunder.devices.get(lb[constants.PROJECT_ID], None)
                device_dict = CONF.hardware_thunder.devices
                (flow, store) = flow_utils.get_delete_rack_vthunder_load_balancer_flow(
                    lb, cascade,listener_dicts,
                    vthunder_conf=vthunder_conf, device_dict=device_dict)
                store.update({constants.LOADBALANCER: lb,
                              a10constants.COMPUTE_BUSY: False,
                              constants.VIP: lb.get(constants.VIP),
                              constants.SERVER_GROUP_ID: lb.get(constants.SERVER_GROUP_ID),
                              constants.PROJECT_ID: lb[constants.PROJECT_ID],
                              constants.FLAVOR_ID: flavor_id,
                              constants.PROVISIONING_STATUS : lb[constants.PROVISIONING_STATUS]})
                delete_lb_tf = self.tf_engine.taskflow_load(flow, store=store)
                delete_lb_tf.run()
            except Exception as e:
                pass