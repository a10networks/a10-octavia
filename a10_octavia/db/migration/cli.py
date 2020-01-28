# Copyright (c) 2018 A10 Networks
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os

from alembic import command as alembic_cmd
from alembic import config as alembic_cfg
from alembic import util as alembic_u
from oslo_config import cfg
from oslo_db import options
from oslo_log import log

from octavia.i18n import _

from octavia.db.migration.cli import do_alembic_command, do_check_migration, do_upgrade, no_downgrade, do_stamp, do_revision, add_command_parsers


CONF = cfg.CONF
options.set_defaults(CONF)
log.set_defaults()
log.register_options(CONF)
log.setup(CONF, 'a10-octavia-db-manage')


def main():
    config = alembic_cfg.Config(
        os.path.join(os.path.dirname(__file__), 'alembic.ini')
    )
    config.set_main_option('script_location',
                           'a10_octavia.db.migration:alembic_migrations')
    # attach the octavia conf to the Alembic conf
    config.octavia_config = CONF

    CONF(project='a10-octavia')
    CONF.command.func(config, CONF.command.name)
