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
    password = sa.Column(sa.String(50), nullable= False)
    axapi_version = sa.Column(sa.Integer, default=30, nullable=False)
    undercloud = sa.Column(sa.Boolean(), default=False, nullable=False)
    loadbalancer_id = sa.Column(sa.String(36))
    compute_id = sa.Column(sa.String(36))


    @classmethod
    def find_by_loadbalancer_id(cls, loadbalancer_id, db_session=None):
        return cls.find_by_attribute('loadbalancer_id', loadbalancer_id, db_session)

