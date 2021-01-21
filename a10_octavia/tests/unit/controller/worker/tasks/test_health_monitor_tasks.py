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

import copy
import imp
try:
    from unittest import mock
except ImportError:
    import mock

from octavia.common import data_models as o_data_models
from oslo_config import cfg
from oslo_config import fixture as oslo_fixture

from a10_octavia.common import config_options
from a10_octavia.common.data_models import VThunder
from a10_octavia.controller.worker.tasks import health_monitor_tasks as task
from a10_octavia.controller.worker.tasks import utils
from a10_octavia.tests.common import a10constants
from a10_octavia.tests.unit.base import BaseTaskTestCase

VTHUNDER = VThunder()
HM = o_data_models.HealthMonitor(id=a10constants.MOCK_HM_ID,
                                 type='TCP',
                                 delay=7,
                                 timeout=3,
                                 rise_threshold=8,
                                 http_method='GET')
ARGS = utils.meta(HM, 'hm', {})
LISTENERS = [o_data_models.Listener(id=a10constants.MOCK_LISTENER_ID, protocol_port=mock.ANY)]

FLAVOR_ARGS = {
    'monitor': {
        'retry': 5,
        'method': {
            'http': {'http_response_code': '201'}
        },
    }
}

FLAVOR_WITH_REGEX_ARGS = {
    'monitor': {
        'retry': 5,
        'method': {
            'http': {'http_host': 'my.test.com'}
        },
        'timeout': 8
    }
}


