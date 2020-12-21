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
        "virtual-server": {
            "type": "object",
            "description": "Specify axapi that will apply to the slb virtual-server",
            "properties": {
                "name-expressions": {
                    "type": "array",
                    "description": "Specify name expression to match loadbalancers "
                                   "and axapi that will apply to the slb virtual-server",
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
        "virtual-port": {
            "type": "object",
            "description": "Specify axapi that will apply to the vport",
            "properties": {
                "name-expressions": {
                    "type": "array",
                    "description": "Specify name expression to match listeners "
                                   "and axapi that will apply to the vport",
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
                "template-tcp": {
                    "type": "string",
                },
                "template-http": {
                    "type": "string",
                },
                "template-virtual-port": {
                    "type": "string",
                },
            }
        },
        "service-group": {
            "type": "object",
            "description": "Specify axapi that will apply to the service-group",
            "properties": {
                "name-expressions": {
                    "type": "array",
                    "description": "Specify name expression to match pools "
                                   "and axapi that will apply to the service-group",
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
            "description": "Specify axapi that will apply to the server",
            "properties": {
                "name-expressions": {
                    "type": "array",
                    "description": "Specify name expression to match members "
                                   "and axapi that will apply to the server",
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
                "conn-limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 64000000,
                    "default": 64000000,
                },
                "conn-resume": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 1000000,
                }
            }
        },
        "health-monitor": {
            "type": "object",
            "description": "Specify axapi that will apply to the health monitor",
            "properties": {
                "name-expressions": {
                    "type": "array",
                    "description": "Specify name expression to match healthmonitor "
                                   "and axapi that will apply to the health monitor",
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
        "nat-pool": {
            "type": "object",
            "description": "Specify axapi of default nat pool for loadbalancer",
            "properties": {
                "pool-name": {
                    "type": "string",
                },
                "start-address": {
                    "type": "string",
                },
                "end-address": {
                    "type": "string",
                },
                "netmask": {
                    "type": "string",
                }
            }
        },
        "nat-pool-list": {
            "type": "array",
            "description": "Specify axapi of nat pools for loadbalancer",
            "items": {
                "type": "object",
                "properties": {
                    "pool-name": {
                        "type": "string",
                    }
                }
            }
        },
    }
}
