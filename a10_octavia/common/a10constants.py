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