class TestHandlerHealthMonitorTasks(BaseTaskTestCase):

    def setUp(self):
        super(TestHandlerHealthMonitorTasks, self).setUp()
        imp.reload(task)
        self.conf = self.useFixture(oslo_fixture.Config(cfg.CONF))
        self.conf.register_opts(config_options.A10_HEALTH_MONITOR_OPTS,
                                group=a10constants.HEALTH_MONITOR_SECTION)
        self.client_mock = mock.Mock()

    def tearDown(self):
        super(TestHandlerHealthMonitorTasks, self).tearDown()

    def test_health_monitor_create_task(self):
        mock_hm = task.CreateAndAssociateHealthMonitor()
        mock_hm.axapi_client = self.client_mock
        mock_hm.execute(LISTENERS, HM, VTHUNDER)
        self.client_mock.slb.hm.create.assert_called_with(a10constants.MOCK_HM_ID,
                                                          self.client_mock.slb.hm.TCP,
                                                          HM.delay, HM.timeout,
                                                          HM.rise_threshold, method=None,
                                                          port=mock.ANY, url=None,
                                                          expect_code=None, post_data=None,
                                                          **ARGS)
        self.conf.config(group=a10constants.HEALTH_MONITOR_SECTION,
                         post_data='abc=1')
        mock_hm.execute(LISTENERS, HM, VTHUNDER)
        self.client_mock.slb.hm.create.assert_called_with(a10constants.MOCK_HM_ID,
                                                          self.client_mock.slb.hm.TCP,
                                                          HM.delay, HM.timeout,
                                                          HM.rise_threshold, method=None,
                                                          port=mock.ANY, url=None,
                                                          expect_code=None, post_data='abc=1',
                                                          **ARGS)

    def test_health_monitor_create_with_flavor_task(self):
        flavor = {
            "health_monitor": {
                "retry": 5,
                "method": {
                    "http": {
                        "http_response_code": "201"
                    }
                }
            }
        }
        mock_hm = task.CreateAndAssociateHealthMonitor()
        mock_hm.axapi_client = self.client_mock
        HM.delay = 30
        HM.name = "hm1"
        mock_hm.execute(LISTENERS, HM, VTHUNDER, flavor)
        self.client_mock.slb.hm.create.assert_called_with(a10constants.MOCK_HM_ID,
                                                          self.client_mock.slb.hm.TCP,
                                                          HM.delay, HM.timeout,
                                                          HM.rise_threshold, method=None,
                                                          port=mock.ANY, url=None, post_data=None,
                                                          expect_code=None, **FLAVOR_ARGS)

    def test_health_monitor_create_with_flavor_and_config(self):
        flavor = {
            "health_monitor": {
                "retry": 5,
                "method": {
                    "http": {
                        "http_response_code": "201"
                    }
                }
            }
        }
        mock_hm = task.CreateAndAssociateHealthMonitor()
        mock_hm.axapi_client = self.client_mock
        HM.delay = 30
        HM.name = "hm1"
        self.conf.config(group=a10constants.HEALTH_MONITOR_SECTION, post_data='abc=1')
        mock_hm.execute(LISTENERS, HM, VTHUNDER, flavor)
        self.client_mock.slb.hm.create.assert_called_with(a10constants.MOCK_HM_ID,
                                                          self.client_mock.slb.hm.TCP,
                                                          HM.delay, HM.timeout,
                                                          HM.rise_threshold, method=None,
                                                          port=mock.ANY, url=None,
                                                          post_data='abc=1',
                                                          expect_code=None, **FLAVOR_ARGS)

    def test_health_monitor_create_with_flavor_regex_task(self):
        flavor = {
            "health_monitor": {
                "retry": 5,
                "method": {
                    "http": {
                        "http_response_code": "201"
                    }
                },
                "name_expressions": [
                    {
                        "regex": "hm1",
                        "json": {
                            "timeout": 8,
                            "method": {
                                "http": {
                                    "http_host": "my.test.com"
                                }
                            }
                        }
                    }
                ]
            }
        }
        mock_hm = task.CreateAndAssociateHealthMonitor()
        mock_hm.axapi_client = self.client_mock
        HM.delay = 30
        HM.name = "hm1"
        mock_hm.execute(LISTENERS, HM, VTHUNDER, flavor)
        self.client_mock.slb.hm.create.assert_called_with(a10constants.MOCK_HM_ID,
                                                          self.client_mock.slb.hm.TCP,
                                                          HM.delay, HM.timeout,
                                                          HM.rise_threshold, method=None,
                                                          port=mock.ANY, url=None,
                                                          expect_code=None, post_data=None,
                                                          **FLAVOR_WITH_REGEX_ARGS)

    def test_health_monitor_create_with_regex_overwrite_flavor_task(self):
        flavor = {
            "health_monitor": {
                "retry": 5,
                "timeout": 90,
                "method": {
                    "http": {
                        "http_response_code": "201"
                    }
                },
                "name_expressions": [
                    {
                        "regex": "hm1",
                        "json": {
                            "timeout": 8,
                            "method": {
                                "http": {
                                    "http_host": "my.test.com"
                                }
                            }
                        }
                    }
                ]
            }
        }
        mock_hm = task.CreateAndAssociateHealthMonitor()
        mock_hm.axapi_client = self.client_mock
        HM.delay = 30
        HM.name = "hm1"
        mock_hm.execute(LISTENERS, HM, VTHUNDER, flavor)
        self.client_mock.slb.hm.create.assert_called_with(a10constants.MOCK_HM_ID,
                                                          self.client_mock.slb.hm.TCP,
                                                          HM.delay, HM.timeout,
                                                          HM.rise_threshold, method=None,
                                                          port=mock.ANY, url=None,
                                                          expect_code=None, post_data=None,
                                                          **FLAVOR_WITH_REGEX_ARGS)

    def test_health_monitor_update_task(self):
        mock_hm = task.UpdateHealthMonitor()
        mock_hm.axapi_client = self.client_mock
        update_dict = {'delay': '10'}
        hm = copy.deepcopy(HM)
        mock_hm.execute(LISTENERS, hm, VTHUNDER, update_dict)
        self.client_mock.slb.hm.update.assert_called_with(a10constants.MOCK_HM_ID,
                                                          self.client_mock.slb.hm.TCP,
                                                          hm.delay, hm.timeout,
                                                          hm.rise_threshold, method=None,
                                                          port=mock.ANY, url=None,
                                                          expect_code=None, post_data=None,
                                                          **ARGS)
        self.conf.config(group=a10constants.HEALTH_MONITOR_SECTION,
                         post_data='abc=1')
        mock_hm.execute(LISTENERS, hm, VTHUNDER, update_dict)
        self.client_mock.slb.hm.update.assert_called_with(a10constants.MOCK_HM_ID,
                                                          self.client_mock.slb.hm.TCP,
                                                          hm.delay, hm.timeout,
                                                          hm.rise_threshold, method=None,
                                                          port=mock.ANY, url=None,
                                                          expect_code=None, post_data='abc=1',
                                                          **ARGS)

    def test_health_monitor_update_with_flavor_and_config_task(self):
        flavor = {
            "health_monitor": {
                "retry": 5,
                "method": {
                    "http": {
                        "http_response_code": "201"
                    }
                }
            }
        }
        update_dict = {}
        mock_hm = task.UpdateHealthMonitor()
        mock_hm.axapi_client = self.client_mock
        HM.delay = 30
        HM.name = "hm1"
        self.conf.config(group=a10constants.HEALTH_MONITOR_SECTION, post_data='abc=1')
        mock_hm.execute(LISTENERS, HM, VTHUNDER, update_dict, flavor=flavor)
        self.client_mock.slb.hm.update.assert_called_with(a10constants.MOCK_HM_ID,
                                                          self.client_mock.slb.hm.TCP,
                                                          HM.delay, HM.timeout,
                                                          HM.rise_threshold, method=None,
                                                          port=mock.ANY, url=None,
                                                          post_data='abc=1',
                                                          expect_code=None, **FLAVOR_ARGS)

    def test_health_monitor_update_with_flavor_task(self):
        flavor = {
            "health_monitor": {
                "retry": 5,
                "method": {
                    "http": {
                        "http_response_code": "201"
                    }
                }
            }
        }
        update_dict = {}
        mock_hm = task.UpdateHealthMonitor()
        mock_hm.axapi_client = self.client_mock
        HM.delay = 30
        HM.name = "hm1"
        mock_hm.execute(LISTENERS, HM, VTHUNDER, update_dict, flavor=flavor)
        self.client_mock.slb.hm.update.assert_called_with(a10constants.MOCK_HM_ID,
                                                          self.client_mock.slb.hm.TCP,
                                                          HM.delay, HM.timeout,
                                                          HM.rise_threshold, method=None,
                                                          port=mock.ANY, url=None, post_data=None,
                                                          expect_code=None, **FLAVOR_ARGS)

    def test_health_monitor_update_with_flavor_regex_task(self):
        flavor = {
            "health_monitor": {
                "retry": 5,
                "method": {
                    "http": {
                        "http_response_code": "201"
                    }
                },
                "name_expressions": [
                    {
                        "regex": "hm1",
                        "json": {
                            "timeout": 8,
                            "method": {
                                "http": {
                                    "http_host": "my.test.com"
                                }
                            }
                        }
                    }
                ]
            }
        }
        update_dict = {}
        mock_hm = task.UpdateHealthMonitor()
        mock_hm.axapi_client = self.client_mock
        HM.delay = 30
        HM.name = "hm1"
        mock_hm.execute(LISTENERS, HM, VTHUNDER, update_dict, flavor=flavor)
        self.client_mock.slb.hm.update.assert_called_with(a10constants.MOCK_HM_ID,
                                                          self.client_mock.slb.hm.TCP,
                                                          HM.delay, HM.timeout,
                                                          HM.rise_threshold, method=None,
                                                          port=mock.ANY, url=None,
                                                          expect_code=None, post_data=None,
                                                          **FLAVOR_WITH_REGEX_ARGS)

    def test_health_monitor_update_with_regex_overwrite_flavor_task(self):
        flavor = {
            "health_monitor": {
                "retry": 5,
                "timeout": 90,
                "method": {
                    "http": {
                        "http_response_code": "201"
                    }
                },
                "name_expressions": [
                    {
                        "regex": "hm1",
                        "json": {
                            "timeout": 8,
                            "method": {
                                "http": {
                                    "http_host": "my.test.com"
                                }
                            }
                        }
                    }
                ]
            }
        }
        update_dict = {}
        mock_hm = task.UpdateHealthMonitor()
        mock_hm.axapi_client = self.client_mock
        HM.delay = 30
        HM.name = "hm1"
        mock_hm.execute(LISTENERS, HM, VTHUNDER, update_dict, flavor=flavor)
        self.client_mock.slb.hm.update.assert_called_with(a10constants.MOCK_HM_ID,
                                                          self.client_mock.slb.hm.TCP,
                                                          HM.delay, HM.timeout,
                                                          HM.rise_threshold, method=None,
                                                          port=mock.ANY, url=None,
                                                          expect_code=None, post_data=None,
                                                          **FLAVOR_WITH_REGEX_ARGS)

    def test_health_monitor_delete_task(self):
        mock_hm = task.DeleteHealthMonitor()
        mock_hm.axapi_client = self.client_mock
        mock_hm.execute(HM, VTHUNDER)
        self.client_mock.slb.hm.delete.assert_called_with(a10constants.MOCK_HM_ID)
