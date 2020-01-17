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


from oslo_config import cfg
from oslo_log import log

from octavia.common import config
from octavia.common import rpc
from a10_octavia.common import a10_config

def prepare_service(argv=None):
    """Sets global config from config file and sets up logging."""
    argv = argv or []
    a10_config.init(argv[1:])
    log.set_defaults()
    a10_config.setup_logging(cfg.CONF)
    rpc.init()

