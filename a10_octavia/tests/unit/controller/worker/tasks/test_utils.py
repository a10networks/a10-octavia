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
#    under the License.]

from octavia.tests.unit import base

from a10_octavia.controller.worker.tasks import utils

NAME_EXPRESSIONS = [
    {
        "regex": "vport1",
        "json": {"support_http2": 1}
    },
    {
        "regex": "vport2",
        "json": {"support_http2": 0}
    }
]

DASH_FLAVOR = {
    "virtual-server": {
        "port-number": 80,
        "name-expressions": [
            {
                "regex": "vip1-test",
                "json": {
                    "arp-disable": 0,
                    "extended-stats": 0,
                }
            },
            {
                "regex": "vip2-test",
                "json": {
                    "arp-disable": 1,
                    "extended-stats": 1,
                }
            }
        ]
    },
    "virtual-port": {
        "support-http2": 0
    },
}

UNDERSCORE_FLAVOR = {
    "virtual_server": {
        "port_number": 80,
        "name_expressions": [
            {
                "regex": "vip1-test",
                "json": {
                    "arp_disable": 0,
                    "extended_stats": 0,
                }
            },
            {
                "regex": "vip2-test",
                "json": {
                    "arp_disable": 1,
                    "extended_stats": 1,
                }
            }
        ]
    },
    "virtual_port": {
        "support_http2": 0
    },
}


class TestUtils(base.TestCase):

    def _get_device_templates(self, template_type, template_name):
        device_templates = {"template": {
            "{}-list".format(template_type): [{
                template_type: {"name": template_name}
            }]
        }
        }
        return device_templates

    def test_shared_template_modifier_resource_not_found(self):
        device_templates = self._get_device_templates('http', 'my_http_temp')
        template_type = utils.shared_template_modifier('template-tcp',
                                                       'my_tcp_temp',
                                                       device_templates)
        self.assertEqual('template-tcp-shared', template_type)

    def test_shared_template_modifier_resource_found_name_found(self):
        device_templates = self._get_device_templates('tcp', 'my_tcp_temp')
        template_type = utils.shared_template_modifier('template-tcp',
                                                       'my_tcp_temp',
                                                       device_templates)
        self.assertEqual('template-tcp-shared', template_type)

    def test_shared_template_modifier_resource_found_name_not_found(self):
        device_templates = self._get_device_templates('tcp', 'my_secondary_tcp')
        template_type = utils.shared_template_modifier('template-tcp',
                                                       'my_tcp_temp',
                                                       device_templates)
        self.assertEqual('template-tcp-shared', template_type)

    def test_parse_name_expressions(self):
        expect_result = {"support_http2": 1}
        obj_flavor = utils.parse_name_expressions("vport1", NAME_EXPRESSIONS)
        self.assertEqual(expect_result, obj_flavor)

    def test_dash_to_underscore(self):
        obj_flavor = utils.dash_to_underscore(DASH_FLAVOR)
        self.assertEqual(UNDERSCORE_FLAVOR, obj_flavor)
