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


from acos_client import errors as acos_errors
from oslo_config import cfg
from oslo_log import log as logging
from requests.exceptions import ConnectionError
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
    def execute(self, listeners, health_mon, vthunder, flavor=None):
        method = None
        url = None
        expect_code = None

        if health_mon.type in a10constants.HTTP_TYPE:
            method = health_mon.http_method
            url = health_mon.url_path
            expect_code = health_mon.expected_codes
        args = utils.meta(health_mon, 'hm', {})
        args = utils.dash_to_underscore(args)

        # overwrite options from flavor
        if flavor:
            flavors = flavor.get('health_monitor')
            if flavors:
                name_exprs = flavors.get('name_expressions')
                parsed_exprs = utils.parse_name_expressions(health_mon.name, name_exprs)
                flavors.pop('name_expressions', None)
                flavors.update(parsed_exprs)
                args.update({'monitor': flavors})

        try:
            post_data = CONF.health_monitor.post_data
            self.axapi_client.slb.hm.create(health_mon.id,
                                            openstack_mappings.hm_type(self.axapi_client,
                                                                       health_mon.type),
                                            health_mon.delay, health_mon.timeout,
                                            health_mon.rise_threshold, method=method,
                                            port=listeners[0].protocol_port, url=url,
                                            expect_code=expect_code, post_data=post_data,
                                            **args)
            LOG.debug("Successfully created health monitor: %s", health_mon.id)

        except (acos_errors.ACOSException, ConnectionError) as e:
            LOG.exception("Failed to create health monitor: %s", health_mon.id)
            raise e

        try:
            self.axapi_client.slb.service_group.update(health_mon.pool_id,
                                                       hm_name=health_mon.id,
                                                       health_check_disable=0)
            LOG.debug("Successfully associated health monitor %s to pool %s",
                      health_mon.id, health_mon.pool_id)
        except (acos_errors.ACOSException, ConnectionError) as e:
            LOG.exception(
                "Failed to associate health monitor %s to pool %s",
                health_mon.id, health_mon.pool_id)
            raise e

    @axapi_client_decorator
    def revert(self, listeners, health_mon, vthunder, *args, **kwargs):
        try:
            self.axapi_client.slb.hm.delete(health_mon.id)
        except ConnectionError:
            LOG.exception("Failed to connect A10 Thunder device: %s", vthunder.ip_address)
        except Exception as e:
            LOG.warning(
                "Failed to revert creation of health monitor: %s due to %s",
                health_mon.id, str(e))


class DeleteHealthMonitor(task.Task):
    """Task to disassociate Health Monitor from pool and delete"""

    @axapi_client_decorator
    def execute(self, health_mon, vthunder):
        try:
            self.axapi_client.slb.service_group.update(health_mon.pool_id,
                                                       hm_delete=True)
            LOG.debug("Successfully dissociated health monitor %s from pool %s",
                      health_mon.id, health_mon.pool_id)
        except (acos_errors.ACOSException, ConnectionError) as e:
            LOG.exception(
                "Failed to dissociate health monitor %s from pool %s",
                health_mon.pool_id, health_mon.id)
            raise e

        try:
            self.axapi_client.slb.hm.delete(health_mon.id)
            LOG.debug("Successfully deleted health monitor: %s", health_mon.id)
        except (acos_errors.ACOSException, ConnectionError) as e:
            LOG.exception("Failed to delete health monitor: %s", health_mon.id)
            raise e


class UpdateHealthMonitor(task.Task):
    """Task to update Health Monitor"""

    @axapi_client_decorator
    def execute(self, listeners, health_mon, vthunder, update_dict, flavor=None):
        """ Execute update health monitor """
        # TODO(hthompson6) Length of name of healthmonitor for older vThunder devices
        health_mon.update(update_dict)
        method = None
        url = None
        expect_code = None
        if health_mon.type in a10constants.HTTP_TYPE:
            method = health_mon.http_method
            url = health_mon.url_path
            expect_code = health_mon.expected_codes
        args = utils.meta(health_mon, 'hm', {})
        args = utils.dash_to_underscore(args)

        # overwrite options from flavor
        if flavor:
            flavors = flavor.get('health_monitor')
            if flavors:
                name_exprs = flavors.get('name_expressions')
                parsed_exprs = utils.parse_name_expressions(health_mon.name, name_exprs)
                flavors.pop('name_expressions', None)
                flavors.update(parsed_exprs)
                args.update({'monitor': flavors})

        try:
            post_data = CONF.health_monitor.post_data
            self.axapi_client.slb.hm.update(
                health_mon.id,
                openstack_mappings.hm_type(self.axapi_client, health_mon.type),
                health_mon.delay, health_mon.timeout, health_mon.rise_threshold,
                method=method, url=url, expect_code=expect_code, post_data=post_data,
                port=listeners[0].protocol_port, **args)
            LOG.debug("Successfully updated health monitor: %s", health_mon.id)
        except (acos_errors.ACOSException, ConnectionError) as e:
            LOG.exception("Failed to update health monitor: %s", health_mon.id)
            raise e
