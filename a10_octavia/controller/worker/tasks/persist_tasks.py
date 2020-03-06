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


import logging

import acos_client.errors as acos_errors
from a10_octavia.controller.worker.tasks.common import BaseVThunderTask
from a10_octavia.controller.worker.tasks import utils


LOG = logging.getLogger(__name__)
SP_OBJ_DICT = {
    'HTTP_COOKIE': "cookie_persistence",
    'APP_COOKIE': "cookie_persistence",
    'SOURCE_IP': "src_ip_persistence",
}


class HandleSessionPersistenceDelta(BaseVThunderTask):

    def execute(self, vthunder, pool):

        c_pers, s_pers, sp = None, None, None

        if pool.session_persistence:
            sp = pool.session_persistence
            c_pers, s_pers = utils.get_sess_pers_templates(pool)

            if sp and sp.type and sp.type in SP_OBJ_DICT:
                axapi_client = self.client_factory(vthunder)
                sp_template = getattr(
                    axapi_client.slb.template, SP_OBJ_DICT[sp.type])

                # Remove existing persistence template if any
                try:
                    sp_template.delete(pool.id)
                except acos_errors.NotFound:
                    pass

                try:
                    if sp.cookie_name:
                        sp_template.create(pool.id, cookie_name=sp.cookie_name)
                    else:
                        sp_template.create(pool.id)
                except acos_errors.Exists:
                    pass
                except Exception:
                    LOG.exception(
                        "Failed to create session persistence for pool: %s", pool.id)
                    raise

    def revert(self, vthunder, pool, *args, **kwargs):
        axapi_client = self.client_factory(vthunder)
        sp_template = getattr(
            axapi_client.slb.template, SP_OBJ_DICT[sp.type])
        try:
            sp_template.delete(pool.id)
        except acos_errors.NotFound:
            pass


class DeleteSessionPersistence(BaseVThunderTask):

    def execute(self, vthunder, pool):
        client = self.client_factory(vthunder)
        if pool.session_persistence:
            for sp_type in ['cookie_persistence', 'src_ip_persistence']:
                try:
                    sp_template = getattr(client.slb.template, sp_type)
                    sp_template.delete(pool.id)
                except acos_errors.NotFound:
                    pass
