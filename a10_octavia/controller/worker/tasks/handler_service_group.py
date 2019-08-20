
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
        args = {'service_group': self.meta(pool, 'service_group', {})}

        try:
            try:
               conf_templates = self.config.get('SERVICE_GROUP','templates')
               conf_templates = conf_templates.replace('"', '')
               service_group_temp = {}
               service_group_temp['template-server'] = conf_templates
            except:
               service_group_temp = None
            c = self.client_factory(vthunder)
            #need to put algorithm logic
            lb_method=openstack_mappings.service_group_lb_method(c,pool.lb_algorithm)

            out = c.slb.service_group.create(pool.id, pool.protocol,lb_method,service_group_temp,axapi_args=args)
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


