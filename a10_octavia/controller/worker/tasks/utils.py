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


def get_sess_pers_templates(pool):
    c_pers, s_pers, sp = None, None, None
    if pool and pool.session_persistence:
        sp = pool.session_persistence
        if sp.type == 'HTTP_COOKIE' or sp.type == 'APP_COOKIE':
            c_pers = pool.id
        elif sp.type == 'SOURCE_IP':
            s_pers = pool.id
    return c_pers, s_pers
