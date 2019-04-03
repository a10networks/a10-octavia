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

    def execute(self, loadbalancer_id, loadbalancer, amphora):
        try:
            #IMP: update required
            vthunder = amphora.cached_zone
            c = acos_client.Client(vthunder.ip, vthunder.acos_version, vthunder.username, vthunder.password)
            r = self.c.slb.virtual_server.create(loadbalancer_id, loadbalancer.vip.ip_address)
            status = { 'loadbalancers': [{"id": loadbalancer_id,
                       "provisioning_status": constants.ACTIVE }]}
            LOG.info("amphora id is:" + str(amphora.id))
            LOG.info("vthunder details:" + str(vthunder))
        except Exception as e:
            r = str(e)
            LOG.info(r)
            status = { 'loadbalancers': [{"id": loadbalancer_id,
                       "provisioning_status": constants.ERROR }]}
        LOG.info(str(status))
        return status


    def revert(self, loadbalancer_id, *args, **kwargs):
        pass

class DeleteVitualServerTask(BaseVThunderTask):
    """Task to delete a virtual server in vthunder device."""

    def execute(self, loadbalancer, amphora):
        loadbalancer_id = loadbalancer.id
        try:
            #IMP: update required
            
            vthunder = amphora[0].cached_zone
            #c = acos_client.Client(vthunder.ip, vthunder.acos_version, vthunder.username, vthunder.password)
            #r = self.c.slb.virtual_server.delete(loadbalancer_id)
            status = { 'loadbalancers': [{"id": loadbalancer_id,
                       "provisioning_status": constants.DELETED }]}
            LOG.info(amphora[0].cached_zone)
            LOG.info("amphora id is:" + str(amphora[0].id))
        except Exception as e:
            r = str(e)
            LOG.info(r)
            status = { 'loadbalancers': [{"id": loadbalancer_id,
                       "provisioning_status": constants.ERROR }]}
        LOG.info(str(status))
        return status

    def revert(self, loadbalancer, *args, **kwargs):
        pass

