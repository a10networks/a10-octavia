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

class CreateAndAssociateHealthMonitor(BaseVThunderTask):
    """ Task to create a healthmonitor and associate it with provided pool. """

    def execute(self, health_mon, vthunder):
        """ Execute create health monitor for amphora """
        # TODO : Length of name of healthmonitor for older vThunder devices
        axapi_version = acos_client.AXAPI_21 if vthunder.axapi_version == 21 else acos_client.AXAPI_30
        try:
            method = None
            url = None
            expect_code = None
            port = None
            if health_mon.type in ['HTTP', 'HTTPS']:
                method = health_mon.http_method
                url = health_mon.url_path
                expect_code = health_mon.expected_codes
            client = acos_client.Client(vthunder.ip_address, axapi_version, vthunder.username,
                                       vthunder.password)
            out = client.slb.hm.create(health_mon.id[0:5], openstack_mappings.hm_type(client, health_mon.type),
                                         health_mon.delay, health_mon.timeout, health_mon.rise_threshold,
                                         method=method, url=url, expect_code=expect_code, port=port
                                         )
            LOG.info("Heath Monitor created successfully.")
        except Exception as e:
            print(str(e))
        try:
            client = acos_client.Client(vthunder.ip_address, axapi_version, vthunder.username,
                                       vthunder.password)
            out = client.slb.service_group.update(health_mon.pool_id,
                                                    health_monitor=health_mon.id[0:5],
                                                    health_check_disable=0)
            LOG.info("Heath Monitor associated to pool successfully.")
        except Exception as e:
            print(str(e))
            LOG.info("Error occurred")

class DeleteHealthMonitor(BaseVThunderTask):
    """ Task to create a healthmonitor and associate it with provided pool. """

    def execute(self, health_mon, vthunder):
        """ Execute create health monitor for amphora """
        axapi_version = acos_client.AXAPI_21 if vthunder.axapi_version == 21 else acos_client.AXAPI_30
        try:
            c = acos_client.Client(vthunder.ip_address, axapi_version, vthunder.username,
                                       vthunder.password)
            out = c.slb.service_group.update(health_mon.pool_id,
                                                    health_monitor="",
                                                    health_check_disable=False)
            LOG.info("Heath Monitor disassociated to pool successfully.")
        except Exception as e:
            print(str(e))
            LOG.info("Error occurred")
        try:
            c = acos_client.Client(vthunder.ip_address, axapi_version, vthunder.username,
                                       vthunder.password)
            out = c.slb.hm.delete(health_mon.id)
            LOG.info("Heath Monitor deleted successfully.")
        except Exception as e:
            print(str(e))


