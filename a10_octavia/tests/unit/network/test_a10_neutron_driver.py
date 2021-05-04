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

from octavia.tests.unit import base


class TestA10NeutronDriver(base.TestCase):

    def setUp(self):
        pass

    def test_deallocate_vip(self):
        pass

    def test_deallocate_vip_no_port(self):
        pass

    def test_deallocate_vip_port_deleted(self):
        pass

    def test_deallocate_vip_no_sec_group(self):
        pass

    def test_deallocate_vip_when_delete_port_fails(self):
        pass

    def test_deallocate_vip_when_secgrp_has_allocated_port(self):
        pass

    def test_deallocate_vip_when_port_no_found(self):
        pass

    def test_deallocate_vip_when_port_not_found_for_update(self):
        pass

    def test_deallocate_vip_when_port_not_owned_by_octavia(self):
        pass

    def test_deallocate_vip_when_vip_port_not_found(self):
        pass

    def test_get_ports_by_security_group(self):
        pass

    def test_get_ports_by_security_group_empty_ret(self):
        pass

    def test_get_ports_by_security_group_empty_secgrps(self):
        pass

    def test_get_instance_ports_by_subnet(self):
        pass

    def test_cleanup_port(self):
        pass

    def test_cleanup_port_error_vip_id_equal(self):
        pass
