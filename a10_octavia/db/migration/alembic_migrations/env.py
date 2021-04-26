from __future__ import with_statement

from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context
from a10_octavia import a10_config
from a10_octavia.db import base_models

# ===========================================================
#                    DO NOT DELETE THIS CODE!!!
#
# The below code is required for autogeneration to work
# ===========================================================
from a10_octavia.db.models import VThunder, NATPool, VRID, VrrpSet
VALID_AUOTGEN_TABLE_NAMES = ('vthunders', 'nat_pool', 'vrid', 'vrrp_set')
# ===========================================================

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
VERSION_TABLE = 'alembic_version_a10'

config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = [base_models.BASE.metadata]

if getattr(config, 'connection', None) is None:
    a10_cfg = a10_config.A10Config()
    config.set_main_option("sqlalchemy.url", a10_cfg.get('database_connection'))


# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.

def include_object(object, name, type_, reflected, compare_to):
    if type_ == "table" and name not in VALID_AUOTGEN_TABLE_NAMES:
        return False
    return True

def run_migrations_offline():
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        include_object=include_object
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            version_table=VERSION_TABLE,
            target_metadata=target_metadata,
            include_object=include_object
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
