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

import os
import sys
from oslo_log import log as logging
from oslo_config import cfg
from a10_octavia.etc import config as blank_config
from a10_octavia.etc import defaults
from a10_octavia.common.defaults import DEFAULT

# This is ConfigParser pre-Python3
if sys.version_info < (3,):
    import ConfigParser as ini
else:
    import configparser as ini


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class ConfigModule(object):
    def __init__(self, d, provider=None):
        self.__dict__.update(d)

        if provider is None or 'providers' not in d or provider not in d['providers']:
            return None

        for k, v in d['providers'][provider].items():
            if isinstance(v, dict):
                if k not in self.__dict__:
                    self.__dict__[k] = {}
                self.__dict__[k].update(v)
            else:
                self.__dict__[k] = v

    @classmethod
    def load(cls, provider=None):
        d = dict()
        return ConfigModule(d, provider=provider)


class A10Config(object):

    def __init__(self, config_dir=None, config=None, provider=None):
        if config is not None:
            self._config = config
            self._load_config()
            return

        self._conf = None
        self._config_dir = self._find_config_dir(config_dir)
        self._config_path = os.path.join(self._config_dir, "config.py")

        try:
            self._config = ConfigModule.load(self._config_path, provider=provider)
            config_parser = ini.ConfigParser(defaults=DEFAULT)
            config_parser.read(self._config_path)
            self._conf = config_parser
        except IOError:
            LOG.error("A10Config could not find %s", self._config_path)
            self._conf = ini.ConfigParser(defaults=DEFAULT)
            self._config = blank_config

        self._config.octavia_conf_dir = '/etc/octavia/'
        self._load_config()

    def get_conf(self):
        return self._conf

    def _find_config_dir(self, config_dir):
        # Look for config in the virtual environment
        # virtualenv puts the original prefix in sys.real_prefix
        # pyenv puts it in sys.base_prefix
        venv_d = os.path.join(sys.prefix, 'etc/a10')
        has_prefix = (hasattr(sys, 'real_prefix') or hasattr(sys, 'base_prefix'))

        env_override = os.environ.get('A10_CONFIG_DIR', None)
        if config_dir is not None:
            directory = config_dir
        elif env_override is not None:
            directory = env_override
        elif has_prefix and os.path.exists(venv_d):
            directory = venv_d
        else:
            directory = '/etc/a10'

        return directory

    def _load_config(self):
        # Global defaults
        for key, value in defaults.GLOBAL_DEFAULTS.items():
            if not hasattr(self._config, key):
                LOG.debug("setting global default %s=%s", key, value)
                setattr(self._config, key, value)
            else:
                LOG.debug("global setting %s=%s", key, getattr(self._config, key))

        # Setup db foo
        if self._config.database_connection is None:
            self._config.database_connection = self._get_octavia_db_string()

        if self._config.keystone_auth_url is None:
            self._config.keystone_auth_url = CONF.keystone_authtoken.auth_uri

    def _get_octavia_db_string(self):
        db_connection_url = CONF.database.connection

        if db_connection_url is None:
            raise Exception('NoDatabaseURL : must set db connection url in configuration file')

        LOG.debug("using %s as db connect string", db_connection_url)
        return db_connection_url

    def get(self, key):
        return getattr(self._config, key)
