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

# Taskflow flow and task names

MARK_VTHUNDER_MASTER_ACTIVE_INDB = 'mark-vthunder-master-active-indb'
MARK_VTHUNDER_BACKUP_ACTIVE_INDB = 'mark-vthunder-backup-active-indb'
GET_BACKUP_VTHUNDER_BY_LB = 'get-backup-vthunder-by-lb'
CREATE_HEALTH_MONITOR_ON_VTHUNDER_MASTER = 'create-health-monitor-on-vthunder-master'
