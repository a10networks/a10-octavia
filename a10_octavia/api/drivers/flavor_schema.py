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

SUPPORTED_FLAVOR_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "Octavia Amphora Driver Flavor Metadata Schema",
    "description": "This schema is used to validate new flavor profiles "
                   "submitted for use in an a10 driver flavor profile.",
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "listener": {
            "type": "object",
            "properties": {
                "tcp_template": {
                    "type": "string",
                    "description": "TCP Template name for TCP listener"
                },
                "http_template": {
                    "type": "string",
                    "description": "HTTP Template name for HTTP listener"
                },
                "http_template_regex": {
                    "type": "boolean",
                    "description": "use http template with regex"
                }
            }
        },
        "server": {
            "type": "object",
            "properties": {
                "conn_limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 64000000,
                    "default": 64000000,
                    "description": "Connection Limit"
                },
                "conn_resume": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 1000000,
                    "description": "Connection Resume"
                }
            }
        },
        "listener-list": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "regex": {
                        "type": "string",
                    },
                    "listener": {
                        "type": "object",
                        "properties": {
                            "tcp_template": {
                                "type": "string",
                                "description": "TCP Template name for TCP listener"
                            },
                            "http_template": {
                                "type": "string",
                                "description": "HTTP Template name for HTTP listener"
                            },
                        }
                    },
                }
            }
        },
    }
}
