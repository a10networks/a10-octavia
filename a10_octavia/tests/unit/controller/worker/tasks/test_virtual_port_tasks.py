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

import imp
try:
    from unittest import mock
except ImportError:
    import mock

from octavia.common import data_models as o_data_models

from oslo_config import cfg

from a10_octavia.common.data_models import VThunder
import a10_octavia.controller.worker.tasks.virtual_port_tasks as task
from a10_octavia.tests.common import a10constants
from a10_octavia.tests.unit.base import BaseTaskTestCase

VTHUNDER = VThunder()
LB = o_data_models.LoadBalancer(id=a10constants.MOCK_LOAD_BALANCER_ID)


class TestHandlerVirtualPortTasks(BaseTaskTestCase):

    def setUp(self):
        super(TestHandlerVirtualPortTasks, self).setUp()
        imp.reload(task)

    def _mock_conf(self, use_rcv_hop_for_resp, no_dest_nat):
        conf = cfg.CONF
        conf.listener = mock.Mock()
        conf.listener.use_rcv_hop_for_resp = use_rcv_hop_for_resp
        conf.listener.no_dest_nat = no_dest_nat
        return conf

    def _mock_listener(self, protocol, conn_limit):
        listener = o_data_models.Listener(id=a10constants.MOCK_LISTENER_ID)
        listener.protocol = protocol
        listener.connection_limit = conn_limit
        return listener

    def test_create_virtual_port_task(self):
        self._mock_conf(True, False)
        listener = self._mock_listener('HTTP', 1000)

        client_mock = mock.Mock()
        listener_task = task.ListenersCreate()
        listener_task.axapi_client = client_mock
        listener_task.execute(LB, [listener], VTHUNDER)
        args, kwargs = client_mock.slb.virtual_server.vport.create.call_args
        self.assertTrue(kwargs.get('use_rcv_hop'))
        self.assertEqual(kwargs.get('conn_limit'), 1000)

    def test_update_virtual_port_task(self):
        self._mock_conf(False, False)
        listener = self._mock_listener('HTTP', 1000)

        client_mock = mock.Mock()
        listener_task = task.ListenersUpdate()
        listener_task.axapi_client = client_mock
        listener_task.execute(LB, [listener], VTHUNDER)
        args, kwargs = client_mock.slb.virtual_server.vport.update.call_args
        self.assertFalse(kwargs.get('use_rcv_hop'))
        self.assertEqual(kwargs.get('conn_limit'), 1000)
