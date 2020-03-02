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

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class LoadBalancerParent(object):

    def set(self, set_method, loadbalancer, vthunder):
        c = self.client_factory(vthunder)
        status = c.slb.UP
        if not loadbalancer.provisioning_status:
            status = c.slb.DOWN
        vip_meta = self.meta(loadbalancer, 'virtual_server', {})
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


class CreateVirtualServerTask(LoadBalancerParent, BaseVThunderTask):

    """ Task to create a virtual server """

    def execute(self, loadbalancer, vthunder):
        c = self.client_factory(vthunder)
        self.set(c.slb.virtual_server.create, loadbalancer, vthunder)

    def revert(self, loadbalancer, vthunder, *args, **kwargs):
        c = self.client_factory(vthunder)
        try:
            c.slb.virtual_server.delete(loadbalancer.id)
        except Exception as e:
            LOG.exception("Failed to revert create load balancer: %s", str(e))


class DeleteVirtualServerTask(BaseVThunderTask):

    """ Task to delete a virtual server """

    def execute(self, loadbalancer, vthunder):
        c = self.client_factory(vthunder)
        try:
            c.slb.virtual_server.delete(loadbalancer.id)
        except Exception as e:
            LOG.warning("Failed to delete load balancer: %s", str(e))


class UpdateVirtualServerTask(LoadBalancerParent, BaseVThunderTask):

    """ Task to update a virtual server """

    def execute(self, loadbalancer, vthunder):
        c = self.client_factory(vthunder)
        status = self.set(c.slb.virtual_server.update,
                          loadbalancer,
                          vthunder)

    def revert(self, loadbalancer, vthunder, *args, **kwargs):
        LOG.warning(
            "Failed to revert update load balancer: %s ", loadbalancer.id)
