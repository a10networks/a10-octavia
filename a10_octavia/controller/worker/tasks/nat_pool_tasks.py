#    Copyright 2020, A10 Networks
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
from requests.exceptions import ConnectionError
from taskflow import task

import acos_client.errors as acos_errors

from a10_octavia.controller.worker.tasks.decorators import axapi_client_decorator
from a10_octavia.controller.worker.tasks.decorators import axapi_client_decorator_for_revert

LOG = logging.getLogger(__name__)


class NatPoolCreate(task.Task):
    """Task to create nat pool"""
    def __init__(self, **kwargs):
        super(NatPoolCreate, self).__init__(**kwargs)
        self._added_pool_list = []

    @axapi_client_decorator
    def execute(self, subnet, loadbalancer, vthunder, flavor_data=None):
        device_pool = None
        if flavor_data:
            natpool_flavor_list = flavor_data.get('nat_pool_list')
            natpool_flavor = flavor_data.get('nat_pool')
            if natpool_flavor_list:
                for nat_pool in natpool_flavor_list:
                    if subnet.ip_version == 6:
                        device_pool = self.axapi_client.nat.ipv6pool.try_get(nat_pool['pool_name'])
                    else:
                        device_pool = self.axapi_client.nat.pool.try_get(nat_pool['pool_name'])
                    if not (device_pool and
                            (device_pool['pool']['start-address'] == nat_pool['start_address'] and
                                device_pool['pool']['end-address'] == nat_pool['end_address'])):
                        try:
                            if subnet.ip_version == 6:
                                self.axapi_client.nat.ipv6pool.create(**nat_pool)
                            else:
                                self.axapi_client.nat.pool.create(**nat_pool)
                            self._added_pool_list.append(nat_pool['pool_name'])
                        except (acos_errors.Exists) as e:
                            LOG.exception("Nat-pool with name %s already exists on partition %s of "
                                          "thunder device %s",
                                          nat_pool['pool_name'], vthunder.partition_name,
                                          vthunder.ip_address)
                            raise e
                        except Exception as e:
                            LOG.exception("Failed to create nat-pool with name %s on partition %s"
                                          " of thunder device %s",
                                          nat_pool['pool_name'], vthunder.partition_name,
                                          vthunder.ip_address)
                            raise e
            if natpool_flavor:
                if subnet.ip_version == 6:
                    device_pool = self.axapi_client.nat.ipv6pool.try_get(
                        natpool_flavor['pool_name'])
                else:
                    device_pool = self.axapi_client.nat.pool.try_get(natpool_flavor['pool_name'])
                if (device_pool and
                    (device_pool['pool']['start-address'] == natpool_flavor['start_address']
                        and device_pool['pool']['end-address'] == natpool_flavor['end_address']
                     )):
                    return
                try:
                    if subnet.ip_version == 6:
                        self.axapi_client.nat.ipv6pool.create(**natpool_flavor)
                    else:
                        self.axapi_client.nat.pool.create(**natpool_flavor)
                    self._added_pool_list.append(natpool_flavor['pool_name'])
                except (acos_errors.Exists) as e:
                    LOG.exception("Nat-pool with name %s already exists on partition %s of "
                                  "thunder device %s",
                                  natpool_flavor['pool_name'], vthunder.partition_name,
                                  vthunder.ip_address)
                    raise e
                except Exception as e:
                    LOG.exception("Failed to create nat-pool with name %s on partition %s of "
                                  "thunder device %s",
                                  natpool_flavor['pool_name'], vthunder.partition_name,
                                  vthunder.ip_address)
                    raise e

    @axapi_client_decorator_for_revert
    def revert(self, subnet, loadbalancer, vthunder, flavor_data=None, *args, **kwargs):
        if flavor_data:
            try:
                natpool_flavor_list = flavor_data.get('nat_pool_list')
                natpool_flavor = flavor_data.get('nat_pool')

                if len(self._added_pool_list) > 0:
                    if natpool_flavor_list:
                        for nat_pool in natpool_flavor_list:
                            pool_name = nat_pool.get('pool_name')
                            if pool_name in self._added_pool_list:
                                LOG.warning("Reverting creation of nat-pool: %s", pool_name)
                                if subnet.ip_version == 6:
                                    self.axapi_client.nat.ipv6pool.delete(pool_name)
                                else:
                                    self.axapi_client.nat.pool.delete(pool_name)
                    if natpool_flavor:
                        pool_name = natpool_flavor.get('pool_name')
                        if pool_name in self._added_pool_list:
                            LOG.warning("Reverting creation of nat-pool: %s", pool_name)
                            if subnet.ip_version == 6:
                                self.axapi_client.nat.ipv6pool.delete(pool_name)
                            else:
                                self.axapi_client.nat.pool.delete(pool_name)
            except ConnectionError:
                LOG.exception(
                    "Failed to connect A10 Thunder device: %s", vthunder.ip_address)
            except (acos_errors.ACOSException, Exception) as e:
                LOG.exception("Failed to revert creation of nat-pool %s due to: %s",
                              pool_name, str(e))


class NatPoolDelete(task.Task):
    """Task to delete nat pool"""

    @axapi_client_decorator
    def execute(self, subnet, loadbalancer, vthunder, lb_count_flavor, flavor_data=None):
        if vthunder:
            if lb_count_flavor <= 1:
                if flavor_data:
                    natpool_flavor_list = flavor_data.get('nat_pool_list')
                    natpool_flavor = flavor_data.get('nat_pool')
                    if natpool_flavor_list:
                        for nat_pool in natpool_flavor_list:
                            pool_name = nat_pool['pool_name']
                            try:
                                if subnet.ip_version == 6:
                                    self.axapi_client.nat.ipv6pool.delete(pool_name)
                                else:
                                    self.axapi_client.nat.pool.delete(pool_name)
                            except (acos_errors.ACOSException) as e:
                                LOG.exception("Failed to delete Nat-pool with name %s due to %s",
                                              pool_name, str(e))
                    if natpool_flavor:
                        pool_name = natpool_flavor['pool_name']
                        try:
                            if subnet.ip_version == 6:
                                self.axapi_client.nat.ipv6pool.delete(pool_name)
                            else:
                                self.axapi_client.nat.pool.delete(pool_name)
                        except (acos_errors.ACOSException) as e:
                            LOG.exception("Failed to delete Nat-pool with name %s due to %s",
                                          pool_name, str(e))
            else:
                LOG.warning("Cannot delete Nat-pool(s) in flavor %s as "
                            "they are in use by another loadbalancer(s)", loadbalancer.flavor_id)
