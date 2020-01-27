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


from contextlib import contextmanager
import datetime
import uuid

import sqlalchemy as sa
from sqlalchemy.inspection import inspect

from a10_octavia.db import api as db_api

Base = db_api.get_base()


def _uuid_str():
    return str(uuid.uuid4())


def _get_date():
    return datetime.datetime.now()


class A10Base(Base):
    __abstract__ = True

    @classmethod
    @contextmanager
    def _query(cls, db_session=None):
        with db_api.magic_session(db_session) as db:
            yield db.query(cls)

    @classmethod
    def get(cls, key, db_session=None):
        with cls._query(db_session) as q:
            return q.get(key)

    @classmethod
    def find_all_by(cls, db_session=None, **kwargs):
        with cls._query(db_session) as q:
            return q.filter_by(**kwargs).all()

    @classmethod
    def find_by(cls, db_session=None, **kwargs):
        with cls._query(db_session) as q:
            return q.filter_by(**kwargs).first()

    @classmethod
    def find_by_attribute(cls, attribute_name, attribute, db_session=None):
        with cls._query(db_session) as q:
            return q.filter(
                getattr(cls, attribute_name) == attribute).first()

    @classmethod
    def find_all(cls, db_session=None):
        with cls._query(db_session) as q:
            return q.all()

    @classmethod
    def create(cls, **kwargs):
        instance = cls(**kwargs)
        # Populate all the unspecified columns with their defaults
        for key, column in inspect(cls).columns.items():
            if key not in kwargs and column.default is not None:
                arg = column.default.arg
                column_default = arg if callable(arg) else lambda: arg
                setattr(instance, key, column_default(instance))
        return instance

    @classmethod
    def create_and_save(cls, db_session=None, **kwargs):
        m = cls.create(**kwargs)
        with db_api.magic_session(db_session) as db:
            db.add(m)
            db.commit()
            return m

    def as_dict(self):
        d = dict(self.__dict__)
        d.pop('_sa_instance_state', None)
        return d

    def update(self, **kwargs):
        for key in kwargs:
            setattr(self, key, kwargs[key])

    def delete(self, db_session=None):
        db = db_session or inspect(self).session
        db.delete(self)


class A10BaseMixin(object):

    id = sa.Column(sa.String(36), primary_key=True, nullable=False, default=_uuid_str)
