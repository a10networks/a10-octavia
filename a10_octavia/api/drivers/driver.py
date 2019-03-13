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
from oslo_log import log as logging
import oslo_messaging as messaging

from octavia.api.drivers import exceptions
from octavia.api.drivers import provider_base as driver_base
from octavia.api.drivers import utils as driver_utils
from octavia.common import constants 
from octavia.common import data_models
from octavia.common import utils
from octavia.db import api as db_apis
from octavia.db import repositories
from octavia.network import base as network_base

CONF = cfg.CONF
CONF.import_group('oslo_messaging', 'octavia.common.config')
LOG = logging.getLogger(__name__)


class A10ProviderDriver(driver_base.ProviderDriver):
    def __init__(self):
        super(A10ProviderDriver, self).__init__()
        self._args = {}
        self.namespace = constants.RPC_NAMESPACE_CONTROLLER_AGENT
        self.topic = CONF.oslo_messaging.topic
        self.version = '1.0'
        self.transport = messaging.get_rpc_transport(cfg.CONF)
        self._args['fanout'] = False
        self._args['namespace'] = self.namespace
        self._args['topic'] = self.topic
        self._args['version'] = self.version
        self.target = messaging.Target(**self._args)
        self.client = messaging.RPCClient(self.transport, target=self.target)

    # Load Balancer
    # loadbalancer_create needs to be implemented
    def loadbalancer_create(self, loadbalancer):
        LOG.info('A10 provider load balancer loadbalancer: %s.', loadbalancer.__dict__)
        payload = {constants.LOAD_BALANCER_ID: loadbalancer.loadbalancer_id}
        self.client.cast({}, 'create_load_balancer', **payload)

    def loadbalancer_delete(self, loadbalancer, cascade=False):
        payload = {constants.LOAD_BALANCER_ID: loadbalancer.loadbalancer_id, 'cascade': cascade}
        self.client.cast({}, 'delete_load_balancer', **payload)

    # Moany other methods may be inheritted from Amphora 

