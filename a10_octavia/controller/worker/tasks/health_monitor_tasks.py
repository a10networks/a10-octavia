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

from octavia.common import exceptions
from octavia.controller.worker.v1.tasks import lifecycle_tasks

from a10_octavia.common import a10constants
from a10_octavia.common import openstack_mappings
from a10_octavia.controller.worker.tasks.decorators import axapi_client_decorator
from a10_octavia.controller.worker.tasks.decorators import axapi_client_decorator_for_revert
from a10_octavia.controller.worker.tasks import utils

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


def _get_hm_name(axapi_client, health_mon):
    try:
        hm = axapi_client.slb.hm.get(health_mon.id)
    except (acos_errors.NotFound):
        # Backwards compatability with a10-neutron-lbaas
        hm = axapi_client.slb.hm.get(health_mon.id[0:28])
    return hm['monitor']['name']


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
            health_mon.type = openstack_mappings.hm_type(self.axapi_client, health_mon.type)
        except Exception:
            raise exceptions.ProviderUnsupportedOptionError(
                prov="A10",
                user_msg=("Failed to create health monitor {}, "
                          "A health monitor of type {} is not supported "
                          "by A10 provider").format(health_mon.id, health_mon.type))

        try:
            hm_port = 0
            if listeners is not None:
                hm_port = listeners[0].protocol_port
            elif len(health_mon.pool.members) > 0:
                hm_port = health_mon.pool.members[0].protocol_port

            post_data = CONF.health_monitor.post_data
            self.axapi_client.slb.hm.create(health_mon.id,
                                            health_mon.type,
                                            health_mon.delay, health_mon.timeout,
                                            health_mon.rise_threshold, method=method,
                                            port=hm_port, url=url,
                                            expect_code=expect_code, post_data=post_data,
                                            **args)
            LOG.debug("Successfully created health monitor: %s", health_mon.id)

        except (acos_errors.ACOSException, ConnectionError) as e:
            LOG.exception("Failed to create health monitor: %s", health_mon.id)
            raise e

        if health_mon.pool is not None and health_mon.pool.members is not None:
            for member in health_mon.pool.members:
                try:
                    server_name = utils.get_member_server_name(self.axapi_client, member,
                                                               raise_not_found=False)
                    if self.axapi_client.slb.server.exists(server_name):
                        self.axapi_client.slb.server.update(server_name, member.ip_address,
                                                            health_check=health_mon.id)
                        LOG.debug("Successfully associated health monitor %s to member %s",
                                  health_mon.id, member.id)
                except (acos_errors.ACOSException, ConnectionError) as e:
                    LOG.exception(
                        "Failed to associate health monitor %s to member %s",
                        health_mon.id, member.id)
                    raise e

    @axapi_client_decorator_for_revert
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
            hm_name = _get_hm_name(self.axapi_client, health_mon)
            self.axapi_client.slb.hm.delete(hm_name)
            LOG.debug("Successfully deleted health monitor: %s", health_mon.id)
        except acos_errors.NotFound:
            LOG.debug("Health monitor %s was already deleted. Skipping...", health_mon.id)
        except (acos_errors.ACOSException, ConnectionError) as e:
            LOG.exception("Failed to delete health monitor: %s", health_mon.id)
            raise e


class UpdateHealthMonitor(task.Task):
    """Task to update Health Monitor"""

    @axapi_client_decorator
    def execute(self, listeners, health_mon, vthunder, update_dict, flavor=None):
        """ Execute update health monitor """

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
            hm_name = _get_hm_name(self.axapi_client, health_mon)
            post_data = CONF.health_monitor.post_data
            self.axapi_client.slb.hm.update(
                hm_name,
                openstack_mappings.hm_type(self.axapi_client, health_mon.type),
                health_mon.delay, health_mon.timeout, health_mon.rise_threshold,
                method=method, url=url, expect_code=expect_code, post_data=post_data,
                port=listeners[0].protocol_port, **args)
            LOG.debug("Successfully updated health monitor: %s", health_mon.id)
        except (acos_errors.ACOSException, ConnectionError) as e:
            LOG.exception("Failed to update health monitor: %s", health_mon.id)
            raise e


class HealthMonitorToErrorOnRevertTask(lifecycle_tasks.BaseLifecycleTask):
    """Task to update Health Monitor"""

    def execute(self, health_mon):
        pass

    def revert(self, health_mon, *args, **kwargs):
        try:
            self.task_utils.mark_health_mon_prov_status_error(health_mon.pool_id)
        except Exception as e:
            LOG.exception("Failed to change status to error due to: %s", e)
