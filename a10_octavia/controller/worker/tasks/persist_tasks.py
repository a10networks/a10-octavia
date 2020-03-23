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

import logging

import acos_client.errors as acos_errors
from taskflow import task

from a10_octavia.common.a10constants import PERS_TYPE
from a10_octavia.common.a10constants import SP_OBJ_DICT
from a10_octavia.controller.worker.tasks.decorators import axapi_client_decorator

LOG = logging.getLogger(__name__)


class HandleSessionPersistenceDelta(task.Task):
    """Task to handle session persistence template delta for pool"""

    @axapi_client_decorator
    def execute(self, vthunder, pool):
        sess_pers = pool.session_persistence
        if sess_pers and sess_pers.type in SP_OBJ_DICT:

            # Remove existing persistence template if any
            for sp_type in PERS_TYPE:
                try:
                    sp_template = getattr(self.axapi_client.slb.template, sp_type)
                    sp_template.delete(pool.id)
                except acos_errors.NotFound:
                    pass

            sp_template = getattr(
                self.axapi_client.slb.template, SP_OBJ_DICT[sess_pers.type])

            try:
                if sess_pers.cookie_name:
                    sp_template.create(pool.id,
                                       cookie_name=sess_pers.cookie_name)
                else:
                    sp_template.create(pool.id)
            except acos_errors.Exists:
                pass
            except Exception:
                LOG.exception(
                    "Failed to create session persistence for pool: %s", pool.id)
                raise

    @axapi_client_decorator
    def revert(self, vthunder, pool, *args, **kwargs):
        sp_template = getattr(
            self.axapi_client.slb.template, SP_OBJ_DICT[pool.session_persistence.type])
        try:
            sp_template.delete(pool.id)
        except acos_errors.NotFound:
            pass


class DeleteSessionPersistence(task.Task):
    """Task to delete session persistence templates"""

    @axapi_client_decorator
    def execute(self, vthunder, pool):
        if pool.session_persistence:
            for sp_type in PERS_TYPE:
                try:
                    sp_template = getattr(self.axapi_client.slb.template, sp_type)
                    sp_template.delete(pool.id)
                except acos_errors.NotFound:
                    pass
                except Exception as e:
                    LOG.warning(
                        "Failed to delete session persistence: %s", str(e))
