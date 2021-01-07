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

from jsonschema import exceptions as js_exceptions
from jsonschema import validate
from oslo_config import cfg
from oslo_log import log as logging
import oslo_messaging as messaging

from octavia.common import constants
from octavia_lib.api.drivers import exceptions
from octavia_lib.api.drivers import provider_base as driver_base

from a10_octavia.api.drivers import flavor_schema


CONF = cfg.CONF
CONF.import_group('oslo_messaging', 'octavia.common.config')
LOG = logging.getLogger(__name__)


class A10ProviderDriver(driver_base.ProviderDriver):
    def __init__(self):
        super(A10ProviderDriver, self).__init__()
        self._args = {}
        self.transport = messaging.get_rpc_transport(cfg.CONF)
        self._args['fanout'] = False
        self._args['namespace'] = constants.RPC_NAMESPACE_CONTROLLER_AGENT
        self._args['topic'] = "a10_octavia"
        self._args['version'] = '1.0'
        self.target = messaging.Target(**self._args)
        self.client = messaging.RPCClient(self.transport, target=self.target)

    # Load Balancer
    def loadbalancer_create(self, loadbalancer):
        LOG.info('A10 provider load balancer loadbalancer: %s.', loadbalancer.__dict__)
        payload = {constants.LOAD_BALANCER_ID: loadbalancer.loadbalancer_id,
                   constants.FLAVOR: loadbalancer.flavor}
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

    def listener_update(self, old_listener, new_listener):
        listener_dict = new_listener.to_dict()
        if 'admin_state_up' in listener_dict:
            listener_dict['enabled'] = listener_dict.pop('admin_state_up')
        listener_id = listener_dict.pop('listener_id')
        if 'client_ca_tls_container_ref' in listener_dict:
            listener_dict['client_ca_tls_container_id'] = listener_dict.pop(
                'client_ca_tls_container_ref')
        listener_dict.pop('client_ca_tls_container_data', None)
        if 'client_crl_container_ref' in listener_dict:
            listener_dict['client_crl_container_id'] = listener_dict.pop(
                'client_crl_container_ref')
        listener_dict.pop('client_crl_container_data', None)

        payload = {constants.LISTENER_ID: listener_id,
                   constants.LISTENER_UPDATES: listener_dict}
        self.client.cast({}, 'update_listener', **payload)

    def pool_create(self, pool):
        payload = {constants.POOL_ID: pool.pool_id}
        self.client.cast({}, 'create_pool', **payload)

    def pool_delete(self, pool):
        pool_id = pool.pool_id
        payload = {constants.POOL_ID: pool_id}
        self.client.cast({}, 'delete_pool', **payload)

    def pool_update(self, old_pool, new_pool):
        pool_dict = new_pool.to_dict()
        if 'admin_state_up' in pool_dict:
            pool_dict['enabled'] = pool_dict.pop('admin_state_up')
        pool_id = pool_dict.pop('pool_id')
        if 'tls_container_ref' in pool_dict:
            pool_dict['tls_container_id'] = pool_dict.pop('tls_container_ref')
        pool_dict.pop('tls_container_data', None)
        if 'ca_tls_container_ref' in pool_dict:
            pool_dict['ca_tls_certificate_id'] = pool_dict.pop(
                'ca_tls_container_ref')
        pool_dict.pop('ca_tls_container_data', None)
        if 'client_crl_container_ref' in pool_dict:
            pool_dict['client_crl_container_id'] = pool_dict.pop(
                'client_crl_container_ref')
        pool_dict.pop('client_crl_container_data', None)

        payload = {constants.POOL_ID: pool_id,
                   constants.POOL_UPDATES: pool_dict}
        self.client.cast({}, 'update_pool', **payload)

    def member_create(self, member):
        payload = {constants.MEMBER_ID: member.member_id}
        self.client.cast({}, 'create_member', **payload)

    def member_delete(self, member):
        member_id = member.member_id
        payload = {constants.MEMBER_ID: member_id}
        self.client.cast({}, 'delete_member', **payload)

    def member_update(self, old_member, new_member):
        member_dict = new_member.to_dict()
        if 'admin_state_up' in member_dict:
            member_dict['enabled'] = member_dict.pop('admin_state_up')
        member_id = member_dict.pop('member_id')

        payload = {constants.MEMBER_ID: member_id,
                   constants.MEMBER_UPDATES: member_dict}
        self.client.cast({}, 'update_member', **payload)

    # Health Monitor
    def health_monitor_create(self, healthmonitor):
        payload = {constants.HEALTH_MONITOR_ID: healthmonitor.healthmonitor_id}
        self.client.cast({}, 'create_health_monitor', **payload)

    def health_monitor_delete(self, healthmonitor):
        healthmonitor_id = healthmonitor.healthmonitor_id
        payload = {constants.HEALTH_MONITOR_ID: healthmonitor_id}
        self.client.cast({}, 'delete_health_monitor', **payload)

    def health_monitor_update(self, old_healthmonitor, new_healthmonitor):
        healthmon_dict = new_healthmonitor.to_dict()
        if 'admin_state_up' in healthmon_dict:
            healthmon_dict['enabled'] = healthmon_dict.pop('admin_state_up')
        if 'max_retries_down' in healthmon_dict:
            healthmon_dict['fall_threshold'] = healthmon_dict.pop(
                'max_retries_down')
        if 'max_retries' in healthmon_dict:
            healthmon_dict['rise_threshold'] = healthmon_dict.pop(
                'max_retries')
        healthmon_id = healthmon_dict.pop('healthmonitor_id')

        payload = {constants.HEALTH_MONITOR_ID: healthmon_id,
                   constants.HEALTH_MONITOR_UPDATES: healthmon_dict}
        self.client.cast({}, 'update_health_monitor', **payload)

    # L7Policy

    def l7policy_create(self, l7policy):
        payload = {constants.L7POLICY_ID: l7policy.l7policy_id}
        self.client.cast({}, 'create_l7policy', **payload)

    def l7policy_delete(self, l7policy):
        l7policy_id = l7policy.l7policy_id
        payload = {constants.L7POLICY_ID: l7policy_id}
        self.client.cast({}, 'delete_l7policy', **payload)

    def l7policy_update(self, old_l7policy, new_l7policy):
        l7policy_dict = new_l7policy.to_dict()
        if 'admin_state_up' in l7policy_dict:
            l7policy_dict['enabled'] = l7policy_dict.pop('admin_state_up')
        l7policy_id = l7policy_dict.pop('l7policy_id')

        payload = {constants.L7POLICY_ID: l7policy_id,
                   constants.L7POLICY_UPDATES: l7policy_dict}
        self.client.cast({}, 'update_l7policy', **payload)

    # L7 Rule

    def l7rule_create(self, l7rule):
        payload = {constants.L7RULE_ID: l7rule.l7rule_id}
        self.client.cast({}, 'create_l7rule', **payload)

    def l7rule_delete(self, l7rule):
        l7rule_id = l7rule.l7rule_id
        payload = {constants.L7RULE_ID: l7rule_id}
        self.client.cast({}, 'delete_l7rule', **payload)

    def l7rule_update(self, old_l7rule, new_l7rule):
        l7rule_dict = new_l7rule.to_dict()
        if 'admin_state_up' in l7rule_dict:
            l7rule_dict['enabled'] = l7rule_dict.pop('admin_state_up')
        l7rule_id = l7rule_dict.pop('l7rule_id')

        payload = {constants.L7RULE_ID: l7rule_id,
                   constants.L7RULE_UPDATES: l7rule_dict}
        self.client.cast({}, 'update_l7rule', **payload)

    # Flavor
    def get_supported_flavor_metadata(self):
        try:
            dict = {}
            for obj in flavor_schema.SUPPORTED_FLAVOR_SCHEMA['properties']:
                obj_v = flavor_schema.SUPPORTED_FLAVOR_SCHEMA['properties'][obj]
                if 'description' in obj_v:
                    dict[obj] = obj_v.get('description')
                if 'properties' in obj_v:
                    props = obj_v['properties']
                    for k, v in props.items():
                        if 'description' in v:
                            dict[obj + '.' + k] = v.get('description')
            return dict
        except Exception as e:
            raise exceptions.DriverError(
                user_fault_string='Failed to get the supported flavor '
                                  'metadata due to: {}'.format(str(e)),
                operator_fault_string='Failed to get the supported flavor '
                                      'metadata due to: {}'.format(str(e)))

    def validate_flavor(self, flavor_dict):
        try:
            validate(flavor_dict, flavor_schema.SUPPORTED_FLAVOR_SCHEMA)

            # validate flavor for slb objects
            if 'virtual-server' in flavor_dict:
                flavor = flavor_dict['virtual-server']
                if 'name' in flavor:
                    raise Exception('axapi key \'name\' is not allowed')
                if 'ip-address' in flavor:
                    raise Exception('axapi key \'ip-address\' is not supported yet')
            if 'virtual-port' in flavor_dict:
                flavor = flavor_dict['virtual-port']
                if 'name' in flavor:
                    raise Exception('axapi key \'name\' is not allowed')
                if 'port-number' in flavor:
                    raise Exception('axapi key \'port-number\' is not allowed')
                if 'protocol' in flavor:
                    raise Exception('axapi key \'protocol\' is not allowed')
            if 'service-group' in flavor_dict:
                flavor = flavor_dict['service-group']
                if 'name' in flavor:
                    raise Exception('axapi key \'name\' is not allowed')
            if 'server' in flavor_dict:
                flavor = flavor_dict['server']
                if 'name' in flavor:
                    raise Exception('axapi key \'name\' is not allowed')
            if 'health-monitor' in flavor_dict:
                flavor = flavor_dict['health-monitor']
                if 'name' in flavor:
                    raise Exception('axapi key \'name\' is not allowed')

            # validate nat-pool and nat-pool-list keys
            if 'nat-pool' in flavor_dict:
                nat = flavor_dict['nat-pool']
                if 'pool-name' not in nat:
                    raise Exception('pool-name is required for nat-pool flavor')
                if 'start-address' not in nat:
                    raise Exception('start-address is required for nat-pool flavor')
                if 'end-address' not in nat:
                    raise Exception('end-address is required for nat-pool flavor')
                if 'netmask' not in nat:
                    raise Exception('netmask is required for nat-pool flavor')
            if 'nat-pool-list' in flavor_dict:
                for nat in flavor_dict['nat-pool-list']:
                    if 'pool-name' not in nat:
                        raise Exception('pool-name is required for nat-pool-list flavor')
                    if 'start-address' not in nat:
                        raise Exception('start-address is required for nat-pool-list flavor')
                    if 'end-address' not in nat:
                        raise Exception('end-address is required for nat-pool-list flavor')
                    if 'netmask' not in nat:
                        raise Exception('netmask is required for nat-pool-list flavor')
        except js_exceptions.ValidationError as e:
            error_object = ''
            if e.relative_path:
                error_object = '{} '.format(e.relative_path[0])
            raise exceptions.UnsupportedOptionError(
                user_fault_string='{0}{1}'.format(error_object, e.message),
                operator_fault_string=str(e))
        except Exception as e:
            raise exceptions.DriverError(
                user_fault_string='Failed to validate the flavor metadata '
                                  'due to: {}'.format(str(e)),
                operator_fault_string='Failed to validate the flavor metadata '
                                      'due to: {}'.format(str(e)))
