[DEFAULT]
DEFAULT_VTHUNDER_USERNAME = "admin"
DEFAULT_VTHUNDER_PASSWORD = "a10"
DEFAULT_AXAPI_VERSION = 30

[SLB]

arp_disable = False
default_virtual_server_vrid = "10"
logging_template = "Logging_temp1"
policy_template = "policy_temp1"
template_virtual_server = "virtual_server_template1"
default_virtual_server_vrid = 0


[LISTENER]
ipinip = False
no_dest_nat = False
ha_conn_mirror = False
template_virtual_port = "vport_template"
template_tcp = "tcp_template"
template_policy = "policy_temp1"
autosnat = True
conn_limit = 5000
template_http = "http_template"
use_rcv_hop_for_resp = True

[SERVICE - GROUP]
templates = "server1"

[L7POLICY]
P1 = "P1"
P2 = "P2"

[L7RULE]
R1 = "R1"
R2 = "R2"

[SERVER]
conn_limit = 5000
conn_resume = 1
templates = "server1"

[RACK_VTHUNDER]
devices = """[
                    {
                     "project_id":"a0e57f9fcdfa47d18fe9ec9f80d63851",
                     "ip_address":"10.43.82.155",
                     "undercloud":"True",
                     "username":"admin",
                     "password":"a10",
                     "device_name":"rack_vthunder",
                     "axapi_version":"30"
                     },
                     {
                     "project_id":"a0e37f9fcdfa48d18fe9ec9f80d6385f",
                     "ip_address":"10.43.12.137",
                     "undercloud":"True",
                     "username":"admin",
                     "password":"a10",
                     "device_name":"rack_vthunder",
                     "axapi_version":"30",
                     "role":"MASTER",
                     "topology":"STANDALONE"
                     }
             ]
       """
