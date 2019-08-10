
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


PROTOCOL_MAP = {
    constants.PROTOCOL_HTTP: constants.PROTOCOL_TCP,
    constants.PROTOCOL_HTTPS: constants.PROTOCOL_TCP,
    constants.PROTOCOL_TERMINATED_HTTPS: constants.PROTOCOL_TCP,
    constants.PROTOCOL_PROXY: constants.PROTOCOL_TCP
}

VALID_SG_PROTOCOLS = ["TCP", "UDP"]

class PoolCreate(BaseVThunderTask):
    """Task to update amphora with all specified listeners' configurations."""

    def execute(self, pool, vthunder):
        """Execute create pool for an amphora."""
        try:
            c = self.client_factory(vthunder)
            #need to put algorithm logic
            # If it exists in our dictionary, map the correct type
            # Else, use what we're given
            protocol = PROTOCOL_MAP.get(pool.protocol, pool.protocol)
            if not protocol in VALID_SG_PROTOCOLS:
                raise Exception("{protocol} is not a valid service group protocol. Must be one of ({protocols})".format(protocol=protocol, protocols=",".join(VALID_SG_PROTOCOLS))
            out = c.slb.service_group.create(pool.id, protocol)
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


