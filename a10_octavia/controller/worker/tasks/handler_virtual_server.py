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


from taskflow import task

from octavia.controller.worker import task_utils as task_utilities
from octavia.common import constants
import acos_client
from octavia.amphorae.driver_exceptions import exceptions as driver_except
import time
from oslo_log import log as logging
from oslo_config import cfg
from a10_octavia.common import openstack_mappings
from a10_octavia.controller.worker.tasks.policy import PolicyUtil
from a10_octavia.controller.worker.tasks import persist
from a10_octavia.controller.worker.tasks.common import BaseVThunderTask
import json

CONF = cfg.CONF
LOG = logging.getLogger(__name__)

class LoadBalancerParent:

    def set(self, set_method, loadbalancer_id, loadbalancer, vthunder):
        conf_templates = self.readConf('SLB', 'template_virtual_server')
        virtual_server_templates = {}
        try:
            if conf_templates is not None:
                conf_templates = conf_templates.strip('"')
                virtual_server_templates['template-server'] = conf_templates
        except:
            virtual_server_templates = None

        try:
            c = self.client_factory(vthunder)
            status = c.slb.UP
            if not loadbalancer.provisioning_status:
                status = c.slb.DOWN
            vip_meta = self.meta(loadbalancer, 'virtual_server', {})
            arp_disable = self.readConf('SLB', 'arp_disable')
            if isinstance(arp_disable, str):
                arp_disable = json.loads(arp_disable.lower())
            else:
                arp_disable = False
            vrid = self.readConf('SLB', 'default_virtual_server_vrid')
            if vrid is not None:
                vrid = int(vrid)
            r = set_method(
                loadbalancer_id,
                loadbalancer.vip.ip_address,
                arp_disable=arp_disable,
                status=status, vrid=vrid,
                virtual_server_templates=virtual_server_templates,
                axapi_body=vip_meta)
            status = {'loadbalancers': [{"id": loadbalancer_id,
                      "provisioning_status": constants.ACTIVE}]}
        except Exception as e:
            r = str(e)
            LOG.info(r)
            status = {'loadbalancers': [{"id": loadbalancer_id,
            "provisioning_status": constants.ERROR}]}
        LOG.info(str(status))
        return status

    def revert(self, loadbalancer_id, *args, **kwargs):
        pass


class CreateVitualServerTask(BaseVThunderTask, LoadBalancerParent):
    """Task to create a virtual server in vthunder device."""

    def execute(self, loadbalancer_id, loadbalancer, vthunder):
  
        c = self.client_factory(vthunder)          
        status = LoadBalancerParent.set(c.slb.virtual_server.create,  loadbalancer_id, loadbalancer, vthunder)
        return status
        '''conf_templates = self.readConf('SLB', 'template_virtual_server')
        virtual_server_templates = {}
        try:
            if conf_templates is not None:
                conf_templates = conf_templates.strip('"')
                virtual_server_templates['template-server'] = conf_templates
        except:
            virtual_server_templates = None

        try:
            c = self.client_factory(vthunder)
            status = c.slb.UP
            if not loadbalancer.provisioning_status:
                status = c.slb.DOWN
            vip_meta = self.meta(loadbalancer, 'virtual_server', {})
            arp_disable = self.readConf('SLB', 'arp_disable')
            if isinstance(arp_disable, str):
                arp_disable = json.loads(arp_disable.lower())
            else:
                arp_disable = False
            vrid = self.readConf('SLB', 'default_virtual_server_vrid')
            if vrid is not None:
                vrid = int(vrid)
            r = c.slb.virtual_server.create(
                loadbalancer_id,
                loadbalancer.vip.ip_address,
                arp_disable=arp_disable,
                status=status, vrid=vrid,
                virtual_server_templates=virtual_server_templates,
                axapi_body=vip_meta)
            status = {'loadbalancers': [{"id": loadbalancer_id,
                      "provisioning_status": constants.ACTIVE}]}
        except Exception as e:
            r = str(e)
            LOG.info(r)
            status = {'loadbalancers': [{"id": loadbalancer_id,
                      "provisioning_status": constants.ERROR}]}
        LOG.info(str(status))
        return status

    def revert(self, loadbalancer_id, *args, **kwargs):
        pass'''


class DeleteVitualServerTask(BaseVThunderTask):
    """Task to delete a virtual server in vthunder device."""

    def execute(self, loadbalancer, vthunder):
        loadbalancer_id = loadbalancer.id
        try:
            c = self.client_factory(vthunder)
            r = c.slb.virtual_server.delete(loadbalancer_id)
            status = {'loadbalancers': [{"id": loadbalancer_id,
                      "provisioning_status": constants.DELETED}]}
        except Exception as e:
            r = str(e)
            LOG.info(r)
            status = {'loadbalancers': [{"id": loadbalancer_id,
                      "provisioning_status": constants.ERROR}]}
        LOG.info(str(status))
        return status

    def revert(self, loadbalancer, *args, **kwargs):
        pass


class UpdateVitualServerTask(BaseVThunderTask):
    """Task to update a virtual server in vthunder device."""

    def execute(self, loadbalancer, vthunder):
        status = LoadBalancerParent.set(c.slb.virtual_server.update,  loadbalancer_id, loadbalancer, vthunder)
        return status
        
        '''loadbalancer_id = loadbalancer.id
        conf_templates = self.readConf('SLB', 'template_virtual_server')
        virtual_server_templates = {}
        try:
            if conf_templates is not None:
                conf_templates = conf_templates.strip('"')
                virtual_server_templates['template-server'] = conf_templates
        except:
            virtual_server_templates = None
        try:
            axapi_version = acos_client.AXAPI_21 if vthunder.axapi_version == 21 else acos_client.AXAPI_30
            c = acos_client.Client(vthunder.ip_address, axapi_version, vthunder.username,
                                   vthunder.password)
            status = c.slb.UP
            # if not loadbalancer.provisioning_status:
            if not loadbalancer.enabled:
                status = c.slb.DOWN
            vip_meta = self.meta(loadbalancer, 'virtual_server', {})
            arp_disable = self.readConf('SLB', 'arp_disable')
            if isinstance(arp_disable, str):
                arp_disable = json.loads(arp_disable.lower())
            else:
                arp_disable = False
            vrid = self.readConf('SLB', 'default_virtual_server_vrid')
            if vrid is not None:
                vrid = int(vrid)

            r = c.slb.virtual_server.update(
                loadbalancer_id,
                loadbalancer.vip.ip_address,
                arp_disable=arp_disable,
                status=status, vrid=vrid,
                virtual_server_templates=virtual_server_templates,
                axapi_body=vip_meta)
            status = {'loadbalancers': [{"id": loadbalancer_id,
                      "provisioning_status": constants.ACTIVE}]}
            # LOG.info("vthunder details:" + str(vthunder))
        except Exception as e:
            r = str(e)
            LOG.info(r)
            status = {'loadbalancers': [{"id": loadbalancer_id,
                      "provisioning_status": constants.ERROR}]}
        LOG.info(str(status))
        return status'''
