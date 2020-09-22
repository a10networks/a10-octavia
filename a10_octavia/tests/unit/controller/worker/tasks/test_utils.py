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
