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


from a10_octavia.db import models
from datetime import datetime

models.VThunder.create_and_save(amphora_id_id='112', device_name='somename',
                                ip_address='192.168.2.3', username='username',
                                password='password', axapi_version=30,
                                undercloud=True, loadbalancer_id='lbid',
                                status='ACTIVE', updated_at=datetime.utcnow(),
                                created_at=datetime.utcnow(),
                                last_udp_update=datetime.utcnow(),
                                db_session=None)
