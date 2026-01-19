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

from octavia.common import constants
from octavia.common import exceptions
from octavia.controller.worker.v2.tasks import lifecycle_tasks

from a10_octavia.common import a10constants
from a10_octavia.common import openstack_mappings
from a10_octavia.controller.worker.tasks.decorators import axapi_client_decorator
from a10_octavia.controller.worker.tasks.decorators import axapi_client_decorator_for_revert
from a10_octavia.controller.worker.tasks import utils
 
CONF = cfg.CONF
LOG = logging.getLogger(__name__)
 
 
def _get_hm_name(axapi_client, health_mon):
    if axapi_client and axapi_client.slb:
        try:
            hm_id = health_mon.get(constants.HEALTHMONITOR_ID) or health_mon.get(constants.ID)
            hm = axapi_client.slb.hm.get(hm_id)
        except (acos_errors.NotFound):
            # Backwards compatability with a10-neutron-lbaas
            hm = axapi_client.slb.hm.get(hm_id[0:28])
        return hm['monitor']['name']

class CreateAndAssociateHealthMonitor(task.Task):
    """Task to create a healthmonitor and associate it with provided pool."""

    @axapi_client_decorator
    def execute(self, listeners, health_mon, pool, vthunder, flavor=None):
        hm_id = health_mon.get(constants.HEALTHMONITOR_ID) or health_mon.get(constants.HEALTH_MONITOR_ID) or health_mon.get(constants.ID)
        LOG.debug("health monitor ID: %s", hm_id)
        method = None
        url = None
        expect_code = None

        if health_mon.get(constants.TYPE) in a10constants.HTTP_TYPE:
            method = health_mon[constants.HTTP_METHOD]
            url = health_mon[constants.URL_PATH]
            expect_code = health_mon[constants.EXPECTED_CODES]
        args = utils.meta(health_mon, 'hm', {})
        args = utils.dash_to_underscore(args)

        # overwrite options from flavor
        if flavor:
            flavors = flavor.get('health_monitor')
            if flavors:
                name_exprs = flavors.get('name_expressions')
                parsed_exprs = utils.parse_name_expressions(health_mon.get(constants.NAME), name_exprs)
                flavors.pop('name_expressions', None)
                flavors.update(parsed_exprs)
                args.update({'monitor': flavors})

        try:
            health_mon[constants.TYPE] = openstack_mappings.hm_type(self.axapi_client, health_mon.get(constants.TYPE))
        except Exception:
            raise exceptions.ProviderUnsupportedOptionError(
                prov="A10",
                user_msg=("Failed to create health monitor {}, "
                          "A health monitor of type {} is not supported "
                          "by A10 provider").format(hm_id, health_mon.get(constants.TYPE)))

        try:
            hm_port = 0
            if listeners is not None:
                hm_port = listeners[0].get('protocol_port')
            elif health_mon.get(constants.POOL) and health_mon.get(constants.POOL).members:
                hm_port = health_mon.get(constants.POOL).members[0].protocol_port

            post_data = CONF.health_monitor.post_data
            hm_max_retries = health_mon.get(constants.MAX_RETRIES)
            if hm_max_retries is None:
                # Fallback to Octavia default or A10 safe default
                hm_max_retries = CONF.health_monitor.max_retries if hasattr(CONF.health_monitor, 'max_retries') else 3
            self.axapi_client.slb.hm.create(hm_id,
                                            health_mon.get(constants.TYPE),
                                            health_mon.get(constants.DELAY), health_mon.get(constants.TIMEOUT),
                                            hm_max_retries=hm_max_retries, method=method,
                                            port=hm_port, url=url,
                                            expect_code=expect_code, post_data=post_data,
                                            **args)
            LOG.debug("Successfully created health monitor: %s", hm_id)

        except (acos_errors.ACOSException, ConnectionError) as e:
            LOG.exception("Failed to create health monitor: %s", hm_id)
            raise e

        # pool = getattr(health_mon, "pool", None) or health_mon.get(constants.POOL, None)
        # if health_mon.get(constants.POOL_ID) and pool and pool.get(constants.MEMBERS):
        if health_mon.get(constants.POOL_ID) is not None and pool.get(constants.MEMBERS) is not None:
            for member in pool.get(constants.MEMBERS):
                try:
                    server_name = utils.get_member_server_name(self.axapi_client, member,
                                                               raise_not_found=False)
                    if self.axapi_client.slb.server.exists(server_name):
                        self.axapi_client.slb.server.update(server_name, member.get('ip_address'),
                                                            health_check=hm_id)
                        LOG.debug("Successfully associated health monitor %s to member %s",
                                  hm_id, member.get('id'))
                except (acos_errors.ACOSException, ConnectionError) as e:
                    LOG.exception(
                        "Failed to associate health monitor %s to member %s",
                        hm_id, member.get('id'))
                    raise e

    @axapi_client_decorator_for_revert
    def revert(self, listeners, health_mon, vthunder, *args, **kwargs):
        hm_id = (health_mon.get(constants.HEALTHMONITOR_ID) or health_mon.get(constants.HEALTH_MONITOR_ID) or health_mon.get(constants.ID) )
        try:
            self.axapi_client.slb.hm.delete(hm_id)
        except ConnectionError:
            LOG.exception("Failed to connect A10 Thunder device: %s", vthunder.ip_address)
        except Exception as e:
            LOG.warning(
                "Failed to revert creation of health monitor: %s due to %s",
                hm_id, str(e))
 

