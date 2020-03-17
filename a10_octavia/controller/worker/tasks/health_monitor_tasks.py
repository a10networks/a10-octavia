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


from oslo_log import log as logging
from oslo_config import cfg
from a10_octavia.controller.worker.tasks.common import BaseVThunderTask
from a10_octavia.common import openstack_mappings

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class CreateAndAssociateHealthMonitor(BaseVThunderTask):
    """ Task to create a healthmonitor and associate it with provided pool. """

    def execute(self, health_mon, vthunder):
        """ Execute create health monitor """

        # TODO(hthompson6) Length of name of healthmonitor for older vThunder devices
        try:
            method = None
            url = None
            expect_code = None
            if health_mon.type in ['HTTP', 'HTTPS']:
                method = health_mon.http_method
                url = health_mon.url_path
                expect_code = health_mon.expected_codes
            args = self.meta(health_mon, 'hm', {})
            c = self.client_factory(vthunder)
            c.slb.hm.create(health_mon.id[0:5],
                            openstack_mappings.hm_type(c, health_mon.type),
                            health_mon.delay, health_mon.timeout,
                            health_mon.rise_threshold, method=method, url=url,
                            expect_code=expect_code, port=None, axapi_args=args)
            LOG.info("Health Monitor created successfully.")
            c.slb.service_group.update(health_mon.pool_id,
                                       health_monitor=health_mon.id[0:5],
                                       health_check_disable=0)
            LOG.info("Health Monitor associated to pool successfully.")
        except Exception as e:
            LOG.error(str(e))
            LOG.info("Error occurred")


class DeleteHealthMonitor(BaseVThunderTask):
    """ Task to disassociate healthmonitor from pool and then delete a healthmonitor """

    def execute(self, health_mon, vthunder):
        """ Execute delete health monitor  """
        try:
            c = self.client_factory(vthunder)
            c.slb.service_group.update(health_mon.pool_id,
                                       health_monitor="",
                                       health_check_disable=True)
            LOG.info("Health Monitor disassociated to pool successfully.")
            c.slb.hm.delete(health_mon.id[0:5])
            LOG.info("Health Monitor deleted successfully.")
        except Exception as e:
            LOG.error(str(e))


class UpdateHealthMonitor(BaseVThunderTask):
    """ Task to update health monitor. """

    def execute(self, health_mon, vthunder, update_dict):
        """ Execute update health monitor """
        # TODO(hthompson6) Length of name of healthmonitor for older vThunder devices
        health_mon.__dict__.update(update_dict)
        try:
            method = None
            url = None
            expect_code = None
            if health_mon.type in ['HTTP', 'HTTPS']:
                method = health_mon.http_method
                url = health_mon.url_path
                expect_code = health_mon.expected_codes
            args = self.meta(health_mon, 'hm', {})
            c = self.client_factory(vthunder)
            c.slb.hm.update(health_mon.id[0:5], openstack_mappings.hm_type(c, health_mon.type),
                            health_mon.delay, health_mon.timeout, health_mon.rise_threshold,
                            method=method, url=url, expect_code=expect_code, port=None,
                            axapi_args=args
                            )
            LOG.info("Health Monitor created successfully.")
        except Exception as e:
            LOG.error(str(e))
            LOG.info("Error occurred")
