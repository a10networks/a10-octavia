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
from taskflow import task

from a10_octavia.common import a10constants
from a10_octavia.common import openstack_mappings
from a10_octavia.controller.worker.tasks.decorators import axapi_client_decorator
from a10_octavia.controller.worker.tasks import utils

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class CreateAndAssociateHealthMonitor(task.Task):
    """Task to create a healthmonitor and associate it with provided pool."""

    @axapi_client_decorator
    def execute(self, health_mon, vthunder):
        method = None
        url = None
        expect_code = None
        if health_mon.type in a10constants.HTTP_TYPE:
            method = health_mon.http_method
            url = health_mon.url_path
            expect_code = health_mon.expected_codes
        args = utils.meta(health_mon, 'hm', {})

        try:
            self.axapi_client.slb.hm.create(health_mon.id[0:5],
                                            openstack_mappings.hm_type(self.axapi_client,
                                            health_mon.type),
                                            health_mon.delay, health_mon.timeout,
                                            health_mon.rise_threshold, method=method, url=url,
                                            expect_code=expect_code, axapi_args=args)
            LOG.debug("Health Monitor created successfully: %s", health_mon.id)
        except Exception as e:
            LOG.exception("Failed to create Health Monitor: %s", str(e))
            raise

        try:
            self.axapi_client.slb.service_group.update(health_mon.pool_id,
                                                       health_monitor=health_mon.id[0:5],
                                                       health_check_disable=0)
            LOG.debug("Health Monitor %s is associated to pool %s successfully.",
                      health_mon.id, health_mon.pool_id)
        except Exception as e:
            LOG.exception("Failed to associate pool to Health Monitor: %s", str(e))
            raise


class DeleteHealthMonitor(task.Task):
    """Task to disassociate Health Monitor from pool and delete"""

    @axapi_client_decorator
    def execute(self, health_mon, vthunder):
        try:
            self.axapi_client.slb.service_group.update(health_mon.pool_id,
                                                       health_monitor="",
                                                       health_check_disable=True)
            LOG.debug("Health Monitor %s is dissociated from pool %s successfully.",
                      health_mon.id, health_mon.pool_id)
        except Exception as e:
            LOG.warning("Failed to dissociate Health Monitor from pool: %s", str(e))
        try:
            self.axapi_client.slb.hm.delete(health_mon.id[0:5])
            LOG.debug("Health Monitor deleted successfully: %s", health_mon.id)
        except Exception as e:
            LOG.warning("Failed to delete health monitor: %s", str(e))


class UpdateHealthMonitor(task.Task):
    """Task to update Health Monitor"""

    @axapi_client_decorator
    def execute(self, health_mon, vthunder, update_dict):
        """ Execute update health monitor """
        # TODO(hthompson6) Length of name of healthmonitor for older vThunder devices
        health_mon.__dict__.update(update_dict)
        method = None
        url = None
        expect_code = None
        if health_mon.type in a10constants.HTTP_TYPE:
            method = health_mon.http_method
            url = health_mon.url_path
            expect_code = health_mon.expected_codes
        args = utils.meta(health_mon, 'hm', {})
        try:
            self.axapi_client.slb.hm.update(
                health_mon.id[0:5],
                openstack_mappings.hm_type(self.axapi_client, health_mon.type),
                health_mon.delay, health_mon.timeout, health_mon.rise_threshold,
                method=method, url=url, expect_code=expect_code, axapi_args=args)
            LOG.debug("Health Monitor updated successfully: %s", health_mon.id)
        except Exception as e:
            LOG.exception("Failed to update Health Monitor: %s", str(e))
