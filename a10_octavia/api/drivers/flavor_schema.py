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
        "slb": {
            "type": "object",
            "properties": {
                "name-expressions": {
                    "type": "array",
                    "description": "Specify name expression to match loadbalancers "
                                   "and options that will apply to the slb",
                    "items": {
                        "type": "object",
                        "properties": {
                            "regex": {
                                "type": "string",
                            },
                            "json": {
                                "type": "object",
                            },
                        }
                    }
                },
            }
        },
        "listener": {
            "type": "object",
            "properties": {
                "name-expressions": {
                    "type": "array",
                    "description": "Specify name expression to match listeners "
                                   "and options that will apply to the vport",
                    "items": {
                        "type": "object",
                        "properties": {
                            "regex": {
                                "type": "string",
                            },
                            "json": {
                                "type": "object",
                            },
                        }
                    }
                },
                "template_tcp": {
                    "type": "string",
                    "description": "TCP Template name for TCP listener"
                },
                "template_http": {
                    "type": "string",
                    "description": "HTTP Template name for HTTP listener"
                },
                "http_template_regex": {
                    "type": "boolean",
                    "description": "use http template with regex"
                }
            }
        },
        "service_group": {
            "type": "object",
            "properties": {
                "name-expressions": {
                    "type": "array",
                    "description": "Specify name expression to match pools "
                                   "and options that will apply to the service-group",
                    "items": {
                        "type": "object",
                        "properties": {
                            "regex": {
                                "type": "string",
                            },
                            "json": {
                                "type": "object",
                            },
                        }
                    }
                },
            }
        },
        "server": {
            "type": "object",
            "properties": {
                "name-expressions": {
                    "type": "array",
                    "description": "Specify name expression to match members "
                                   "and options that will apply to the server",
                    "items": {
                        "type": "object",
                        "properties": {
                            "regex": {
                                "type": "string",
                            },
                            "json": {
                                "type": "object",
                            },
                        }
                    }
                },
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
        "health_monitor": {
            "type": "object",
            "properties": {
                "name-expressions": {
                    "type": "array",
                    "description": "Specify name expression to match healthmonitor"
                                   " and options that will apply to the health monitor",
                    "items": {
                        "type": "object",
                        "properties": {
                            "regex": {
                                "type": "string",
                            },
                            "json": {
                                "type": "object",
                            },
                        }
                    }
                },
            }
        },
    }
}
