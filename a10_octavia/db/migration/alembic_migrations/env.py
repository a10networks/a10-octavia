from __future__ import with_statement

from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool
import sqlalchemy as sa

from alembic import context, command
from alembic.script import ScriptDirectory
from alembic.operations import Operations

from a10_octavia import a10_config
from a10_octavia.db import base_models

VERSION_TABLE = 'alembic_version_a10'
LOG_INFO = "INFO  [a10-octavia.db.migration] "
LOG_ERR = "ERROR  [a10-octavia.db.migration] "

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = None

if getattr(config, 'connection', None) is None:
    a10_cfg = a10_config.A10Config()
    config.set_main_option("sqlalchemy.url", a10_cfg.get('database_connection'))


# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def get_octavia_revision(ctx, op):
    current_rev = 0
    try:
        conn = op.get_bind()
        current_rev = conn.execute("select version_num from alembic_version").scalar()
    except:
        config.print_stdout("%sFailed to get octavia alembic revision", LOG_ERR)

    return current_rev

def a10_revision_migration(ctx):
    """ Check a10 database revision from 'alembic_version' table

    In a10-octavia v1.1 and earlier vrersions, a10-octavia use 
    'alembic_version' table as alembic version table (which will
    overwrite octavia alembic revisions). 

    To migrate from these versions, we need to copy the revision
    from'alembic_version' to 'alembic_version_a10'.

    """
    op = Operations(ctx)
    octavia_rev = get_octavia_revision(ctx, op)
    script = ScriptDirectory.from_config(config)
    dest_rev = 0
    try:
        rev = script.get_revision(octavia_rev)
        config.print_stdout("%soctavia revision %s is a10 revision", LOG_INFO, rev.revision)
        dest_rev = rev.revision
    except:
        config.print_stdout("%s%s is not a10 revision", LOG_INFO, octavia_rev)
        return

    try:
        ctx.stamp(script, dest_rev)
        config.print_stdout("%sstamp a10_revision to %s", LOG_INFO, dest_rev)

        # Since revision is copy to alembic_version_a10, remove a10 revision in octavia table.
        # Keep a10 vision in octavia may cause issue after a10-octavia do `alembic downgrade base`
        conn = op.get_bind()
        conn.execute("delete from alembic_version")
    except:
        config.print_stdout("%smigrate version from alembic_version failed", LOG_ERR)

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
        url=url, target_metadata=target_metadata, literal_binds=True
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
            target_metadata=target_metadata
        )

        # a10-octavia revision checks
        ctx = context.get_context()
        a10_revision = ctx.get_current_revision()
        if a10_revision is None:
            config.print_stdout("%sNo a10_revision yet.", LOG_INFO)
            a10_revision_migration(ctx=ctx)
        else:
            config.print_stdout("%scurrent a10_revision: %s", LOG_INFO, a10_revision)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