class DeleteHealthMonitor(task.Task):
    """Task to disassociate Health Monitor from pool and delete"""

    @axapi_client_decorator
    def execute(self, health_mon, vthunder):
        if self.axapi_client and self.axapi_client.slb:
            try:
                hm_id = health_mon.get(constants.HEALTHMONITOR_ID) or health_mon.get(constants.ID)
                hm_name = _get_hm_name(self.axapi_client, health_mon)
                self.axapi_client.slb.hm.delete(hm_name)
                LOG.debug("Successfully deleted health monitor: %s", hm_id)
            except acos_errors.NotFound:
                LOG.debug("Health monitor %s was already deleted. Skipping...", hm_id)
            except (acos_errors.ACOSException, ConnectionError) as e:
                LOG.exception("Failed to delete health monitor: %s", hm_id)
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
        if health_mon.get(constants.TYPE) in a10constants.HTTP_TYPE:
            method = health_mon.get(constants.HTTP_METHOD)
            url = health_mon.get(constants.URL_PATH)
            expect_code = health_mon.get(constants.EXPECTED_CODES)
        args = utils.meta(health_mon, 'hm', {})
        args = utils.dash_to_underscore(args)
 
        # overwrite options from flavor
        if flavor:
            flavors = flavor.get('health_monitor')
            if flavors:
                name_exprs = flavors.get('name_expressions')
                parsed_exprs = utils.parse_name_expressions(health_mon.get(constants.NAME), name_exprs)
                flavors.pop('name_expressions', None)
                flavors.update(parsed_exprs)
                args.update({'monitor': flavors})
 
        try:
            hm_name = _get_hm_name(self.axapi_client, health_mon)
            post_data = CONF.health_monitor.post_data
            self.axapi_client.slb.hm.update(
                hm_name,
                openstack_mappings.hm_type(self.axapi_client, health_mon.get(constants.TYPE)),
                health_mon.get(constants.DELAY), health_mon.get(constants.TIMEOUT), health_mon.get(constants.MAX_RETRIES),
                method=method, url=url, expect_code=expect_code, post_data=post_data,
                port=listeners[0].get('protocol_port'), **args)
            LOG.debug("Successfully updated health monitor: %s", health_mon[constants.HEALTHMONITOR_ID])
        except (acos_errors.ACOSException, ConnectionError) as e:
            LOG.exception("Failed to update health monitor: %s", health_mon[constants.HEALTHMONITOR_ID])
            raise e
 
 
class HealthMonitorToErrorOnRevertTask(lifecycle_tasks.BaseLifecycleTask):
    """Task to update Health Monitor"""
 
    def execute(self, health_mon):
        pass
 
    def revert(self, health_mon, *args, **kwargs):
        try:
            self.task_utils.mark_health_mon_prov_status_error(health_mon[constants.POOL_ID])
        except Exception as e:
            LOG.exception("Failed to change status to error due to: %s", e)