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
from taskflow import task

import acos_client.errors as acos_errors

from a10_octavia.controller.worker.tasks.decorators import axapi_client_decorator

LOG = logging.getLogger(__name__)


class NatPoolCreate(task.Task):
    """Task to create nat pool"""

    @axapi_client_decorator
    def execute(self, loadbalancer, vthunder, flavor_data=None):
        device_pool = None
        if flavor_data:
            natpool_flavor_list = flavor_data.get('nat_pool_list')
            natpool_flavor = flavor_data.get('nat_pool')
            if natpool_flavor_list:
                for i in range(len(natpool_flavor_list)):
                    if self.axapi_client.nat.pool.exists(natpool_flavor_list[i]['pool_name']):
                        device_pool = self.axapi_client.nat.pool.get(
                            natpool_flavor_list[i]['pool_name'])
                    if not (device_pool and
                            (device_pool['pool']['start-address'] ==
                                natpool_flavor_list[i]['start_address'] and
                                device_pool['pool']['end-address'] ==
                                natpool_flavor_list[i]['end_address'])):
                        pool_name = natpool_flavor_list[i]['pool_name']
                        start_address = natpool_flavor_list[i]['start_address']
                        end_address = natpool_flavor_list[i]['end_address']
                        netmask = natpool_flavor_list[i]['netmask']
                        gateway = natpool_flavor_list[i]['gateway']
                        try:
                            self.axapi_client.nat.pool.create(
                                pool_name, start_address, end_address, netmask, gateway=gateway)
                        except(acos_errors.Exists) as e:
                            LOG.exception(
                                "The specified nat-pool already exists on thunder")
                            raise e
                    else:
                        continue
            if natpool_flavor:
                if self.axapi_client.nat.pool.exists(natpool_flavor['pool_name']):
                    device_pool = self.axapi_client.nat.pool.get(
                        natpool_flavor['pool_name'])
                if (device_pool and
                    (device_pool['pool']['start-address'] == natpool_flavor['start_address']
                        and device_pool['pool']['end-address'] == natpool_flavor['end_address']
                     )):
                    return
                pool_name = natpool_flavor['pool_name']
                start_address = natpool_flavor['start_address']
                end_address = natpool_flavor['end_address']
                netmask = natpool_flavor['netmask']
                gateway = natpool_flavor['gateway']
                try:
                    self.axapi_client.nat.pool.create(
                        pool_name, start_address, end_address, netmask, gateway=gateway)
                except(acos_errors.Exists) as e:
                    LOG.exception("The specified nat-pool already exists on thunder")
                    raise e
