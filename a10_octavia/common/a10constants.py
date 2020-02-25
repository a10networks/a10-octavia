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

# Flow names
GET_VTHUNDER_FOR_LB_SUBFLOW = 'octavia-get-vthunder-for-lb-subflow'

GET_FLAT_NET_SUBFLOW = 'octavia-get-flat-net-subflow'
GET_VLAN_NET_SUBFLOW = 'octavia-get-vlan-net-subflow'

NETWORK_TYPE_HANDLER_SUBFLOW = 'octavia-get-network-type-handler-subflow'
FLAT_NET_HANDLER_SUBFLOW = 'octavia-get-flat-net-handler-sublow'
VLAN_NET_HANDLER_SUBFLOW = 'octavia-get-vlan-net-handler-subflow'
VLAN_DELETE_NET_HANDLER_SUBFLOW = 'octavia-delete-vlan-net-handler-subflow'
FLAT_DELETE_NET_HANDLER_SUBFLOW = 'octavia-delete-flat-net-handler-subflow'
CREATE_MEMBER_NET_FLOW = 'octavia-create-member-net-flow'
DELETE_MEMBER_NET_FLOW = 'octavia-delete-member-net-flow'

# Flow constants
BACKUP_VTHUNDER = 'backup_vthunder'
VTHUNDER = 'vthunder'
PARENT_PORT = 'parent_port'
TRUNK = 'trunk'
ADDED_NICS = 'added_nics'
PORT_DELTAS = 'port_deltas'
NIC_DELTAS  = 'nic_deltas'
PORT_DELTA = 'port_delta'
NIC_DELTA = 'nic_delta'
VE_INTERFACES = 've_interfaces'
DELETED_PORTS = 'deleted_ports'

# Constant values
STATUS = 'status'
ROLE = 'role'
VRRP_STATUS = 'vrrp_status'

FAILED = 'FAILED'
VTHUNDER_UDP_HEARTBEAT = 'vthunder_udp_heartbeat'
HM_SERVER = 'a10_hm_server'
VTHUNDER_ID = "vthunder_id"
VTHUNDER_CONFIG='vthunder_config'
