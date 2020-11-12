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

import datetime
from oslo_db.sqlalchemy import models
import sqlalchemy as sa
from sqlalchemy.ext import orderinglist
from sqlalchemy import orm
from sqlalchemy.orm import validates
from sqlalchemy.sql import func

from a10_octavia.common import data_models
from a10_octavia.db import base_models
from octavia.i18n import _


class TimeStampData:
    created_at = sa.Column(sa.DateTime, default=datetime.datetime.utcnow)
    updated_at = sa.Column(sa.DateTime, onupdate=datetime.datetime.utcnow)


class VThunder(base_models.BASE, TimeStampData):
    __data_model__ = data_models.VThunder
    __tablename__ = 'vthunders'

    id = sa.Column(sa.Integer, primary_key=True)
    vthunder_id = sa.Column(sa.String(36), nullable=False)
    project_id = sa.Column(sa.String(36))
    amphora_id = sa.Column(sa.String(36), nullable=True)
    device_name = sa.Column(sa.String(1024), nullable=False)
    ip_address = sa.Column('ip_address', sa.String(64), nullable=False)
    username = sa.Column(sa.String(1024), nullable=False)
    password = sa.Column(sa.String(50), nullable=False)
    axapi_version = sa.Column(sa.Integer, default=30, nullable=False)
    undercloud = sa.Column(sa.Boolean(), default=False, nullable=False)
    loadbalancer_id = sa.Column(sa.String(36))
    compute_id = sa.Column(sa.String(36))
    topology = sa.Column(sa.String(50))
    role = sa.Column(sa.String(50))
    last_udp_update = sa.Column(u'last_udp_update', sa.DateTime(), nullable=True)
    status = sa.Column('status', sa.String(36), default='ACTIVE', nullable=False)
    partition_name = sa.Column(sa.String(14), nullable=True)
    hierarchical_multitenancy = sa.Column(sa.String(7), default=None, nullable=True)

    @classmethod
    def find_by_loadbalancer_id(cls, loadbalancer_id, db_session=None):
        return cls.find_by_attribute('loadbalancer_id', loadbalancer_id, db_session)


class VRID(base_models.BASE, TimeStampData):
    __data_model__ = data_models.VRID
    __tablename__ = 'vrid'

    id = sa.Column(sa.Integer, primary_key=True)
    project_id = sa.Column(sa.String(36), nullable=False)
    vrid = sa.Column(sa.Integer, default=0, nullable=False)
    vrid_port_id = sa.Column(sa.String(36), nullable=False)
    vrid_floating_ip = sa.Column(sa.String(40), nullable=False)
    subnet_id = sa.Column(sa.String(36), nullable=False)


class Amphora_Meta(base_models.BASE, TimeStampData):
    __tablename__ = 'amphora_meta'

    id = sa.Column(sa.String(36), primary_key=True, nullable=False)
    last_udp_update = sa.Column(u'last_udp_update', sa.DateTime(), nullable=False)
    status = sa.Column('status', sa.String(36), default='ACTIVE', nullable=False)


class Thunder(base_models.BASE, TimeStampData):
    __tablename__ = 'thunder'

    id = sa.Column(sa.String(36), primary_key=True, nullable=False)
    vcs_device_id = sa.Column(sa.String(1), nullable=False)
    management_ip_address = sa.Column(sa.String(64), nullable=False)
    cluster_id = sa.Column(sa.String(36), sa.ForeignKey('thunder_cluster.id'))


class Role(base_models.BASE, TimeStampData):
    __tablename__ = 'role'

    id = sa.Column(sa.String(36), primary_key=True, nullable=False)
    state = sa.Column(sa.String(36), nullable=False)
    thunder_id = sa.Column(sa.String(36), sa.ForeignKey('thunder.id'))


class Thunder_Cluster(base_models.BASE, TimeStampData):
    __tablename__ = 'thunder_cluster'

    id = sa.Column(sa.String(36), primary_key=True, nullable=False)
    username = sa.Column(sa.String(1024), nullable=False)
    password = sa.Column(sa.String(50), nullable=False)
    cluster_name = sa.Column(sa.String(1024), nullable=False)
    cluster_ip_address = sa.Column(sa.String(64), nullable=False)
    topology = sa.Column(sa.String(50))
    undercloud = sa.Column(sa.Boolean(), default=False, nullable=False)


class Partitions(base_models.BASE, TimeStampData):
    __tablename__ = 'partitions'

    id = sa.Column(sa.String(36), primary_key=True, nullable=False)
    name = sa.Column(sa.String(14), nullable=True)
    hierarchical_multitenancy = sa.Column(sa.String(7), nullable=False)


class Project(base_models.BASE, TimeStampData):
    __tablename__ = 'project'

    id = sa.Column(sa.String(36), primary_key=True, nullable=False)
    partition_id = sa.Column(sa.String(36), sa.ForeignKey('partitions.id'))
    thunder_cluster_id = sa.Column(sa.String(36), sa.ForeignKey('thunder_cluster.id'))


class Ethernet_Interface(base_models.BASE, TimeStampData):
    __tablename__ = 'ethernet_interface'

    interface_num = sa.Column(sa.Integer, primary_key=True, nullable=False)
    vlan_id = sa.Column(sa.String(36), nullable=False)
    subnet_id = sa.Column(sa.String(36), nullable=False)
    ve_ip_address = sa.Column(sa.String(64), nullable=False)
    port_id = sa.Column(sa.String(36), nullable=False)


class Trunk_Interface(base_models.BASE, TimeStampData):
    __tablename__ = 'trunk_interface'

    interface_num = sa.Column(sa.Integer, primary_key=True, nullable=False)
    vlan_id = sa.Column(sa.String(36), nullable=False)
    subnet_id = sa.Column(sa.String(36), nullable=False)
    ve_ip_address = sa.Column(sa.String(64), nullable=False)
    port_id = sa.Column(sa.String(36), nullable=False)


class Device_Network_Cluster(base_models.BASE, TimeStampData):
    __tablename__ = 'device_network_cluster'

    id = sa.Column(sa.String(36), primary_key=True, nullable=False)
    thunder_id = sa.Column(sa.String(36), sa.ForeignKey('thunder.id'))
    ethernet_interface_num = sa.Column(
        sa.Integer, sa.ForeignKey('ethernet_interface.interface_num'))
    trunk_interface_num = sa.Column(sa.Integer, sa.ForeignKey('trunk_interface.interface_num'))
