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

from a10_octavia.controller.worker.tasks.decorators import axapi_client_decorator
from a10_octavia.controller.worker.tasks import utils


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class LoadBalancerParent(object):

    def set(self, set_method, loadbalancer):
        status = self.axapi_client.slb.UP
        if not loadbalancer.provisioning_status:
            status = self.axapi_client.slb.DOWN
        vip_meta = utils.meta(loadbalancer, 'virtual_server', {})
        arp_disable = CONF.slb.arp_disable
        vrid = CONF.slb.default_virtual_server_vrid

        try:
            set_method(
                loadbalancer.id,
                loadbalancer.vip.ip_address,
                arp_disable=arp_disable,
                status=status, vrid=vrid,
                axapi_body=vip_meta)
            LOG.debug("LoadBalancer created/updated succesfully: %s",
                      loadbalancer.id)
        except Exception as e:
            LOG.exception("Failed to create/update load balancer: %s", str(e))
            raise


class CreateVirtualServerTask(LoadBalancerParent, task.Task):
    """Task to create a virtual server"""

    @axapi_client_decorator
    def execute(self, loadbalancer, vthunder):
        self.set(self.axapi_client.slb.virtual_server.create, loadbalancer)

    @axapi_client_decorator
    def revert(self, loadbalancer, vthunder, *args, **kwargs):
        try:
            self.axapi_client.slb.virtual_server.delete(loadbalancer.id)
        except Exception as e:
            LOG.exception("Failed to revert create load balancer: %s", str(e))


class DeleteVirtualServerTask(task.Task):
    """Task to delete a virtual server"""

    @axapi_client_decorator
    def execute(self, loadbalancer, vthunder):
        try:
            self.axapi_client.slb.virtual_server.delete(loadbalancer.id)
        except Exception as e:
            LOG.warning("Failed to delete load balancer: %s", str(e))


class UpdateVirtualServerTask(LoadBalancerParent, task.Task):
    """Task to update a virtual server"""

    @axapi_client_decorator
    def execute(self, loadbalancer, vthunder):
        self.set(self.axapi_client.slb.virtual_server.update, loadbalancer)
