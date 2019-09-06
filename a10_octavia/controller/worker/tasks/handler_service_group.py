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


from taskflow import task

from octavia.controller.worker import task_utils as task_utilities
from octavia.common import constants
import acos_client
from octavia.amphorae.driver_exceptions import exceptions as driver_except
import time
from oslo_log import log as logging
from oslo_config import cfg
from a10_octavia.common import openstack_mappings
from a10_octavia.controller.worker.tasks.policy import PolicyUtil
from a10_octavia.controller.worker.tasks import persist
from a10_octavia.controller.worker.tasks.common import BaseVThunderTask

CONF = cfg.CONF
LOG = logging.getLogger(__name__)

class PoolCreate(BaseVThunderTask):
    """Task to update amphora with all specified listeners' configurations."""

    def execute(self, pool, vthunder):
        """Execute create pool for an amphora."""
        try:
            c = self.client_factory(vthunder)
            #need to put algorithm logic
            out = c.slb.service_group.create(pool.id, pool.protocol)
            LOG.info("Pool created successfully.")
        except Exception as e:
            print(str(e))
            LOG.info("Error occurred")

class PoolDelete(BaseVThunderTask):
    """Task to update amphora with all specified listeners' configurations."""

    def execute(self, pool, vthunder):
        """Execute create pool for an amphora."""
        try:
            axapi_version = acos_client.AXAPI_21 if vthunder.axapi_version == 21 else acos_client.AXAPI_30
            c = self.client_factory(vthunder)
            #need to put algorithm logic
            out = c.slb.service_group.delete(pool.id)
            LOG.info("Pool deleted successfully.")
        except Exception as e:
            print(str(e))
            LOG.info("Error occurred")


