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

try:
    import mock
except ImportError:
    from unittest import mock

from octavia.common import clients
from octavia.network.drivers.neutron import base as neutron_base
from octavia.network.drivers.neutron import allowed_address_pairs
from octavia.tests.unit import base
from octavia.tests.common import data_model_helpers as dmh

from a10_octavia.network.drivers.neutron import a10_octavia_neutron


class TestA10NeutronDriver(base.TestCase):

    def setUp(self):
        super(TestA10NeutronDriver, self).setUp()
        with mock.patch('octavia.common.clients.neutron_client.Client',
                        autospec=True) as neutron_client:
            with mock.patch('stevedore.driver.DriverManager.driver',
                            autospec=True):
                client = neutron_client(clients.NEUTRON_VERSION)
                client.list_extensions.return_value = {
                    'extensions': [
                        {'alias': allowed_address_pairs.AAP_EXT_ALIAS},
                        {'alias': neutron_base.SEC_GRP_EXT_ALIAS}
                    ]
                }
                self.k_session = mock.patch(
                    'keystoneauth1.session.Session').start()
                self.driver = a10_octavia_neutron.A10OctaviaNeutronDriver()

    def _setup_deallocate_vip_mocks(self):
        self.driver._get_lb_security_group = mock.Mock()
        self.driver._get_ports_by_security_group = mock.Mock()
        self.driver._get_instance_ports_by_subnet = mock.Mock()
        self.driver._remove_security_group = mock.Mock()
        self.driver._cleanup_port = mock.Mock()
        self.driver._delete_vip_security_group = mock.Mock()


    def _generate_lb(self):
        lb = dmh.generate_load_balancer_tree()
        lb.vip.load_balancer = lb
        vip = lb.vip
        return lb

    def test_deallocate_vip_one_lb(self):
        lb = self._generate_lb()
        sec_group = {'id': 'sec-grp-1'}
        ports = [{'id': 'instance-port-1'},
                 {'id': 'instance-port-2'},
                 {'id': 'vrrp-port-1'}]

        self._setup_deallocate_vip_mocks()
        get_lb_sec = self.driver._get_lb_security_group
        get_ports_sec = self.driver._get_ports_by_security_group
        cleanup_port = self.driver._cleanup_port
        delete_sec_grp = self.driver._delete_vip_security_group
        get_lb_sec.return_value = sec_group
        get_ports_sec.return_value = ports

        calls = []
        for port in ports:
            calls.append(mock.call(lb.vip.port_id, port))
        self.driver.deallocate_vip(lb, 1)
        cleanup_port.assert_has_calls(calls, any_order=True)
        delete_sec_grp.assert_called_once_with(sec_group['id'])

    def test_deallocate_vip_multi_lb(self):
        lb = self._generate_lb()
        sec_group = {'id': 'sec-grp-1'}
        ports = [{'id': 'instance-port-1'},
                 {'id': 'instance-port-2'},
                 {'id': 'vrrp-port-1'}]

        self._setup_deallocate_vip_mocks()
        get_lb_sec = self.driver._get_lb_security_group
        get_ports_sec = self.driver._get_ports_by_security_group
        rem_sec_grp = self.driver._remove_security_group
        cleanup_port = self.driver._cleanup_port
        delete_sec_grp = self.driver._delete_vip_security_group
        get_lb_sec.return_value = sec_group
        get_ports_sec.return_value = ports

        calls = []
        for port in ports:
            calls.append(mock.call(port, sec_group['id']))
        self.driver.deallocate_vip(lb, 2)
        rem_sec_grp.assert_has_calls(calls, any_order=True)
        cleanup_port.assert_called_once_with('vrrp-port-1', {'id': 'vrrp-port-1'})
        delete_sec_grp.assert_called_once_with(sec_group['id'])

    def test_deallocate_vip_sec_grp_disabled(self):
        lb = self._generate_lb()
        sec_group = {'id': 'sec-grp-1'}
        ports = [{'id': 'instance-port-1'},
                 {'id': 'instance-port-2'},
                 {'id': 'vrrp-port-1'}]

        #self.drsiver.sec_grp_enabled = False
        self._setup_deallocate_vip_mocks()
        get_lb_sec = self.driver._get_lb_security_group
        get_ports_sec = self.driver._get_ports_by_security_group
        cleanup_port = self.driver._cleanup_port
        delete_sec_grp = self.driver._delete_vip_security_group
        get_lb_sec.return_value = sec_group
        get_ports_sec.return_value = ports

        calls = []
        for port in ports:
            calls.append(mock.call(lb.vip.port_id, port))
        self.driver.deallocate_vip(lb, 1)
        cleanup_port.assert_has_calls(calls, any_order=True)
        delete_sec_grp.assert_called_once_with(sec_group['id'])

    def test_deallocate_vip_no_sec_grp_ports(self):
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
