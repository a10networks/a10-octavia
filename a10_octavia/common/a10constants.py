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

GET_VTHUNDER_FOR_LB_SUBFLOW = 'octavia-get-vthunder-for-lb-subflow'

VTHUNDER = 'vthunder'
STATUS = 'status'
ROLE = 'role'
BACKUP_VTHUNDER = 'backup_vthunder'
VRRP_STATUS = 'vrrp_status'
MASTER_VRRP_STATUS = 'master_vrrp_status'
BACKUP_VRRP_STATUS = 'backup_vrrp_status'
NAT_POOL = 'nat_pool'
NAT_FLAVOR = 'nat_flavor'
SUBNET_PORT = 'subnet_port'
WRITE_MEM_SHARED = 'write_mem_shared'
WRITE_MEM_PRIVATE = 'write_mem_private'

FAILED = 'FAILED'
USED_SPARE = 'USED_SPARE'
OCTAVIA_HEALTH_MANAGER_CONTROLLER = 'octavia_health_manager_controller'
OCTAVIA_HEALTH_MONITOR = 'octavia_health_monitor'
VTHUNDER_CONFIG = 'vthunder_config'
VTHUNDER_ID = "vthunder_id"
DEVICE_ID = "device_id"
SET_ID = "set_id"
VRID = "vrid"
DEVICE_PRIORITY = 'device_priority'
FLOATING_IP = 'floating_ip'
FLOATING_IP_MASK = 'floating_ip_mask'
CERT_DATA = 'cert_data'
SP_OBJ_DICT = {
    'HTTP_COOKIE': "cookie_persistence",
    'APP_COOKIE': "cookie_persistence",
    'SOURCE_IP': "src_ip_persistence",
}
HTTP_TYPE = ['HTTP', 'HTTPS']
PERS_TYPE = ['cookie_persistence', 'src_ip_persistence']
NO_DEST_NAT_SUPPORTED_PROTOCOL = ['tcp', 'udp']
PORT = 'port'
LB_COUNT = 'lb_count'
MEMBER_COUNT = 'member_count'
DELETE_VRID = 'delete_vrid'

LB_RESOURCE = 'lb_resource'

SUBNET_ID = "subnet_id"
VLAN_ID = "vlan_id"
TAG_INTERFACE = "tag_interface"
VE_INTERFACE = "ve_interface"
DELETE_VLAN = "delete_vlan"
VLAN = "vlan"
FLAT = "flat"
SUPPORTED_NETWORK_TYPE = [FLAT, VLAN]
SSL_TEMPLATE = "ssl_template"

# Taskflow flow and task names

