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

from octavia.common import data_models as base_data_models
from octavia.network import data_models as network_data_models


class ParentPort(network_data_models.Port):

    def __init__(self, id=None, name=None, device_id=None, device_owner=None,
                 mac_address=None, network_id=None, status=None, project_id=None,
                 admin_state_up=None, fixed_ips=None, qos_policy_id=None,
                 trunk_id=None, subports=None):
        self.id = id
        self.name = name
        self.device_id = device_id
        self.device_owner = device_owner
        self.mac_address = mac_address
        self.network_id = network_id
        self.status = status
        self.project_id = project_id
        self.admin_state_up = admin_state_up
        self.fixed_ips = fixed_ips or []
        self.qos_policy_id = qos_policy_id
        self.trunk_id = trunk_id
        self.subports = subports or []


class Subport(base_data_models.BaseDataModel):
    """Sometimes reffered to as subport"""

    def __init__(self, segmentation_id=None, port_id=None,
                 segmentation_type=None, mac_address=None,
                 network_id=None):
        self.segmentation_id = segmentation_id
        self.port_id = port_id
        self.segmentation_type = segmentation_type
        self.mac_address = mac_address
        self.network_id = network_id


class PortDelta(base_data_models.BaseDataModel):

    def __init__(self, amphora_id=None, compute_id=None,
                 add_subports=None, delete_subports=None):
        self.compute_id = compute_id
        self.amphora_id = amphora_id
        self.add_subports = add_subports
        self.delete_subports = delete_subports
