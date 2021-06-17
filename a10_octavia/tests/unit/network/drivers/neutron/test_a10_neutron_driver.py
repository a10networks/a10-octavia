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

from neutronclient.common import exceptions as neutron_client_exceptions

from oslo_config import cfg
from oslo_config import fixture as oslo_fixture

from octavia.common import clients
from octavia.network import base as network_driver_base
from octavia.network.drivers.neutron import allowed_address_pairs
from octavia.network.drivers.neutron import base as neutron_base
from octavia.tests.common import data_model_helpers as dmh
from octavia.tests.unit import base

from a10_octavia.common import a10constants
from a10_octavia.common import config_options
from a10_octavia.network.drivers.neutron import a10_octavia_neutron
from a10_octavia.tests.common import a10constants as a10_tconstants


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
        self.conf = self.useFixture(oslo_fixture.Config(cfg.CONF))
        self.conf.register_opts(config_options.A10_CONTROLLER_WORKER_OPTS,
                                group=a10_tconstants.A10_CONTROLLER_WORKER_CONF_SECTION)

    def _setup_deallocate_vip_mocks(self):
        self.driver._get_lb_security_group = mock.MagicMock()
        self.driver._get_ports_by_security_group = mock.MagicMock()
        self.driver._get_instance_ports_by_subnet = mock.MagicMock()
        self.driver._remove_security_group = mock.MagicMock()
        self.driver._cleanup_port = mock.MagicMock()
        self.driver._delete_vip_security_group = mock.MagicMock()

    def _generate_lb(self):
        lb = dmh.generate_load_balancer_tree()
        lb.vip.load_balancer = lb
        return lb

    def test_deallocate_vip_one_lb(self):
        lb = self._generate_lb()
        sec_group = {'id': 'sec-grp-1'}
        ports = [{'id': 'instance-port-1'},
                 {'id': 'instance-port-2'},
                 {'id': lb.vip.port_id}]

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
                 {'id': lb.vip.port_id}]

        self._setup_deallocate_vip_mocks()
        get_lb_sec = self.driver._get_lb_security_group
        get_ports_sec = self.driver._get_ports_by_security_group
        rem_sec_grp = self.driver._remove_security_group
        cleanup_port = self.driver._cleanup_port
        delete_sec_grp = self.driver._delete_vip_security_group
        get_lb_sec.return_value = sec_group
        get_ports_sec.return_value = ports

        rem_calls = []
        for port in ports:
            rem_calls.append(mock.call(port, sec_group['id']))
        self.driver.deallocate_vip(lb, 2)
        rem_sec_grp.assert_has_calls(rem_calls, any_order=True)
        cleanup_port.assert_called_once_with(lb.vip.port_id, {'id': lb.vip.port_id})
        delete_sec_grp.assert_called_once_with(sec_group['id'])

    def test_deallocate_vip_sec_grp_disabled(self):
        lb = self._generate_lb()
        vip_port = {'id': lb.vip.port_id}
        ports = [{'id': 'instance-port-1'},
                 {'id': 'instance-port-2'}]

        self.driver.sec_grp_enabled = False
        self._setup_deallocate_vip_mocks()
        self.driver.neutron_client.show_port.return_value = vip_port
        get_ports_subnet = self.driver._get_instance_ports_by_subnet
        cleanup_port = self.driver._cleanup_port
        delete_sec_grp = self.driver._delete_vip_security_group
        get_ports_subnet.return_value = ports

        calls = []
        for port in ports:
            calls.append(mock.call(lb.vip.port_id, port))
        self.driver.deallocate_vip(lb, 1)
        cleanup_port.assert_has_calls(calls, any_order=True)
        delete_sec_grp.assert_not_called()

    def test_deallocate_vip_no_sec_grp_ports(self):
        lb = self._generate_lb()
        sec_group = {'id': 'sec-grp-1'}
        vip_port = {'id': lb.vip.port_id}
        ports = [{'id': 'instance-port-1'},
                 {'id': 'instance-port-2'}]

        self._setup_deallocate_vip_mocks()
        self.driver.neutron_client.show_port.return_value = vip_port
        get_lb_sec = self.driver._get_lb_security_group
        get_ports_sec = self.driver._get_ports_by_security_group
        get_ports_subnet = self.driver._get_instance_ports_by_subnet
        cleanup_port = self.driver._cleanup_port
        delete_sec_grp = self.driver._delete_vip_security_group
        get_lb_sec.return_value = sec_group
        get_ports_sec.return_value = []
        get_ports_subnet.return_value = ports

        calls = []
        for port in ports:
            calls.append(mock.call(lb.vip.port_id, port))
        self.driver.deallocate_vip(lb, 1)
        cleanup_port.assert_has_calls(calls, any_order=True)
        delete_sec_grp.assert_called_once_with(sec_group['id'])

    def test_deallocate_vip_no_sec_group(self):
        lb = self._generate_lb()
        vip_port = {'id': lb.vip.port_id}
        ports = [{'id': 'instance-port-1'},
                 {'id': 'instance-port-2'}]

        self._setup_deallocate_vip_mocks()
        self.driver.neutron_client.show_port.return_value = vip_port
        get_lb_sec = self.driver._get_lb_security_group
        get_ports_subnet = self.driver._get_instance_ports_by_subnet
        cleanup_port = self.driver._cleanup_port
        delete_sec_grp = self.driver._delete_vip_security_group
        rem_sec_grp = self.driver._remove_security_group
        get_lb_sec.return_value = None
        get_ports_subnet.return_value = ports

        self.driver.deallocate_vip(lb, 2)
        cleanup_port.assert_called_with(lb.vip.port_id, vip_port)
        delete_sec_grp.assert_not_called()
        rem_sec_grp.assert_not_called()

    def test_get_ports_by_security_group(self):
        ports = {'ports': [{'id': 'instance-port-1',
                            'security_groups': ['sec-grp-1', 'sec-grp-2'],
                            'device_owner': a10constants.OCTAVIA_OWNER},
                           {'id': 'instance-port-2',
                            'security_groups': ['sec-grp-1', 'sec-grp-2'],
                            'device_owner': a10constants.OCTAVIA_OWNER},
                           {'id': 'vrrp-port-1',
                            'security_groups': ['sec-grp-1'],
                            'device_owner': a10constants.OCTAVIA_OWNER}]}
        self.driver.project_id = 'proj-1'
        self.driver.neutron_client.list_ports.return_value = ports

        actual_ports = self.driver._get_ports_by_security_group('sec-grp-1')
        self.assertEqual(ports['ports'], actual_ports)

    def test_get_ports_by_security_group_empty_ret(self):
        ports = {}
        self.driver.project_id = 'proj-1'
        self.driver.neutron_client.list_ports.return_value = ports

        actual_ports = self.driver._get_ports_by_security_group('sec-grp-1')
        self.assertEqual([], actual_ports)

    def test_get_ports_by_security_group_empty_secgrps(self):
        ports = {'ports': [{'id': 'instance-port-1',
                            'security_groups': [],
                            'device_owner': a10constants.OCTAVIA_OWNER},
                           {'id': 'instance-port-2',
                            'security_groups': [],
                            'device_owner': a10constants.OCTAVIA_OWNER},
                           {'id': 'vrrp-port-1',
                            'security_groups': [],
                            'device_owner': a10constants.OCTAVIA_OWNER}]}
        self.driver.project_id = 'proj-1'
        self.driver.neutron_client.list_ports.return_value = ports

        actual_ports = self.driver._get_ports_by_security_group('sec-grp-1')
        self.assertEqual([], actual_ports)

    def test_get_ports_by_security_group_oct_not_owner(self):
        ports = {'ports': [{'id': 'instance-port-1',
                            'security_groups': ['sec-grp-1', 'sec-grp-2'],
                            'device_owner': 'outis'},
                           {'id': 'instance-port-2',
                            'security_groups': ['sec-grp-1', 'sec-grp-2'],
                            'device_owner': 'outis'},
                           {'id': 'vrrp-port-1',
                            'security_groups': ['sec-grp-1'],
                            'device_owner': 'outis'}]}
        self.driver.project_id = 'proj-1'
        self.driver.neutron_client.list_ports.return_value = ports

        actual_ports = self.driver._get_ports_by_security_group('sec-grp-1')
        self.assertEqual(ports['ports'], actual_ports)

    def test_get_instance_ports_by_subnet(self):
        ports = {'ports': [{'id': 'instance-port-1',
                            'fixed_ips': [{'subnet_id': 'subnet-1'}],
                            'device_owner': a10constants.OCTAVIA_OWNER},
                           {'id': 'instance-port-2',
                            'fixed_ips': [{'subnet_id': 'subnet-1'}],
                            'device_owner': a10constants.OCTAVIA_OWNER},
                           {'id': 'instance-port-3',
                            'fixed_ips': [{'subnet_id': 'subnet-20'}],
                            'device_owner': a10constants.OCTAVIA_OWNER}]}
        self.driver.neutron_client.list_ports.return_value = ports

        actual_ports = self.driver._get_instance_ports_by_subnet('amp-comp-1', 'subnet-1')
        ports['ports'].pop(2)
        self.assertEqual(ports['ports'], actual_ports)

    def test_get_instance_ports_by_subnet_oct_not_owner(self):
        ports = {'ports': [{'id': 'instance-port-1',
                            'fixed_ips': [{'subnet_id': 'subnet-1'}],
                            'device_owner': 'outis'},
                           {'id': 'instance-port-2',
                            'fixed_ips': [{'subnet_id': 'subnet-1'}],
                            'device_owner': 'outis'}]}
        self.driver.neutron_client.list_ports.return_value = ports

        actual_ports = self.driver._get_instance_ports_by_subnet('amp-comp-1', 'subnet-1')
        self.assertEqual([], actual_ports)

    def test_cleanup_port(self):
        vip_port_id = 'vrrp-port-1'
        port = {'id': 'instance-port-1'}
        delete_port = self.driver.neutron_client.delete_port
        self.driver._cleanup_port(vip_port_id, port)
        delete_port.assert_called_with(port['id'])

    def test_cleanup_port_vip_port_deleted(self):
        vip_port_id = 'vrrp-port-1'
        port = {'id': vip_port_id}
        delete_port = self.driver.neutron_client.delete_port
        delete_port.side_effect = neutron_client_exceptions.NotFound

        log_path = "a10_octavia.network.drivers.neutron.a10_octavia_neutron"
        log_message = str("VIP port %s already deleted. Skipping.")
        expected_log = ["DEBUG:{}:{}".format(
            log_path, log_message % vip_port_id)]

        with self.assertLogs(log_path, level='DEBUG') as cm:
            self.driver._cleanup_port(vip_port_id, port)
            delete_port.assert_called_with(vip_port_id)
            self.assertEqual(expected_log, cm.output)

    def test_cleanup_port_not_found(self):
        vip_port_id = 'vrrp-port-1'
        port = {'id': 'instance-port-1'}
        delete_port = self.driver.neutron_client.delete_port
        delete_port.side_effect = neutron_client_exceptions.PortNotFoundClient

        log_path = "a10_octavia.network.drivers.neutron.a10_octavia_neutron"
        log_message = str("Can't deallocate instance port %s because it "
                          "cannot be found in neutron. "
                          "Continuing cleanup.")
        expected_log = ["WARNING:{}:{}".format(
            log_path, log_message % port['id'])]

        with self.assertLogs(log_path, level='WARN') as cm:
            self.driver._cleanup_port(vip_port_id, port)
            delete_port.assert_called_with(port['id'])
            self.assertEqual(expected_log, cm.output)

    def test_cleanup_port_unknown_failure(self):
        vip_port_id = 'vrrp-port-1'
        port = {'id': 'instance-port-1'}
        delete_port = self.driver.neutron_client.delete_port
        delete_port.side_effect = Exception

        log_path = "a10_octavia.network.drivers.neutron.a10_octavia_neutron"
        log_message = ('Error deleting VIP port_id %s from neutron')
        expected_log = ["ERROR:{}:{}".format(
            log_path, log_message % port['id'])]

        expected_error = network_driver_base.DeallocateVIPException
        module_func = self.driver._cleanup_port
        module_args = [vip_port_id, port]
        with self.assertLogs(log_path, level='ERROR') as cm:
            self.assertRaises(expected_error, module_func, *module_args)
            delete_port.assert_called_with(port['id'])
            self.assertIn(expected_log[0], cm.output[0])

    def test_remove_security_group(self):
        sec_grp_id = 'sec-grp-1'
        port = {'id': 'instance-port-1',
                'security_groups': [sec_grp_id, 'sec-grp-2']}
        expected_payload = {'port': {'security_groups': ['sec-grp-2']}}
        update_port = self.driver.neutron_client.update_port

        self.driver._remove_security_group(port, sec_grp_id)
        update_port.assert_called_with(port['id'], expected_payload)

    def test_remove_security_group_not_found(self):
        sec_grp_id = 'sec-grp-1'
        port = {'id': 'instance-port-1',
                'security_groups': [sec_grp_id, 'sec-grp-2']}
        expected_payload = {'port': {'security_groups': ['sec-grp-2']}}
        update_port = self.driver.neutron_client.update_port
        update_port.side_effect = neutron_client_exceptions.PortNotFoundClient

        expected_error = network_driver_base.PortNotFound
        module_func = self.driver._remove_security_group
        module_args = [port, sec_grp_id]

        self.assertRaises(expected_error, module_func, *module_args)
        update_port.assert_called_with(port['id'], expected_payload)

    def test_remove_security_group_unknown_failure(self):
        sec_grp_id = 'sec-grp-1'
        port = {'id': 'instance-port-1',
                'security_groups': [sec_grp_id, 'sec-grp-2']}
        expected_payload = {'port': {'security_groups': ['sec-grp-2']}}
        update_port = self.driver.neutron_client.update_port
        update_port.side_effect = Exception

        expected_error = network_driver_base.NetworkException
        module_func = self.driver._remove_security_group
        module_args = [port, sec_grp_id]

        self.assertRaises(expected_error, module_func, *module_args)
        update_port.assert_called_with(port['id'], expected_payload)