BACKUP_AMPHORA_PLUG = 'backup-amphora-plug'
MASTER_CONNECTIVITY_WAIT = 'master-connectivity-wait'
BACKUP_CONNECTIVITY_WAIT = 'backup-connectivity-wait'
BACKUP_ENABLE_INTERFACE = 'backup-enable-interface'
MARK_VTHUNDER_MASTER_ACTIVE_IN_DB = 'mark-vthunder-master-active-in-db'
MARK_VTHUNDER_BACKUP_ACTIVE_IN_DB = 'mark-vthunder-backup-active-in-db'
GET_BACKUP_VTHUNDER_BY_LB = 'get-backup-vthunder-by-lb'
CREATE_HEALTH_MONITOR_ON_VTHUNDER_MASTER = 'create-health-monitor-on-vthunder-master'
HANDLE_SESS_PERS = 'handle-session-persistence-delta-subflow'
GET_LOADBALANCER_FROM_DB = 'Get-Loadbalancer-from-db'
GET_BACKUP_LOADBALANCER_FROM_DB = 'get-backup-loadbalancer-from-db'
CONFIGURE_VRRP_FOR_MASTER_VTHUNDER = 'configure-vrrp-for-master-vthunder'
CONFIGURE_VRRP_FOR_BACKUP_VTHUNDER = 'configure-vrrp-for-backup-vthunder'
CONFIGURE_VRID_FOR_MASTER_VTHUNDER = 'configure-vrid-for-master-vthunder'
CONFIGURE_VRID_FOR_BACKUP_VTHUNDER = 'configure-vrid-for-backup-vthunder'
CONFIGURE_VRRP_SYNC = 'configure-vrrp-sync'
WAIT_FOR_MASTER_SYNC = 'wait-for-master-sync'
WAIT_FOR_BACKUP_SYNC = 'wait-for-backup-sync'
CONFIGURE_AVCS_SYNC_FOR_MASTER = 'configure-avcs-sync-for-master'
CONFIGURE_AVCS_SYNC_FOR_BACKUP = 'configure-avcs-sync-for-backup'
CHECK_VRRP_STATUS = 'check-vrrp-status'
CHECK_VRRP_MASTER_STATUS = 'check-vrrp-master-status'
CHECK_VRRP_BACKUP_STATUS = 'check-vrrp-backup-status'
CONFIRM_VRRP_STATUS = 'confirm-vrrp-status'
ALLOCATE_VIP = 'allocate-vip'
UPDATE_VIP_AFTER_ALLOCATION = 'update-vip-after-allocation'
CREATE_VTHUNDER_ENTRY = 'create-vthunder-entry'
VTHUNDER_BY_LB = 'vthunder-by-loadbalancer'
CHANGE_PARTITION = 'change-partition'
CREATE_SSL_CERT_FLOW = 'create-ssl-cert-flow'
DELETE_SSL_CERT_FLOW = 'delete-ssl-cert-flow'
LISTENER_TYPE_DECIDER_FLOW = 'listener_type_decider_flow'
DELETE_LOADBALANCER_VRID_SUBFLOW = 'delete-loadbalancer-vrid-subflow'
HANDLE_VRID_LOADBALANCER_SUBFLOW = 'handle-vrid-loadbalancer-subflow'
DELETE_MEMBER_VTHUNDER_INTERNAL_SUBFLOW = 'delete-member-vthunder-internal-subflow'
DELETE_MEMBER_VRID_SUBFLOW = 'delete-member-vrid-subflow'
DELETE_MEMBER_VRID_INTERNAL_SUBFLOW = 'delete-member-vrid-internal-subflow'
DELETE_HEALTH_MONITOR_VTHUNDER_SUBFLOW = 'delete-hm-vthunder-subflow'
DELETE_HEALTH_MONITOR_SUBFLOW_WITH_POOL_DELETE_FLOW = 'delete-health-monitor-subflow' \
                                                      '-with-pool-delete-flow'
DELETE_MEMBERS_SUBFLOW_WITH_POOL_DELETE_FLOW = 'delete-members-subflow-with-pool-delete-flow'
HANDLE_VRID_MEMBER_SUBFLOW = 'handle-vrid-member-subflow'
SPARE_VTHUNDER_CREATE = 'spare-vthunder-create'
WRITE_MEMORY_THUNDER_FLOW = 'write-memory-thunder-flow'
RELOAD_CHECK_THUNDER_FLOW = 'reload-check-thunder-flow'
LB_TO_VTHUNDER_SUBFLOW = 'lb-to-vthunder-subflow'
LOADBALANCERS_LIST = 'loadbalancers_list'
VRID_LIST = 'vrid_list'
RESOURCE_COUNT = 'resource_count'

# Member count with specific IP.
MEMBER_COUNT_IP = 'member_count_ip'
MEMBER_COUNT_IP_PORT_PROTOCOL = 'member_count_ip_port_protocol'
POOL_COUNT_IP = 'pool_count_ip'
WRITE_MEM_SHARED_PART = 'write_mem_shared_part'
WRITE_MEM_FOR_SHARED_PARTITION = 'write_memory_for_shared_partition'
WRITE_MEM_FOR_LOCAL_PARTITION = 'write_memory_for_local_partition'

MEMBER_LIST = 'member_list'
SUBNET_LIST = 'subnet_list'

PARTITION_PROJECT_LIST = 'partition_project_list'
