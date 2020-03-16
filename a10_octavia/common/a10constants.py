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
FLOATING_MASK = 'floating_mask'
SP_OBJ_DICT = {
    'HTTP_COOKIE': "cookie_persistence",
    'APP_COOKIE': "cookie_persistence",
    'SOURCE_IP': "src_ip_persistence",
}
HM_TYPE = ['HTTP', 'HTTPS']
PERS_TYPE = ['cookie_persistence', 'src_ip_persistence']
# Taskflow flow and task names

MARK_VTHUNDER_MASTER_ACTIVE_IN_DB = 'mark-vthunder-master-active-in-db'
MARK_VTHUNDER_BACKUP_ACTIVE_IN_DB = 'mark-vthunder-backup-active-in-db'
GET_BACKUP_VTHUNDER_BY_LB = 'get-backup-vthunder-by-lb'
CREATE_HEALTH_MONITOR_ON_VTHUNDER_MASTER = 'create-health-monitor-on-vthunder-master'
HANDLE_SESS_PERS = 'handle-session-persistence-delta-subflow'
GET_LOADBALANCER_FROM_DB = 'Get_Loadbalancer_from_db'
GET_BACKUP_LOADBALANCER_FROM_DB = 'get_backup_loadbalancer_from_db'
CONFIGURE_VRRP_FOR_MASTER_VTHUNDER = 'configure_vrrp_for_master_vthunder'
CONFIGURE_VRRP_FOR_BACKUP_VTHUNDER = 'configure_vrrp_for_backup_vthunder'
CONFIGURE_VRID_FOR_MASTER_VTHUNDER = 'configure_vrid_for_master_vthunder'
CONFIGURE_VRID_FOR_BACKUP_VTHUNDER = 'configure_vrid_for_backup_vthunder'
CONFIGURE_VRRP_SYNC = 'configure_vrrp_sync'
WAIT_FOR_MASTER_SYNC = 'wait_for_master_sync'
WAIT_FOR_BACKUP_SYNC = 'wait_for_backup_sync'
CONFIGURE_AVCS_SYNC_FOR_MASTER = 'configure_avcs_sync_for_master'
CONFIGURE_AVCS_SYNC_FOR_BACKUP = 'configure_avcs_sync_for_backup'
CHECK_VRRP_STATUS = 'check_vrrp_status'
