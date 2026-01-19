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
from octavia.common import constants

TYPE_DICT = {
    "HOST_NAME": "HTTP::host",
    "PATH": "HTTP::path",
    "FILE_TYPE": "HTTP::uri endswith",
    "HEADER": "HTTP::header",
    "COOKIE": "HTTP::cookie"
}


COMPARE_TYPE_DICT = {
    "REGEX": "matches_regex",
    "STARTS_WITH": "starts_with",
    "ENDS_WITH": "ends_with",
    "CONTAINS": "contains",
    "EQUAL_TO": "equals"
}


class PolicyUtil(object):
    def __init__(self):
        self.base = """ when HTTP_REQUEST {{ \n
        if {{ {0} }} {{ \n
        {1}  \n
        }} \n
        }} """

    def createPolicy(self, l7policy):
        actionString = ""
        if l7policy['action'] == "REDIRECT_TO_POOL":
            actionString = "pool " + l7policy.get("redirect_pool_id", "")

        elif l7policy['action'] == "REDIRECT_TO_URL":
            actionString = "HTTP::redirect " + l7policy.get("redirect_url", "")

        else:
            actionString = "HTTP::close"
        ruleString = ""
        l7rules = (l7policy.get("l7rules", []) or l7policy.get("rules", []))
        if len(l7rules) <= 0:
            ruleString = "( true )"
        else:
            ruleArray = []
            for rule in l7rules:
                temp = self.ruleParser(rule)
                ruleArray.append(temp)
            ruleString = " and ".join(ruleArray)
        return self.base.format(ruleString, actionString)

    def ruleParser(self, l7rule):
        ruleString = "("
        # type
        typeString = TYPE_DICT[l7rule.get('type')]
        if l7rule.get('key') and (l7rule.get('type') == 'HEADER' or l7rule.get('type') == 'COOKIE'):
            typeString = typeString + " " + l7rule.get('key')
        typeString = "[" + typeString + "]"
        ruleString += typeString

        # compare type
        compare_type_string = COMPARE_TYPE_DICT[l7rule.get('compare_type')]
        ruleString += " " + compare_type_string

        # rule string static - required for file type rules only
        if l7rule.get('type') == "FILE_TYPE":
            if l7rule.get('compare_type') == "REGEX":
                ruleString = "([HTTP::uri] matches_regex"
            else:
                ruleString = "([HTTP::uri] ends_with"

        # value
        value_string = l7rule.get('value')
        ruleString += " \"" + value_string + "\""

        ruleString += ")"
        if l7rule.get('invert'):
            ruleString = "not" + ruleString
        return ruleString
