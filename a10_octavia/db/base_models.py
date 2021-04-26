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


from oslo_db.sqlalchemy import models
from oslo_utils import strutils
from oslo_utils import uuidutils
import sqlalchemy as sa
from sqlalchemy.ext import declarative
from sqlalchemy.orm import collections


class A10Base(models.ModelBase):

    __data_model__ = None

    @staticmethod
    def _get_unique_key(obj):
        """Returns a unique key for passed object for data model building."""
        # First handle all objects with their own ID, then handle subordinate
        # objects.
        if obj.__class__.__name__ in ['Member', 'Pool', 'LoadBalancer',
                                      'Listener', 'Amphora', 'L7Policy',
                                      'L7Rule', 'VThunder', 'VRID',
                                      'NATPool']:
            return obj.__class__.__name__ + str(obj.id)
        elif obj.__class__.__name__ in ['SessionPersistence', 'HealthMonitor']:
            return obj.__class__.__name__ + obj.pool_id
        elif obj.__class__.__name__ in ['ListenerStatistics']:
            return obj.__class__.__name__ + obj.listener_id + obj.amphora_id
        elif obj.__class__.__name__ in ['VRRPGroup', 'Vip']:
            return obj.__class__.__name__ + obj.load_balancer_id
        elif obj.__class__.__name__ in ['AmphoraHealth']:
            return obj.__class__.__name__ + obj.amphora_id
        elif obj.__class__.__name__ in ['SNI']:
            return (obj.__class__.__name__ +
                    obj.listener_id + obj.tls_container_id)
        elif obj.__class__.__name__ in ['Quotas']:
            return obj.__class__.__name__ + obj.project_id
        elif obj.__class__.__name__ in ['VrrpSet']:
            return obj.__class__.__name__ + obj.mgmt_subnet + obj.project_id
        else:
            raise NotImplementedError

    def to_data_model(self, _graph_nodes=None):
        """Converts to a data model graph.

        In order to make the resulting data model graph usable no matter how
        many internal references are followed, we generate a complete graph of
        A10Base nodes connected to the object passed to this method.

        :param _graph_nodes: Used only for internal recursion of this
                             method. Should not be called from the outside.
                             Contains a dictionary of all A10Base type
                             objects in the generated graph
        """
        _graph_nodes = _graph_nodes or {}
        if not self.__data_model__:
            raise NotImplementedError
        dm_kwargs = {}
        for column in self.__table__.columns:
            dm_kwargs[column.name] = getattr(self, column.name)

        attr_names = [attr_name for attr_name in dir(self)
                      if not attr_name.startswith('_')]
        # Appending early, as any unique ID should be defined already and
        # the rest of this object will get filled out more fully later on,
        # and we need to add ourselves to the _graph_nodes before we
        # attempt recursion.
        dm_self = self.__data_model__(**dm_kwargs)
        dm_key = self._get_unique_key(dm_self)
        _graph_nodes.update({dm_key: dm_self})
        for attr_name in attr_names:
            attr = getattr(self, attr_name)
            if isinstance(attr, A10Base) and attr.__class__:
                # If this attr is already in the graph node list, just
                # reference it there and don't recurse.
                ukey = self._get_unique_key(attr)
                if ukey in _graph_nodes.keys():
                    setattr(dm_self, attr_name, _graph_nodes[ukey])
                else:
                    setattr(dm_self, attr_name, attr.to_data_model(
                        _graph_nodes=_graph_nodes))
            elif isinstance(attr, (collections.InstrumentedList, list)):
                setattr(dm_self, attr_name, [])
                listref = getattr(dm_self, attr_name)
                for item in attr:
                    if isinstance(item, A10Base) and item.__class__:
                        ukey = self._get_unique_key(item)
                        if ukey in _graph_nodes.keys():
                            listref.append(_graph_nodes[ukey])
                        else:
                            listref.append(
                                item.to_data_model(_graph_nodes=_graph_nodes))
                    elif not isinstance(item, A10Base):
                        listref.append(item)
        return dm_self

    @staticmethod
    def apply_filter(query, model, filters):
        translated_filters = {}
        child_map = {}
        # Convert enabled to proper type
        if 'enabled' in filters:
            filters['enabled'] = strutils.bool_from_string(
                filters['enabled'])
        for attr, name_map in model.__v2_wsme__._child_map.items():
            for k, v in name_map.items():
                if attr in filters and k in filters[attr]:
                    child_map.setdefault(attr, {}).update(
                        {k: filters[attr].pop(k)})
            filters.pop(attr, None)

        for k, v in model.__v2_wsme__._type_to_model_map.items():
            if k in filters:
                translated_filters[v] = filters.pop(k)
        translated_filters.update(filters)
        if translated_filters:
            query = query.filter_by(**translated_filters)
        for k, v in child_map.items():
            query = query.join(getattr(model, k)).filter_by(**v)
        return query


BASE = declarative.declarative_base(cls=A10Base)
