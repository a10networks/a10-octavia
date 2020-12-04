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

import acos_client.errors as acos_errors
from oslo_config import cfg
from oslo_log import log as logging
from requests import exceptions
from taskflow import task


from a10_octavia.controller.worker.tasks.decorators import axapi_client_decorator
from a10_octavia.controller.worker.tasks import utils


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class LoadBalancerParent(object):

    def set(self, set_method, loadbalancer, flavor_data=None, **kwargs):
        config_args = {
            'arp_disable': CONF.slb.arp_disable,
            'port_list': kwargs.get('port_list'),
            'vrid': CONF.slb.default_virtual_server_vrid,
            'virtual_server': utils.meta(loadbalancer, 'virtual_server', {})
        }

        status = self.axapi_client.slb.UP
        if not loadbalancer.provisioning_status:
            status = self.axapi_client.slb.DOWN
        config_args['status'] = status

        desc = loadbalancer.description
        if not desc:
            desc = None
        elif str(desc).isspace() or not str(desc):
            desc = ""
        else:
            desc = '"{}"'.format(desc)
        config_args['description'] = desc

        if flavor_data:
            virtual_server_flavor = flavor_data.get('virtual_server')
            if virtual_server_flavor:
                name_exprs = virtual_server_flavor.get('name_expressions')
                if name_exprs:
                    del virtual_server_flavor['name_expressions']
                virtual_server_flavor.update(utils.parse_name_expressions(
                    loadbalancer.name, name_exprs))
                config_args['virtual_server'].update(virtual_server_flavor)

        set_method(loadbalancer.id, loadbalancer.vip.ip_address, **config_args)


class CreateVirtualServerTask(LoadBalancerParent, task.Task):
    """Task to create a virtual server"""

    @axapi_client_decorator
    def execute(self, loadbalancer, vthunder, flavor_data=None):
        try:
            self.set(self.axapi_client.slb.virtual_server.create, loadbalancer, flavor_data)
            LOG.debug("Successfully created load balancer: %s", loadbalancer.id)
        except (acos_errors.ACOSException, exceptions.ConnectionError) as e:
            LOG.exception("Failed to created load balancer: %s", loadbalancer.id)
            raise e

    @axapi_client_decorator
    def revert(self, loadbalancer, vthunder, flavor_data=None, *args, **kwargs):
        try:
            LOG.warning("Reverting creation of load balancer: %s", loadbalancer.id)
            self.axapi_client.slb.virtual_server.delete(loadbalancer.id)
        except exceptions.ConnectionError:
            LOG.exception(
                "Failed to connect A10 Thunder device: %s", vthunder.ip)
        except Exception as e:
            LOG.exception("Failed to revert creation of load balancer: %s due to %s",
                          loadbalancer.id, str(e))


class DeleteVirtualServerTask(task.Task):
    """Task to delete a virtual server"""

    @axapi_client_decorator
    def execute(self, loadbalancer, vthunder):
        if vthunder:
            try:
                self.axapi_client.slb.virtual_server.delete(loadbalancer.id)
                LOG.debug("Successfully deleted load balancer: %s", loadbalancer.id)
            except (acos_errors.ACOSException, exceptions.ConnectionError) as e:
                LOG.exception("Failed to delete load balancer: %s", loadbalancer.id)
                raise e


class UpdateVirtualServerTask(LoadBalancerParent, task.Task):
    """Task to update a virtual server"""

    @axapi_client_decorator
    def execute(self, loadbalancer, vthunder, flavor_data=None):
        try:
            port_list = self.axapi_client.slb.virtual_server.get(
                loadbalancer.id)['virtual-server'].get('port-list')
            self.set(self.axapi_client.slb.virtual_server.replace, loadbalancer,
                     port_list=port_list, flavor_data=flavor_data)
            LOG.debug("Successfully updated load balancer: %s", loadbalancer.id)
        except (acos_errors.ACOSException, exceptions.ConnectionError) as e:
            LOG.exception("Failed to update load balancer: %s", loadbalancer.id)
            raise e
