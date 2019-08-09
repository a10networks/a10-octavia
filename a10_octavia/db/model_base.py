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
