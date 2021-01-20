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


from datetime import datetime
import re
import six
from sqlalchemy.orm import collections


class BaseDataModel(object):
    def to_dict(self, calling_classes=None, recurse=False, **kwargs):
        """Converts a data model to a dictionary."""
        calling_classes = calling_classes or []
        ret = {}
        for attr in self.__dict__:
            if attr.startswith('_') or not kwargs.get(attr, True):
                continue
            value = self.__dict__[attr]

            if recurse:
                if isinstance(getattr(self, attr), list):
                    ret[attr] = []
                    for item in value:
                        if isinstance(item, BaseDataModel):
                            if type(self) not in calling_classes:
                                ret[attr].append(
                                    item.to_dict(calling_classes=(
                                        calling_classes + [type(self)])))
                            else:
                                ret[attr] = None
                        else:
                            ret[attr] = item
                elif isinstance(getattr(self, attr), BaseDataModel):
                    if type(self) not in calling_classes:
                        ret[attr] = value.to_dict(
                            calling_classes=calling_classes + [type(self)])
                    else:
                        ret[attr] = None
                elif six.PY2 and isinstance(value, six.text_type):
                    ret[attr.encode('utf8')] = value.encode('utf8')
                else:
                    ret[attr] = value
            else:
                if isinstance(getattr(self, attr), (BaseDataModel, list)):
                    ret[attr] = None
                else:
                    ret[attr] = value

        return ret

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.to_dict() == other.to_dict()
        return False

    def __ne__(self, other):
        return not self.__eq__(other)

    @classmethod
    def from_dict(cls, dict):
        return cls(**dict)

    @classmethod
    def _name(cls):
        """Returns class name in a more human readable form."""
        # Split the class name up by capitalized words
        return ' '.join(re.findall('[A-Z][^A-Z]*', cls.__name__))

    def _get_unique_key(self, obj=None):
        """Returns a unique key for passed object for data model building."""
        obj = obj or self
        # First handle all objects with their own ID, then handle subordinate
        # objects.
        if obj.__class__.__name__ in ['VThunder']:
            return obj.__class__.__name__ + obj.id
        else:
            raise NotImplementedError

    def _find_in_graph(self, key, _visited_nodes=None):
        """Locates an object with the given unique key in the current

        object graph and returns a reference to it.
        """
        _visited_nodes = _visited_nodes or []
        mykey = self._get_unique_key()
        if mykey in _visited_nodes:
            # Seen this node already, don't traverse further
            return None
        elif mykey == key:
            return self
        else:
            _visited_nodes.append(mykey)
            attr_names = [attr_name for attr_name in dir(self)
                          if not attr_name.startswith('_')]
            for attr_name in attr_names:
                attr = getattr(self, attr_name)
                if isinstance(attr, BaseDataModel):
                    result = attr._find_in_graph(
                        key, _visited_nodes=_visited_nodes)
                    if result is not None:
                        return result
                elif isinstance(attr, (collections.InstrumentedList, list)):
                    for item in attr:
                        if isinstance(item, BaseDataModel):
                            result = item._find_in_graph(
                                key, _visited_nodes=_visited_nodes)
                            if result is not None:
                                return result
        # If we are here we didn't find it.
        return None

    def update(self, update_dict):
        """Generic update method which works for simple,

        non-relational attributes.
        """
        for key, value in update_dict.items():
            setattr(self, key, value)


class Thunder(BaseDataModel):

    def __init__(self, id=None, vthunder_id=None, amphora_id=None,
                 device_name=None, ip_address=None, username=None,
                 password=None, axapi_version=None, undercloud=None,
                 loadbalancer_id=None, project_id=None, compute_id=None,
                 topology="STANDALONE", role="MASTER", last_udp_update=None, status="ACTIVE",
                 created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
                 partition_name="shared", hierarchical_multitenancy="disable",
                 last_write_mem=None, vrid_floating_ip=None, device_network_map=None):
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
        self.last_write_mem = last_write_mem
        self.vrid_floating_ip = vrid_floating_ip
        self.device_network_map = device_network_map or []


class HardwareThunder(Thunder):
    def __init__(self, **kwargs):
        Thunder.__init__(self, **kwargs)


class VThunder(Thunder):
    def __init__(self, **kwargs):
        Thunder.__init__(self, **kwargs)


class Certificate(BaseDataModel):

    def __init__(self, cert_filename=None, cert_content=None, key_filename=None,
                 key_content=None, key_pass=None, template_name=None):
        self.cert_filename = cert_filename
        self.cert_content = cert_content
        self.key_filename = key_filename
        self.key_content = key_content
        self.key_pass = key_pass
        self.template_name = template_name


class VRID(BaseDataModel):

    def __init__(self, id=None, project_id=None, vrid=None, vrid_port_id=None,
                 vrid_floating_ip=None, subnet_id=None):
        self.id = id
        self.project_id = project_id
        self.vrid = vrid
        self.vrid_port_id = vrid_port_id
        self.vrid_floating_ip = vrid_floating_ip
        self.subnet_id = subnet_id


class Interface(BaseDataModel):

    def __init__(self, interface_num=None, tags=None, ve_ips=None):
        self.interface_num = interface_num
        self.tags = tags or []
        self.ve_ips = ve_ips or []


class DeviceNetworkMap(BaseDataModel):

    def __init__(self, vcs_device_id=None, mgmt_ip_address=None, ethernet_interfaces=None,
                 trunk_interfaces=None):
        self.vcs_device_id = vcs_device_id
        self.mgmt_ip_address = mgmt_ip_address
        self.ethernet_interfaces = ethernet_interfaces or []
        self.trunk_interfaces = trunk_interfaces or []
        self.state = 'Unknown'


class NATPool(BaseDataModel):
    def __init__(self, id=None, name=None, subnet_id=None, start_address=None,
                 end_address=None, member_ref_count=None, port_id=None):
        self.id = id
        self.name = name
        self.subnet_id = subnet_id
        self.start_address = start_address
        self.end_address = end_address
        self.member_ref_count = member_ref_count
        self.port_id = port_id
