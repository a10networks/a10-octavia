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
import sqlalchemy as sa
from sqlalchemy.ext import orderinglist
from sqlalchemy import orm
from sqlalchemy.orm import validates
from sqlalchemy.sql import func

from a10_octavia.common import data_models
from a10_octavia.db import base_models
from octavia.i18n import _


class VThunder(base_models.BASE):
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
    last_udp_update = sa.Column(u'last_udp_update', sa.DateTime(), nullable=False)
    status = sa.Column('status', sa.String(36), default='ACTIVE', nullable=False)
    created_at = sa.Column(u'created_at', sa.DateTime(), nullable=True)
    updated_at = sa.Column(u'updated_at', sa.DateTime(), nullable=True)
    partition_name = sa.Column(sa.String(14), nullable=True)
    hierarchical_multitenancy = sa.Column(sa.String(7), nullable=False)
    last_write_mem = sa.Column(u'last_write_mem', sa.DateTime(), nullable=True)

    @classmethod
    def find_by_loadbalancer_id(cls, loadbalancer_id, db_session=None):
        return cls.find_by_attribute('loadbalancer_id', loadbalancer_id, db_session)


class VRID(base_models.BASE):
    __data_model__ = data_models.VRID
    __tablename__ = 'vrid'

    id = sa.Column(sa.Integer, primary_key=True)
    project_id = sa.Column(sa.String(36), nullable=False)
    vrid = sa.Column(sa.Integer, default=0)
    vrid_port_id = sa.Column(sa.String(36), nullable=False)
    vrid_floating_ip = sa.Column(sa.String(40))
    subnet_id = sa.Column(sa.String(36), nullable=False)


class NATPool(base_models.BASE):
    __data_model__ = data_models.NATPool
    __tablename__ = 'nat_pool'
    __table_args__ = (
        sa.UniqueConstraint('name', 'subnet_id', name='unique_name_subnet_id'),
    )
    id = sa.Column(sa.String(64), primary_key=True)
    name = sa.Column(sa.String(64), nullable=False)
    subnet_id = sa.Column(sa.String(64), nullable=False)
    start_address = sa.Column('start_address', sa.String(64), nullable=False)
    end_address = sa.Column('end_address', sa.String(64), nullable=False)
    member_ref_count = sa.Column(sa.Integer, default=0, nullable=False)
    port_id = sa.Column(sa.String(64), nullable=False)

