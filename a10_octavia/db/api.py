from contextlib import contextmanager

import sqlalchemy
import sqlalchemy.ext.declarative
import sqlalchemy.orm

#from a10_neutron_lbaas import a10_exceptions as ex

A10_CFG = None
Base = sqlalchemy.ext.declarative.declarative_base()



def get_base():
    return Base


def get_engine(url=None):
    global A10_CFG

    if url is None:
        if A10_CFG is None:
            from a10_neutron_lbaas import a10_config
            A10_CFG = a10_config.A10Config()

        if not A10_CFG.get('use_database'):
            raise ex.InternalError("attempted to use database when it is disabled")
        url = A10_CFG.get('database_connection')

    return sqlalchemy.create_engine(url)


def get_session(url=None, **kwargs):
    DBSession = sqlalchemy.orm.sessionmaker(bind=get_engine(url=url))
    return DBSession(**kwargs)


@contextmanager
def magic_session(db_session=None, url=None):
    """Either does nothing with the session you already have or
    makes one that commits and closes no matter what happens
    """

    if db_session is not None:
        yield db_session
    else:
        session = get_session(url, expire_on_commit=False)
        try:
            try:
                yield session
            finally:
                session.commit()
        finally:
            session.close()
