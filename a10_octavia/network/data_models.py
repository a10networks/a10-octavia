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

    def __init__(self, trunk_details=None, **kwargs) 
        if trunk_details:
            self.trunk_id = trunk_details["trunk_id"]
            self.sub_ports = [ChildPort(**subport) for subport in trunk_details["sub_ports"]]
        super(ParentPort, self).__init__(**kwargs)


class ChildPort(base_data_models.BaseDataModel):
    """Somtimes reffered to as subport"""

    def __init__(self, segmentation_id=None, port_id=None,
                 segmentation_type=None, mac_address=None):
        self.segmentation_id = segmentation_id
        self.port_id = port_id
        self.segmentation_vlan = segmentation_vlan
        self.mac_address = mac_address
