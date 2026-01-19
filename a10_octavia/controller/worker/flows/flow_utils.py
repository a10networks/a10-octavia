#    Copyright 2025, A10 Networks
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

from a10_octavia.controller.worker.flows import a10_health_monitor_flows
from a10_octavia.controller.worker.flows import a10_l7policy_flows
from a10_octavia.controller.worker.flows import a10_l7rule_flows
from a10_octavia.controller.worker.flows import a10_listener_flows
from a10_octavia.controller.worker.flows import a10_load_balancer_flows
from a10_octavia.controller.worker.flows import a10_member_flows
from a10_octavia.controller.worker.flows import a10_pool_flows
from a10_octavia.controller.worker.flows import vthunder_flows

LB_FLOWS = a10_load_balancer_flows.LoadBalancerFlows()
HM_FLOWS = a10_health_monitor_flows.HealthMonitorFlows()
L7_POLICY_FLOWS = a10_l7policy_flows.L7PolicyFlows()
L7_RULES_FLOWS = a10_l7rule_flows.L7RuleFlows()
LISTENER_FLOWS = a10_listener_flows.ListenerFlows()
M_FLOWS = a10_member_flows.MemberFlows()
P_FLOWS = a10_pool_flows.PoolFlows()
VTH_FLOWS = vthunder_flows.VThunderFlows()


def get_create_rack_vthunder_load_balancer_flow(vthunder_conf, device_dict, topology, listeners=None, pools=None):
    return LB_FLOWS.get_create_rack_vthunder_load_balancer_flow(
        vthunder_conf, device_dict, topology, listeners=listeners, pools=pools)

def get_create_load_balancer_flow(load_balancer, topology, project_id,
                                      listeners=None, pools=None):
    return LB_FLOWS.get_create_load_balancer_flow(
        load_balancer, topology, project_id, listeners=listeners, pools=pools)

def get_delete_rack_vthunder_load_balancer_flow(lb, cascade, listeners, vthunder_conf, device_dict):
    return LB_FLOWS.get_delete_rack_vthunder_load_balancer_flow(lb, cascade, listeners, vthunder_conf, device_dict)

def get_delete_load_balancer_flow(lb, listeners, deleteCompute, cascade):
    return LB_FLOWS.get_delete_load_balancer_flow(lb, listeners, deleteCompute, cascade)

def get_update_rack_load_balancer_flow(vthunder_conf, device_dict, topology):
    return LB_FLOWS.get_update_rack_load_balancer_flow(vthunder_conf, device_dict, topology)

def get_update_load_balancer_flow(topology):
    return LB_FLOWS.get_update_load_balancer_flow(topology)

def get_create_health_monitor_flow(topology):
    return HM_FLOWS.get_create_health_monitor_flow(topology)


def get_delete_health_monitor_flow(topology):
    return HM_FLOWS.get_delete_health_monitor_flow(topology)


def get_update_health_monitor_flow(topology):
    return HM_FLOWS.get_update_health_monitor_flow(topology)


def get_create_l7policy_flow(topology):
    return L7_POLICY_FLOWS.get_create_l7policy_flow(topology)


def get_delete_l7policy_flow(topology):
    return L7_POLICY_FLOWS.get_delete_l7policy_flow(topology)


def get_update_l7policy_flow(topology):
    return L7_POLICY_FLOWS.get_update_l7policy_flow(topology)


def get_create_l7rule_flow(topology):
    return L7_RULES_FLOWS.get_create_l7rule_flow(topology)


def get_delete_l7rule_flow(topology):
    return L7_RULES_FLOWS.get_delete_l7rule_flow(topology)


def get_update_l7rule_flow(topology):
    return L7_RULES_FLOWS.get_update_l7rule_flow(topology)

def get_rack_vthunder_create_listener_flow(project_id):
    return LISTENER_FLOWS.get_rack_vthunder_create_listener_flow(project_id)

def get_create_listener_flow(topology):
    return LISTENER_FLOWS.get_create_listener_flow(topology)

def get_delete_listener_flow(topology):
    return LISTENER_FLOWS.get_delete_listener_flow(topology)

def get_delete_rack_listener_flow():
    return LISTENER_FLOWS.get_delete_rack_listener_flow()

def get_update_listener_flow(topology):
    return LISTENER_FLOWS.get_update_listener_flow(topology)

def get_rack_vthunder_create_member_flow(vthunder_conf, device_dict):
    return M_FLOWS.get_rack_vthunder_create_member_flow(vthunder_conf, device_dict)

def get_create_member_flow(topology):
    return M_FLOWS.get_create_member_flow(topology)

def get_rack_vthunder_delete_member_flow(vthunder_conf, device_dict):
    return M_FLOWS.get_rack_vthunder_delete_member_flow(vthunder_conf, device_dict)

def get_delete_member_flow(topology):
    return M_FLOWS.get_delete_member_flow(topology)

def get_rack_vthunder_batch_update_members_flow(old_members, new_members,updated_members, vthunder_conf, device_dict, pool):
    return M_FLOWS.get_rack_vthunder_batch_update_members_flow(old_members, new_members,updated_members, vthunder_conf, device_dict, pool)

def get_batch_update_members_flow(old_members, new_members, updated_members, topology, pool):
    return M_FLOWS.get_batch_update_members_flow(old_members, new_members, updated_members,topology, pool)

def get_rack_vthunder_update_member_flow(vthunder_conf, device_dict):
    return M_FLOWS.get_rack_vthunder_update_member_flow(vthunder_conf, device_dict)

def get_update_member_flow(topology):
    return M_FLOWS.get_update_member_flow(topology)

def get_create_pool_flow(topology):
    return P_FLOWS.get_create_pool_flow(topology)

def get_delete_pool_rack_flow( members, health_mon, store):
    return P_FLOWS.get_delete_pool_rack_flow( members, health_mon, store)

def get_delete_pool_flow(members, health_mon, store,topology):
    return P_FLOWS.get_delete_pool_flow(members, health_mon, store,topology)

def get_update_pool_flow(topology):
    return P_FLOWS.get_update_pool_flow(topology)

def get_create_vthunder_flow():
    return VTH_FLOWS.get_create_vthunder_flow()

def get_write_memory_flow(vthunder, store, deleteCompute):
    return VTH_FLOWS.get_write_memory_flow(vthunder, store, deleteCompute)

def get_reload_check_flow(vthunder, store):
    return VTH_FLOWS.get_reload_check_flow( vthunder, store)

def get_listener_stats_flow(vthunder, store):
    return LISTENER_FLOWS.get_listener_stats_flow(vthunder, store)

def get_failover_vcs_vthunder_flow():
    return VTH_FLOWS.get_failover_vcs_vthunder_flow()

def get_failover_spare_vthunder_flow():
    return VTH_FLOWS.get_failover_spare_vthunder_flow()

def get_failover_restore_vthunder_flow():
    return VTH_FLOWS.get_failover_restore_vthunder_flow()