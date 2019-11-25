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

class CreateAndAssociateHealthMonitor(BaseVThunderTask):
    """ Task to create a healthmonitor and associate it with provided pool. """

    def execute(self, health_mon, vthunder):
        """ Execute create health monitor for amphora """

        # TODO : Length of name of healthmonitor for older vThunder devices
        try:
            method = None
            url = None
            expect_code = None
            port = None
            if health_mon.type in ['HTTP', 'HTTPS']:
                method = health_mon.http_method
                url = health_mon.url_path
                expect_code = health_mon.expected_codes
            args = self.meta(health_mon, 'hm', {})
            c = self.client_factory(vthunder)
            out = c.slb.hm.create(health_mon.id[0:5],
                                  openstack_mappings.hm_type(c, health_mon.type),
                                  health_mon.delay, health_mon.timeout,
                                  health_mon.rise_threshold, method=method, url=url,
                                  expect_code=expect_code, port=port, axapi_args=args)
            LOG.info("Health Monitor created successfully.")
        except Exception as e:
            print(str(e))

        try:
            c = self.client_factory(vthunder)
            out = c.slb.service_group.update(health_mon.pool_id,
                                             health_monitor=health_mon.id[0:5],
                                             health_check_disable=0)
            LOG.info("Health Monitor associated to pool successfully.")
        except Exception as e:
            print(str(e))
            LOG.info("Error occurred")

class DeleteHealthMonitor(BaseVThunderTask):
    """ Task to create a healthmonitor and associate it with provided pool. """

    def execute(self, health_mon, vthunder):
        """ Execute create health monitor for amphora """
        try:
            c = self.client_factory(vthunder)
            out = c.slb.service_group.update(health_mon.pool_id,
                                                    health_monitor="",
                                                    health_check_disable=False)
            LOG.info("Health Monitor disassociated to pool successfully.")
        except Exception as e:
            print(str(e))
            LOG.info("Error occurred")
        try:
            c = self.client_factory(vthunder)
            out = c.slb.hm.delete(health_mon.id)
            LOG.info("Health Monitor deleted successfully.")
        except Exception as e:
            print(str(e))

class UpdateHealthMonitor(BaseVThunderTask):

     def execute(self, health_mon, vthunder):
        """ Execute create health monitor for amphora """
        # TODO : Length of name of healthmonitor for older vThunder devices
        axapi_version = acos_client.AXAPI_21 if vthunder.axapi_version == 21 else acos_client.AXAPI_30
        try:
            method = None
            url = None
            expect_code = None
            port = None
            update=True
            if health_mon.type in ['HTTP', 'HTTPS']:
                method = health_mon.http_method
                url = health_mon.url_path
                expect_code = health_mon.expected_codes
            client = acos_client.Client(vthunder.ip_address, axapi_version, vthunder.username,
                                       vthunder.password)
            out = client.slb.hm.create(health_mon.id[0:5], openstack_mappings.hm_type(client, health_mon.type),
                                         health_mon.delay, health_mon.timeout, health_mon.rise_threshold,
                                         method=method, url=url, expect_code=expect_code, port=port, update=update
                                         )
            LOG.info("Heath Monitor created successfully.")
        except Exception as e:
            print(str(e))
            LOG.info("Error occurred")

