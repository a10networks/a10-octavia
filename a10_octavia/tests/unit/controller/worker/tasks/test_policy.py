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

from octavia.common import data_models as o_data_models
from octavia.tests.unit import base

from a10_octavia.controller.worker.tasks import policy
from a10_octavia.tests.common import a10constants

L7POLICY = o_data_models.L7Policy(id=a10constants.MOCK_L7POLICY_ID,
                                  listener_id=a10constants.MOCK_LISTENER_ID,
                                  action="REDIRECT_TO_URL",
                                  redirect_url="www.google.com")
L7RULE = o_data_models.L7Rule(id=a10constants.MOCK_L7RULE_ID,
                              l7policy_id=a10constants.MOCK_L7POLICY_ID,
                              type="PATH", compare_type="EQUAL_TO",
                              value="www://abc.com")


class TestPolicy(base.TestCase):
    def test_policy_rule_path(self):
        L7POLICY.l7rules = [L7RULE]
        policy_util = policy.PolicyUtil()
        policy_util.createPolicy(L7POLICY)
        self.assertEqual(policy_util.ruleParser(L7RULE),
                         '([HTTP::path] equals "www://abc.com")')
