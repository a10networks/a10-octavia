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


from octavia.common import data_models


class A10OctaviaDataModel(data_models.BaseDataModel):

    def _get_unique_key(self, obj=None):
        """Returns a unique key for passed object for data model building."""
        obj = obj or self
        # First handle all objects with their own ID, then handle subordinate
        # objects.
        if obj.__class__.__name__ in ['ThunderV1', 'AmphoraMeta', 'Partitions', 'ThunderCluster',
                                      'Thunder', 'DeviceNetworkCluster', 'VRID']:
            return obj.__class__.__name__ + obj.id
        if obj.__class__.__name__ in ['Interface', 'TrunkInterface', 'EthernetInterface']:
            return obj.__class__.__name__ + obj.interface_num
        else:
            raise NotImplementedError


class ThunderV1(A10OctaviaDataModel):

    def __init__(self, id=None, vthunder_id=None, amphora_id=None,
                 device_name=None, ip_address=None, username=None,
                 password=None, axapi_version=None, undercloud=None,
                 loadbalancer_id=None, project_id=None, compute_id=None,
                 topology=None, role=None, last_udp_update=None, status=None,
                 created_at=None, updated_at=None,
                 partition_name=None, hierarchical_multitenancy=None,
                 vrid_floating_ip=None, device_network_map=None):
        self.id = id
        self.vthunder_id = vthunder_id
        self.amphora_id = amphora_id
        self.device_name = device_name
        self.ip_address = ip_address
        self.username = username
        self.password = password
        self.axapi_version = axapi_version
        self.undercloud = undercloud
        self.loadbalancer_id = loadbalancer_id
        self.project_id = project_id
        self.compute_id = compute_id
        self.topology = topology
        self.role = role
        self.last_udp_update = last_udp_update
        self.status = status
        self.created_at = created_at
        self.updated_at = updated_at
        self.partition_name = partition_name
        self.hierarchical_multitenancy = hierarchical_multitenancy
        self.vrid_floating_ip = vrid_floating_ip
        self.device_network_map = device_network_map or []


class HardwareThunder(ThunderV1):
    def __init__(self, **kwargs):
        ThunderV1.__init__(self, **kwargs)


class VThunder(ThunderV1):
    def __init__(self, **kwargs):
        ThunderV1.__init__(self, **kwargs)


class Certificate(A10OctaviaDataModel):

    def __init__(self, cert_filename=None, cert_content=None, key_filename=None,
                 key_content=None, key_pass=None, template_name=None):
        self.cert_filename = cert_filename
        self.cert_content = cert_content
        self.key_filename = key_filename
        self.key_content = key_content
        self.key_pass = key_pass
        self.template_name = template_name


class VRID(A10OctaviaDataModel):

    def __init__(self, id=None, project_id=None, vrid=None, vrid_port_id=None,
                 vrid_floating_ip=None, subnet_id=None):
        self.id = id
        self.project_id = project_id
        self.vrid = vrid
        self.vrid_port_id = vrid_port_id
        self.vrid_floating_ip = vrid_floating_ip
        self.subnet_id = subnet_id


class InterfaceV1(A10OctaviaDataModel):

    def __init__(self, interface_num=None, tags=None, ve_ips=None):
        self.interface_num = interface_num
        self.tags = tags or []
        self.ve_ips = ve_ips or []


class DeviceNetworkMap(A10OctaviaDataModel):

    def __init__(self, vcs_device_id=None, mgmt_ip_address=None, ethernet_interfaces=None,
                 trunk_interfaces=None):
        self.vcs_device_id = vcs_device_id
        self.mgmt_ip_address = mgmt_ip_address
        self.ethernet_interfaces = ethernet_interfaces or []
        self.trunk_interfaces = trunk_interfaces or []
        self.state = 'Unknown'


class DeviceNetworkCluster(A10OctaviaDataModel):

    def __init__(self, id=None, thunder_id=None, ethernet_interface_num=None,
                 trunk_interface_num=None, created_at=None, updated_at=None):
        self.id = id
        self.thunder_id = thunder_id
        self.ethernet_interface_num = ethernet_interface_num
        self.trunk_interface_num = trunk_interface_num
        self.created_at = created_at
        self.updated_at = updated_at


class Interface(A10OctaviaDataModel):

    def __init__(self, interface_num=None, subnet_id=None, vlan_id=None,
                 ve_ip_address=None, port_id=None, created_at=None, updated_at=None):
        self.interface_num = interface_num
        self.subnet_id = subnet_id
        self.vlan_id = vlan_id
        self.ve_ip_address = ve_ip_address
        self.port_id = port_id
        self.created_at = created_at
        self.updated_at = updated_at


class EthernetInterface(Interface):

    def __init__(self, **kwargs):
        Interface.__init__(self, **kwargs)


class TrunkInterface(Interface):

    def __init__(self, **kwargs):
        Interface.__init__(self, **kwargs)


class ThunderCluster(A10OctaviaDataModel):

    def __init__(self, id=None, created_at=None, updated_at=None, username=None, password=None,
                 cluster_name=None, cluster_ip_address=None, undercloud=None, topology=None):
        self.id = id
        self.created_at = created_at
        self.updated_at = updated_at
        self.username = username
        self.password = password
        self.cluster_name = cluster_name
        self.cluster_ip_address = cluster_ip_address
        self.undercloud = undercloud
        self.topology = topology


class AmphoraMeta(A10OctaviaDataModel):

    def __init__(self, id=None, created_at=None, updated_at=None,
                 last_udp_update=None, status=None):
        self.id = id
        self.created_at = created_at
        self.updated_at = updated_at
        self.last_udp_update = last_udp_update
        self.status = status


class Partitions(A10OctaviaDataModel):
    def __init__(self, id=None, name=None, hierarchical_multitenancy=None,
                 created_at=None, updated_at=None):
        self.id = id
        self.name = name
        self.hierarchical_multitenancy = hierarchical_multitenancy
        self.created_at = created_at
        self.updated_at = updated_at


class Thunder(A10OctaviaDataModel):
    def __init__(self, id=None, vcs_device_id=None, created_at=None, updated_at=None,
                 management_ip_address=None, cluster_id=None):
        self.id = id
        self.vcs_device_id = vcs_device_id
        self.management_ip_address = management_ip_address
        self.cluster_id = cluster_id
        self.created_at = created_at
        self.updated_at = updated_at
