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

import json

from oslo_config import cfg
from oslo_log import log as logging
from taskflow import task

from octavia.controller.worker import task_utils as task_utilities

import acos_client

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class BaseVThunderTask(task.Task):

    def __init__(self, **kwargs):
        self.task_utils = task_utilities.TaskUtils()
        super(BaseVThunderTask, self).__init__(**kwargs)

    def client_factory(self, vthunder):
        c = acos_client.Client(
            vthunder.ip_address,
            str(vthunder.axapi_version),
            vthunder.username,
            vthunder.password,
            timeout=30)
        return c

    def meta(self, lbaas_obj, key, default):
        if isinstance(lbaas_obj, dict):
            m = lbaas_obj.get('a10_meta', '{}')
        elif hasattr(lbaas_obj, 'a10_meta'):
            m = lbaas_obj.a10_meta
        else:
            return default
        try:
            d = json.loads(m)
        except Exception:
            return default
        return d.get(key, default)
