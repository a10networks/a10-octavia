from taskflow import task

from octavia.controller.worker import task_utils as task_utilities
from octavia.common import constants
import acos_client

import logging
from oslo_config import cfg
CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class BaseVThunderTask(task.Task):
    """Base task to instansiate common classes."""

    def __init__(self, **kwargs):
        self.task_utils = task_utilities.TaskUtils()
        super(BaseVThunderTask, self).__init__(**kwargs)
        self.c = acos_client.Client('138.197.107.20', acos_client.AXAPI_21, 'admin', 'a10')

class CreateVitualServerTask(BaseVThunderTask):
    """Task to create a virtual server in vthunder device."""

    def execute(self, loadbalancer_id):
        try:
            r = self.c.slb.virtual_server.create(loadbalancer_id, lb.vip.ip_address)
            status = { 'loadbalancers': [{"id": loadbalancer_id,
                       "provisioning_status": constants.ACTIVE }]}
        except Exception as e:
            r = str(e)
            status = { 'loadbalancers': [{"id": loadbalancer_id,
                       "provisioning_status": constants.ERROR }]}
        LOG.info("##########################hello##############")
        LOG.info(str(status))
        return status


    def revert(self, loadbalancer_id, *args, **kwargs):
        pass
