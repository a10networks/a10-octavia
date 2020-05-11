# Copyright 2020, A10 Networks.
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

import unittest

from a10_octavia.common import utils


class TestUtils(unittest.TestCase):

    def test_check_ip_in_subnet_range_valid(self):
        self.assertEqual(utils.check_ip_in_subnet_range('10.10.10.8', '10.10.10.0/24'), True)
        self.assertEqual(utils.check_ip_in_subnet_range('0.0.0.0', '0.0.0.0/24'), True)

    def test_check_ip_in_subnet_range_invalid(self):
        self.assertEqual(utils.check_ip_in_subnet_range('10.10.11.8', '10.10.10.0/24'), False)
        self.assertEqual(utils.check_ip_in_subnet_range('0.0.0.0', '10.10.10.0/24'), False)
        self.assertEqual(utils.check_ip_in_subnet_range('1.2.3', '10.10.10.0/24'), False)
