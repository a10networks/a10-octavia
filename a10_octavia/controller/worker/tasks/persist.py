# Copyright 2014, Doug Wiegley (dougwig), A10 Networks
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

LOG = logging.getLogger(__name__)


class PersistHandler(object):

    def __init__(self, c, pool):
        self.c = c
        self.pool = pool
        self.c_pers = None
        self.s_pers = None

        self.sp_obj_dict = {
            'HTTP_COOKIE': "cookie_persistence",
            'APP_COOKIE': "cookie_persistence",
            'SOURCE_IP': "src_ip_persistence",
        }

        if pool:
            self.name = pool.id

        if pool and pool.session_persistence:
            self.sp = pool.session_persistence
            if self.sp.type == 'HTTP_COOKIE' or self.sp.type == 'APP_COOKIE':
                self.c_pers = self.name
            elif self.sp.type == 'SOURCE_IP':
                self.s_pers = self.name
            else:
                raise Exception("Invalid")
        else:
            self.sp = None

    def c_persistence(self):
        return self.c_pers

    def s_persistence(self):
        return self.s_pers

    def create(self):
        if self.sp is None:
            return
        sp_type = self.sp.type
        if sp_type is not None and sp_type in self.sp_obj_dict:
            try:

                m = getattr(self.c.slb.template, self.sp_obj_dict[sp_type])
                m.create(self.name)
            except acos_errors.Exists:
                pass

    def delete(self):
        if self.sp is None:
            return

        sp_type = self.sp.type
        if sp_type in self.sp_obj_dict.keys():
            try:
                m = getattr(self.c.slb.template, self.sp_obj_dict[sp_type])
                m.delete(self.name)
            except acos_errors.NotExists:
                pass