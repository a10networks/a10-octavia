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
            "description": "Specify AXAPI that will apply to the slb virtual-server",
            "properties": {
                "name-expressions": {
                    "type": "array",
                    "description": "Specify name expression to match loadbalancers "
                                   "and AXAPI that will apply to the slb virtual-server",
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
            "description": "Specify AXAPI that will apply to the vport",
            "properties": {
                "name-expressions": {
                    "type": "array",
                    "description": "Specify name expression to match listeners "
                                   "and AXAPI that will apply to the vport",
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
            "description": "Specify AXAPI that will apply to the service-group",
            "properties": {
                "name-expressions": {
                    "type": "array",
                    "description": "Specify name expression to match pools "
                                   "and AXAPI that will apply to the service-group",
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
            "description": "Specify AXAPI that will apply to the server",
            "properties": {
                "name-expressions": {
                    "type": "array",
                    "description": "Specify name expression to match members "
                                   "and AXAPI that will apply to the server",
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
            "description": "Specify AXAPI that will apply to the health monitor",
            "properties": {
                "name-expressions": {
                    "type": "array",
                    "description": "Specify name expression to match healthmonitor "
                                   "and AXAPI that will apply to the health monitor",
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
            "description": "Specify AXAPI of default nat pool for loadbalancer",
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
            "description": "Specify AXAPI of nat pools for loadbalancer",
            "items": {
                "type": "object",
                "properties": {
                    "pool-name": {
                        "type": "string",
                    }
                }
            }
        },
        "device-name": {
            "type": "string",
            "description": "Specify vthunder device name that used for this loadbalancer"
        },
        "deployment": {
            "type": "object",
            "description": "Specify deployment strategy for the loadbalancer",
            "properties": {
                "dsr_type": {
                    "type": "string",
                    "description": "Specify deployment DSR type[l2dsr_transparent]"
                                   " for the loadbalancer"
                }
            }
        },
        "dns": {
            "type": "object",
            "description": "DNS nameserver information",
            "properties": {
                "primary-dns": {
                    "type": "string",
                    "description": "Primary nameserver used to contact the GLM or ELM"
                },
                "secondary-dns": {
                    "type": "string",
                    "description": "Secondary nameserver used to contact the GLM or ELM"
                }
            }
        },
        "glm-proxy-server": {
            "type": "object",
            "description": "Forward proxy-server configuration details.",
            "properties": {
                "proxy-host": {
                    "type": "string",
                    "description": "Hostname of proxy server used for requests to GLM"
                },
                "proxy-port": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 65535,
                    "description": "Port number through which the forward proxy server "
                                   "connects to the GLM account",
                },
                "proxy-username": {
                    "type": "string",
                    "description": "Username for proxy authentication"
                },
                "proxy-password": {
                    "type": "boolean",
                    "description": "Password for proxy authentication"
                },
                "proxy-secret-string": {
                    "type": "string",
                    "description": "Password for proxy authentication"
                }
            }
        },
        "glm": {
            "type": "object",
            "description": "Global License Manager configuration settings",
            "properties": {
                "use-network-dns": {
                    "type": "boolean",
                    "description": "Use the network dns nameservers instead of "
                                   "those in the config or flavor."
                },
                "allocate-bandwidth": {
                    "type": "integer",
                    "description": "Bandwidth allocated per amphora",
                    "minimum": 2,
                    "maximum": 204800
                },
                "burst": {
                    "type": "boolean",
                    "description": "Enable bursting. Allows amphora to exceed allocated "
                                   "bandwidth limits. Ensures that packets never drop."
                },
                "interval": {
                    "type": "integer",
                    "description": "Interval for license manager heartbeat in hours",
                    "minimum": 1,
                    "maximum": 8760
                },
                "port": {
                    "type": "integer",
                    "description": "Port with which to send HTTP/S license request",
                    "minimum": 1,
                    "maximum": 65535
                },
                "enable-requests": {
                    "type": "boolean",
                    "description": "Enables license retrieval from the GLM/ELM server. "
                                   "Allows license changes to be replicated automatically.",
                },
            }
        }
    }
}
