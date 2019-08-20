[DEFAULT]
DEFAULT_VTHUNDER_USERNAME = "admin"
DEFAULT_VTHUNDER_PASSWORD = "a10"
DEFAULT_AXAPI_VERSION = 30

[SLB]
a="10"
arp_disable=False
default_virtual_server_vrid=1
logging_template="Logging_temp1"
policy_template="policy_temp1"
template-virtual-server="virtual_server_template1"


[LISTENER]
ipinip=False
no_dest_nat=False
ha_conn_mirror=False
virtual_port_templates="vport_template"
tcp_template="tcp_template"
template_policy="policy_temp1"
template_scaleout=
autosnat=True
conn-limit=5000
http_template="http_template"

[SERVICE_GROUP]
templates="server1"

[L7POLICY]
P1="P1"
P2="P2"

[L7RULE]
R1="R1"
R2="R2"

[SERVER]
conn-limit=5000
conn-resume=1
templates="server1"

