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
import runpy
import socket
import ast
from oslo_log import log as logging

# This is ConfigParser pre-Python3
if sys.version_info < (3,):
    import ConfigParser as ini
else:
    import configparser as ini

from debtcollector import removals
from a10_octavia.etc import config as blank_config
from a10_octavia.etc import defaults
from a10_octavia.common.defaults import DEFAULT
from a10_octavia.common import data_models
from octavia.db import repositories as repo

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
    def load(cls, path, provider=None):
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
            n = ini.ConfigParser(defaults=DEFAULT)
            n.read(self._config_path)
            self._conf = n
        except IOError:
            LOG.error("A10Config could not find %s", self._config_path)
            self._conf = ini.ConfigParser(defaults=DEFAULT)
            self._config = blank_config

        self._config.octavia_conf_dir = '/etc/octavia/'
        self._load_config()

    def get_rack_dict(self):
        rack_dict = {}
        if self._conf.has_section("RACK_VTHUNDER") and self._conf.has_option("RACK_VTHUNDER", "devices"):
            project_conf = self._conf.get('RACK_VTHUNDER', 'devices')
            rack_conf = ast.literal_eval(project_conf.strip('"'))
            validation_flag = False
            try:
                for i in range(len(rack_conf["device_list"])):
                    project_id = rack_conf["device_list"][i]["project_id"]
                    ip_address = rack_conf["device_list"][i]["ip_address"]
                    undercloud = bool(rack_conf["device_list"][i]["undercloud"])
                    username = rack_conf["device_list"][i]["username"]
                    password = rack_conf["device_list"][i]["password"]
                    device_name = rack_conf["device_list"][i]["device_name"]
                    axapi_version = rack_conf["device_list"][i]["axapi_version"]
                    role = rack_conf["device_list"][i]["role"]
                    topology = rack_conf["device_list"][i]["topology"]
                    validation_flag = self.validate(project_id, ip_address, username,
                                                    password, axapi_version,
                                                    undercloud, device_name,
                                                    role, topology)

                    if validation_flag:
                        vthunder_conf = data_models.VThunder(project_id=project_id,
                                                             ip_address=ip_address,
                                                             undercloud=undercloud,
                                                             username=username, role=role,
                                                             topology=topology,
                                                             password=password,
                                                             device_name=device_name,
                                                             axapi_version=axapi_version)
                        rack_dict[project_id] = vthunder_conf
                    else:
                        LOG.warning('Invalid definition of rack device for'
                                    'project ' + project_id)

            except KeyError as e:
                LOG.error("Invalid definition of rack device in A10 config file."
                          "The Loadbalancer you create shall boot as overcloud."
                          "Check attribute: " + str(e))
        return rack_dict

    def get_rack_dict(self):
        rack_dict = {}
        if self._conf.has_section("RACK_VTHUNDER") and self._conf.has_option("RACK_VTHUNDER", "devices"):
            project_conf = self._conf.get('RACK_VTHUNDER', 'devices')
            rack_list = ast.literal_eval(project_conf.strip('"'))
            validation_flag = False
            try:
                for rack_device in rack_list:
                    validation_flag = self.validate(rack_device["project_id"],
                                                    rack_device["ip_address"],
                                                    rack_device["username"],
                                                    rack_device["password"],
                                                    rack_device["axapi_version"],
                                                    rack_device["device_name"])
                    if validation_flag:
                        rack_device["undercloud"] = True
                        vthunder_conf = data_models.VThunder(**rack_device)
                        rack_dict[rack_device["project_id"]] = vthunder_conf
                    else:
                        LOG.warning('Invalid definition of rack device for'
                                    'project ' + project_id)

            except KeyError as e:
                LOG.error("Invalid definition of rack device in A10 config file."
                          "The Loadbalancer you create shall boot as overcloud."
                          "Check attribute: " + str(e))
        return rack_dict

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
            d = config_dir
        elif env_override is not None:
            d = env_override
        elif has_prefix and os.path.exists(venv_d):
            d = venv_d
        else:
            d = '/etc/a10'

        return d

    def _load_config(self):
        # Global defaults
        for dk, dv in defaults.GLOBAL_DEFAULTS.items():
            if not hasattr(self._config, dk):
                LOG.debug("setting global default %s=%s", dk, dv)
                setattr(self._config, dk, dv)
            else:
                LOG.debug("global setting %s=%s", dk, getattr(self._config, dk))

        # Setup db foo
        if self._config.database_connection is None:
            self._config.database_connection = self._get_octavia_db_string()

        if self._config.keystone_auth_url is None:
            self._config.keystone_auth_url = self.get_octavia_conf(
                'keystone_authtoken', 'auth_uri')

    def get_octavia_conf(self, section, option):
        octavia_conf_dir = os.environ.get('OCTAVIA_CONF_DIR', self._config.octavia_conf_dir)
        octavia_conf = '%s/octavia.conf' % octavia_conf_dir

        if os.path.exists(octavia_conf):
            LOG.debug("found octavia.conf file in /etc")
            n = ini.ConfigParser()
            n.read(octavia_conf)
            try:
                return n.get(section, option)
            except (ini.NoSectionError, ini.NoOptionError):
                pass
        else:
            raise Exception('FatalError: Octavia config directoty could not be found.')
            LOG.error("A10Config could not find %s", self._config_path)

    def _get_octavia_db_string(self):
        z = self.get_octavia_conf('database', 'connection')

        if z is None:
            raise a10_ex.NoDatabaseURL('must set db connection url or octavia dir in config.py')

        LOG.debug("using %s as db connect string", z)
        return z

    def get(self, key):
        return getattr(self._config, key)

    def validate(self, project_id, ip_address, username, password,
                 axapi_version, device_name):
        ip_validator = self.is_valid_ipv4_address(ip_address)
        if (project_id is not None and ip_address is not None and username is not None
           and password is not None and axapi_version is not None):
            if ip_validator:
                return True
            else:
                return False

    def is_valid_ipv4_address(self, address):
        try:
            socket.inet_pton(socket.AF_INET, address)
        except AttributeError:
            try:
                socket.inet_aton(address)
            except socket.error:
                return False
            return address.count('.') == 3
        except socket.error:
            return False

        return True
