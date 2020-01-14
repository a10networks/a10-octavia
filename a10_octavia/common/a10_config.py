# Copyright 2011 VMware, Inc., 2014 A10 Networks
# All Rights Reserved.
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

"""
Routines for configuring Octavia
"""

import sys

from keystoneauth1 import loading as ks_loading
from oslo_config import cfg
from oslo_db import options as db_options
from oslo_log import log as logging
import oslo_messaging as messaging

from octavia.certificates.common import local
from octavia.common import constants
from octavia.common import utils
from octavia.i18n import _
from octavia import version
from a10_octavia.common import a10_types

LOG = logging.getLogger(__name__)

# TODO(rm_work) Remove in or after "R" release
API_SETTINGS_DEPRECATION_MESSAGE = _(
    'This setting has moved to the [api_settings] section.')


a10_core_opts = [
    cfg.HostnameOpt('host', default=utils.get_hostname(),
                    help=_("The hostname Octavia is running on")),
    cfg.StrOpt('octavia_plugins', default='hot_plug_plugin',
               help=_("Name of the controller plugin to use")),

    # TODO(johnsom) Remove in or after "R" release
    cfg.IPOpt('bind_host', help=_("The host IP to bind to"),
              deprecated_for_removal=True,
              deprecated_reason=API_SETTINGS_DEPRECATION_MESSAGE),
    # TODO(johnsom) Remove in or after "R" release
    cfg.PortOpt('bind_port', help=_("The port to bind to"),
                deprecated_for_removal=True,
                deprecated_reason=API_SETTINGS_DEPRECATION_MESSAGE),
    # TODO(johnsom) Remove in or after "R" release
    cfg.StrOpt('auth_strategy',
               choices=[constants.NOAUTH,
                        constants.KEYSTONE,
                        constants.TESTING],
               help=_("The auth strategy for API requests."),
               deprecated_for_removal=True,
               deprecated_reason=API_SETTINGS_DEPRECATION_MESSAGE),
    # TODO(johnsom) Remove in or after "R" release
    cfg.StrOpt('api_handler',
               help=_("The handler that the API communicates with"),
               deprecated_for_removal=True,
               deprecated_reason=API_SETTINGS_DEPRECATION_MESSAGE),
]

# Options only used by the amphora agent
a10_amphora_agent_opts = [
    cfg.StrOpt('agent_server_ca', default='/etc/octavia/certs/client_ca.pem',
               help=_("The ca which signed the client certificates")),
    cfg.StrOpt('agent_server_cert', default='/etc/octavia/certs/server.pem',
               help=_("The server certificate for the agent.py server "
                      "to use")),
    cfg.StrOpt('agent_server_network_dir',
               help=_("The directory where new network interfaces "
                      "are located")),
    cfg.StrOpt('agent_server_network_file',
               help=_("The file where the network interfaces are located. "
                      "Specifying this will override any value set for "
                      "agent_server_network_dir.")),
    cfg.IntOpt('agent_request_read_timeout', default=180,
               help=_("The time in seconds to allow a request from the "
                      "controller to run before terminating the socket.")),
    # Do not specify in octavia.conf, loaded at runtime
    cfg.StrOpt('amphora_id', help=_("The amphora ID.")),
    cfg.StrOpt('amphora_udp_driver',
               default='keepalived_lvs',
               help='The UDP API backend for amphora agent.'),
]

a10_networking_opts = [
    cfg.IntOpt('max_retries', default=15,
               help=_('The maximum attempts to retry an action with the '
                      'networking service.')),
    cfg.IntOpt('retry_interval', default=1,
               help=_('Seconds to wait before retrying an action with the '
                      'networking service.')),
    cfg.IntOpt('port_detach_timeout', default=300,
               help=_('Seconds to wait for a port to detach from an '
                      'amphora.')),
    cfg.BoolOpt('allow_vip_network_id', default=True,
                help=_('Can users supply a network_id for their VIP?')),
    cfg.BoolOpt('allow_vip_subnet_id', default=True,
                help=_('Can users supply a subnet_id for their VIP?')),
    cfg.BoolOpt('allow_vip_port_id', default=True,
                help=_('Can users supply a port_id for their VIP?')),
    cfg.ListOpt('valid_vip_networks',
                help=_('List of network_ids that are valid for VIP '
                       'creation. If this field is empty, no validation '
                       'is performed.')),
    cfg.ListOpt('reserved_ips',
                default=['169.254.169.254'],
                item_type=cfg.types.IPAddress(),
                help=_('List of IP addresses reserved from being used for '
                       'member addresses. IPv6 addresses should be in '
                       'expanded, uppercase form.')),
]

a10_vthunder_opts = [
    cfg.StrOpt('DEFAULT_VTHUNDER_USERNAME', 
                default='admin',
                help=_('VThunder username')),
    cfg.StrOpt('DEFAULT_VTHUNDER_PASSWORD',
                default='a10',
                help=_('VThunder password')),
    cfg.IntOpt('DEFAULT_AXAPI_VERSION',
                default='30',
                help=_('VThunder axapi version')),

]

a10_slb_opts = [
    cfg.BoolOpt('arp_disable', default=False,
                help=_('slb arp_disable')),
    cfg.StrOpt('default_virtual_server_vrid',
                help=_('default_virtual_server_vrid')),
    cfg.StrOpt('logging_template',
                help=_('logging_template')),
    cfg.StrOpt('policy_template',
                help=_('policy_template')),
    cfg.StrOpt('template_virtual_server',
                help=_('template_virtual_server')),
]

a10_listener_opts = [
    cfg.BoolOpt('ipinip', default=False,
                 help=_('ipinip')),
    cfg.BoolOpt('no_dest_nat',
                 help=_('no_dest_nat')),
    cfg.BoolOpt('ha_conn_mirror',
                 help=_('ha_conn_mirror')),
    cfg.StrOpt('template_virtual_port', 
                help=_('template_virtual_port')),
    cfg.StrOpt('template_tcp',
                help=_('template_tcp')),
    cfg.StrOpt('template_policy',
                help=_('template_policy')),
    cfg.BoolOpt('autosnat', default=True,
                 help=_('autosnat')),
    cfg.IntOpt('conn_limit',
                help=_('conn_limit')),
    cfg.StrOpt('template_http',
                help=_('template_http')),
]

a10_service_group_opts = [
    cfg.StrOpt('templates',
                help=_('templates')),
]

a10_l7_policy_opts = [
    cfg.StrOpt('P1',
                help=_('P1')),
    cfg.StrOpt('P2',
                help=_('P2')),
]

a10_l7_rule_opts = [
    cfg.StrOpt('R1',
                help=_('R1')),
    cfg.StrOpt('R2',
                help=_('R2')),
]

a10_server_opts = [
    cfg.IntOpt('conn_limit',
                help=_('conn_limit')),
    cfg.IntOpt('conn_resume',
                help=_('conn_resume')),
    cfg.StrOpt('templates',
                help=_('templates')),
]

a10_rack_vthunder_opts = [
    a10_types.ListOfDictOpt('devices',
                            item_type=a10_types.ListOfObjects(),
                            bounds=True,
                            help=_('list of all device configuration'))    
]

a10_healthmanager_opts = [
    cfg.IPOpt('bind_ip', default='127.0.0.1',
              help=_('IP address the controller will listen on for '
                     'heart beats')),
    cfg.PortOpt('bind_port', default=5550,
                help=_('Port number the controller will listen on'
                       'for heart beats')),
    cfg.IntOpt('failover_threads',
               default=10,
               help=_('Number of threads performing amphora failovers.')),
    cfg.IntOpt('status_update_threads',
               default=None,
               help=_('Number of processes for amphora status update.')),
    cfg.IntOpt('health_update_threads',
               default=None,
               help=_('Number of processes for amphora health update.')),
    cfg.IntOpt('stats_update_threads',
               default=None,
               help=_('Number of processes for amphora stats update.')),
    cfg.StrOpt('heartbeat_key',
               help=_('key used to validate amphora sending'
                      'the message'), secret=True),
    cfg.IntOpt('heartbeat_timeout',
               default=60,
               help=_('Interval, in seconds, to wait before failing over an '
                      'amphora.')),
    cfg.IntOpt('health_check_interval',
               default=3,
               help=_('Sleep time between health checks in seconds.')),
    cfg.IntOpt('sock_rlimit', default=0,
               help=_(' sets the value of the heartbeat recv buffer')),

    # Used by the health manager on the amphora
    cfg.ListOpt('controller_ip_port_list',
                help=_('List of controller ip and port pairs for the '
                       'heartbeat receivers. Example 127.0.0.1:5550, '
                       '192.168.0.1:5550'),
                default=[]),
    cfg.IntOpt('heartbeat_interval',
               default=10,
               help=_('Sleep time between sending heartbeats.')),

    # Used for updating health and stats
    cfg.StrOpt('health_update_driver', default='health_db',
               help=_('Driver for updating amphora health system.')),
    cfg.StrOpt('stats_update_driver', default='stats_db',
               help=_('Driver for updating amphora statistics.')),

    # Used for synchronizing neutron-lbaas and octavia
    cfg.StrOpt('event_streamer_driver',
               help=_('Specifies which driver to use for the event_streamer '
                      'for syncing the octavia and neutron_lbaas dbs. If you '
                      'don\'t need to sync the database or are running '
                      'octavia in stand alone mode use the '
                      'noop_event_streamer'),
               default='noop_event_streamer'),
    cfg.BoolOpt('sync_provisioning_status', default=False,
                help=_("Enable provisioning status sync with neutron db"))]

a10_oslo_messaging_opts = [
    cfg.StrOpt('topic'),
    cfg.StrOpt('event_stream_topic',
               default='neutron_lbaas_event',
               help=_('topic name for communicating events through a queue')),
    cfg.StrOpt('event_stream_transport_url', default=None,
               help=_('Transport URL to use for the neutron-lbaas'
                      'synchronization event stream when neutron and octavia'
                      'have separate queues.')),
]

a10_haproxy_amphora_opts = [
    cfg.StrOpt('base_path',
               default='/var/lib/octavia',
               help=_('Base directory for amphora files.')),
    cfg.StrOpt('base_cert_dir',
               default='/var/lib/octavia/certs',
               help=_('Base directory for cert storage.')),
    cfg.StrOpt('haproxy_template', help=_('Custom haproxy template.')),
    cfg.BoolOpt('connection_logging', default=True,
                help=_('Set this to False to disable connection logging.')),
    cfg.IntOpt('connection_max_retries',
               default=300,
               help=_('Retry threshold for connecting to amphorae.')),
    cfg.IntOpt('connection_retry_interval',
               default=5,
               help=_('Retry timeout between connection attempts in '
                      'seconds.')),
    cfg.IntOpt('active_connection_max_retries',
               default=15,
               help=_('Retry threshold for connecting to active amphorae.')),
    cfg.IntOpt('active_connection_rety_interval',
               default=2,
               help=_('Retry timeout between connection attempts in '
                      'seconds for active amphora.')),
    cfg.IntOpt('build_rate_limit',
               default=-1,
               help=_('Number of amphorae that could be built per controller'
                      'worker, simultaneously.')),
    cfg.IntOpt('build_active_retries',
               default=300,
               help=_('Retry threshold for waiting for a build slot for '
                      'an amphorae.')),
    cfg.IntOpt('build_retry_interval',
               default=5,
               help=_('Retry timeout between build attempts in '
                      'seconds.')),
    cfg.StrOpt('haproxy_stick_size', default='10k',
               help=_('Size of the HAProxy stick table. Accepts k, m, g '
                      'suffixes.  Example: 10k')),

    # REST server
    cfg.IPOpt('bind_host', default='::',  # nosec
              help=_("The host IP to bind to")),
    cfg.PortOpt('bind_port', default=9443,
                help=_("The port to bind to")),
    cfg.StrOpt('lb_network_interface',
               default='o-hm0',
               help=_('Network interface through which to reach amphora, only '
                      'required if using IPv6 link local addresses.')),
    cfg.StrOpt('haproxy_cmd', default='/usr/sbin/haproxy',
               help=_("The full path to haproxy")),
    cfg.IntOpt('respawn_count', default=2,
               help=_("The respawn count for haproxy's upstart script")),
    cfg.IntOpt('respawn_interval', default=2,
               help=_("The respawn interval for haproxy's upstart script")),
    cfg.FloatOpt('rest_request_conn_timeout', default=10,
                 help=_("The time in seconds to wait for a REST API "
                        "to connect.")),
    cfg.FloatOpt('rest_request_read_timeout', default=60,
                 help=_("The time in seconds to wait for a REST API "
                        "response.")),
    # REST client
    cfg.StrOpt('client_cert', default='/etc/octavia/certs/client.pem',
               help=_("The client certificate to talk to the agent")),
    cfg.StrOpt('server_ca', default='/etc/octavia/certs/server_ca.pem',
               help=_("The ca which signed the server certificates")),
    cfg.BoolOpt('use_upstart', default=True,
                deprecated_for_removal=True,
                deprecated_reason='This is now automatically discovered '
                                  ' and configured.',
                help=_("If False, use sysvinit.")),
]

a10_controller_worker_opts = [
    cfg.IntOpt('workers',
               default=1, min=1,
               help='Number of workers for the controller-worker service.'),
    cfg.IntOpt('amp_active_retries',
               default=10,
               help=_('Retry attempts to wait for Amphora to become active')),
    cfg.IntOpt('amp_active_wait_sec',
               default=10,
               help=_('Seconds to wait between checks on whether an Amphora '
                      'has become active')),
    cfg.StrOpt('amp_flavor_id',
               default='',
               help=_('Nova instance flavor id for the Amphora')),
    cfg.StrOpt('amp_image_tag',
               default='',
               help=_('Glance image tag for the Amphora image to boot. '
                      'Use this option to be able to update the image '
                      'without reconfiguring Octavia. '
                      'Ignored if amp_image_id is defined.')),
    cfg.StrOpt('amp_image_id',
               default='',
               deprecated_for_removal=True,
               deprecated_reason='Superseded by amp_image_tag option.',
               help=_('Glance image id for the Amphora image to boot')),
    cfg.StrOpt('amp_image_owner_id',
               default='',
               help=_('Restrict glance image selection to a specific '
                      'owner ID.  This is a recommended security setting.')),
    cfg.StrOpt('amp_ssh_key_name',
               default='',
               help=_('SSH key name used to boot the Amphora')),
    cfg.BoolOpt('amp_ssh_access_allowed',
                default=True,
                deprecated_for_removal=True,
                deprecated_reason='This option and amp_ssh_key_name overlap '
                                  'in functionality, and only one is needed. '
                                  'SSH access can be enabled/disabled simply '
                                  'by setting amp_ssh_key_name, or not.',
                help=_('Determines whether or not to allow access '
                       'to the Amphorae')),
    cfg.ListOpt('amp_boot_network_list',
                default='',
                help=_('List of networks to attach to the Amphorae. '
                       'All networks defined in the list will '
                       'be attached to each amphora.')),
    cfg.ListOpt('amp_secgroup_list',
                default='',
                help=_('List of security groups to attach to the Amphora.')),
    cfg.StrOpt('client_ca',
               default='/etc/octavia/certs/ca_01.pem',
               help=_('Client CA for the amphora agent to use')),
    cfg.StrOpt('amphora_driver',
               default='amphora_noop_driver',
               help=_('Name of the amphora driver to use')),
    cfg.StrOpt('compute_driver',
               default='compute_noop_driver',
               help=_('Name of the compute driver to use')),
    cfg.StrOpt('network_driver',
               default='network_noop_driver',
               help=_('Name of the network driver to use')),
    cfg.StrOpt('distributor_driver',
               default='distributor_noop_driver',
               help=_('Name of the distributor driver to use')),
    cfg.StrOpt('loadbalancer_topology',
               default=constants.TOPOLOGY_SINGLE,
               choices=constants.SUPPORTED_LB_TOPOLOGIES,
               help=_('Load balancer topology configuration. '
                      'SINGLE - One amphora per load balancer. '
                      'ACTIVE_STANDBY - Two amphora per load balancer.')),
    cfg.BoolOpt('user_data_config_drive', default=False,
                help=_('If True, build cloud-init user-data that is passed '
                       'to the config drive on Amphora boot instead of '
                       'personality files. If False, utilize personality '
                       'files.'))
]

a10_task_flow_opts = [
    cfg.StrOpt('engine',
               default='serial',
               help=_('TaskFlow engine to use')),
    cfg.IntOpt('max_workers',
               default=5,
               help=_('The maximum number of workers')),
    cfg.BoolOpt('disable_revert', default=False,
                help=_('If True, disables the controller worker taskflow '
                       'flows from reverting.  This will leave resources in '
                       'an inconsistent state and should only be used for '
                       'debugging purposes.'))
]

a10_core_cli_opts = []


a10_house_keeping_opts = [
    cfg.IntOpt('spare_check_interval',
               default=30,
               help=_('Spare check interval in seconds')),
    cfg.IntOpt('spare_amphora_pool_size',
               default=0,
               help=_('Number of spare amphorae')),
    cfg.IntOpt('cleanup_interval',
               default=30,
               help=_('DB cleanup interval in seconds')),
    cfg.IntOpt('amphora_expiry_age',
               default=604800,
               help=_('Amphora expiry age in seconds')),
    cfg.IntOpt('load_balancer_expiry_age',
               default=604800,
               help=_('Load balancer expiry age in seconds')),
    cfg.IntOpt('cert_interval',
               default=3600,
               help=_('Certificate check interval in seconds')),
    # 14 days for cert expiry buffer
    cfg.IntOpt('cert_expiry_buffer',
               default=1209600,
               help=_('Seconds until certificate expiration')),
    cfg.IntOpt('cert_rotate_threads',
               default=10,
               help=_('Number of threads performing amphora certificate'
                      ' rotation'))
]

a10_anchor_opts = [
    cfg.StrOpt('url',
               default='http://localhost:9999/v1/sign/default',
               help=_('Anchor URL')),
    cfg.StrOpt('username',
               help=_('Anchor username')),
    cfg.StrOpt('password',
               help=_('Anchor password'),
               secret=True)
]

a10_nova_opts = [
    cfg.StrOpt('service_name',
               help=_('The name of the nova service in the keystone catalog')),
    cfg.StrOpt('endpoint', help=_('A new endpoint to override the endpoint '
                                  'in the keystone catalog.')),
    cfg.StrOpt('region_name',
               help=_('Region in Identity service catalog to use for '
                      'communication with the OpenStack services.')),
    cfg.StrOpt('endpoint_type', default='publicURL',
               help=_('Endpoint interface in identity service to use')),
    cfg.StrOpt('ca_certificates_file',
               help=_('CA certificates file path')),
    cfg.BoolOpt('insecure',
                default=False,
                help=_('Disable certificate validation on SSL connections')),
    cfg.BoolOpt('enable_anti_affinity', default=False,
                help=_('Flag to indicate if nova anti-affinity feature is '
                       'turned on.')),
    cfg.StrOpt('anti_affinity_policy', default=constants.ANTI_AFFINITY,
               choices=[constants.ANTI_AFFINITY, constants.SOFT_ANTI_AFFINITY],
               help=_('Sets the anti-affinity policy for nova')),
    cfg.IntOpt('random_amphora_name_length', default=0,
               help=_('If non-zero, generate a random name of the length '
                      'provided for each amphora, in the format "a[A-Z0-9]*". '
                      'Otherwise, the default name format will be used: '
                      '"amphora-{UUID}".')),
    cfg.StrOpt('availability_zone', default=None,
               help=_('Availability zone to use for creating Amphorae')),
]

a10_neutron_opts = [
    cfg.StrOpt('service_name',
               help=_('The name of the neutron service in the '
                      'keystone catalog')),
    cfg.StrOpt('endpoint', help=_('A new endpoint to override the endpoint '
                                  'in the keystone catalog.')),
    cfg.StrOpt('region_name',
               help=_('Region in Identity service catalog to use for '
                      'communication with the OpenStack services.')),
    cfg.StrOpt('endpoint_type', default='publicURL',
               help=_('Endpoint interface in identity service to use')),
    cfg.StrOpt('ca_certificates_file',
               help=_('CA certificates file path')),
    cfg.BoolOpt('insecure',
                default=False,
                help=_('Disable certificate validation on SSL connections ')),
]


a10_octavia_opts = [
    cfg.StrOpt('amp_image_owner_id',
               default='',
               help=_('Restrict glance image selection to a specific '
                      'owner ID.  This is a recommended security setting.')),
    cfg.ListOpt('amp_secgroup_list',
                default='',
                help=_('List of security groups to attach to the VThunder.')),
    cfg.StrOpt('amp_flavor_id',
               default='',
               help=_('Nova instance flavor id for the VThunder')),
    cfg.ListOpt('amp_boot_network_list',
                default='',
                help=_('List of networks to attach to the VThunder. '
                       'All networks defined in the list will '
                       'be attached to each vthunder.')),
    cfg.StrOpt('amp_ssh_key_name',
               default='',
               help=_('SSH key name used to boot the VThunder')),
    cfg.StrOpt('network_driver',
               default='network_noop_driver',
               help=_('Name of the network driver to use')),
    cfg.StrOpt('compute_driver',
               default='compute_noop_driver',
               help=_('Name of the compute driver to use')),
    cfg.StrOpt('amphora_driver',
               default='amphora_noop_driver',
               help=_('Name of the vthunder driver to use')),
    cfg.IntOpt('workers',
               default=1, min=1,
               help='Number of workers for the controller-worker service.'),
    cfg.IntOpt('amp_active_retries',
               default=10,
               help=_('Retry attempts to wait for VThunder to become active')),
    cfg.IntOpt('amp_active_wait_sec',
               default=10,
               help=_('Seconds to wait between checks on whether an VThunder '
                      'has become active')),
    cfg.StrOpt('amp_image_id',
               default='',
               deprecated_for_removal=True,
               deprecated_reason='Superseded by amp_image_tag option.',
               help=_('Glance image id for the VThunder image to boot')),
    cfg.StrOpt('amp_image_tag',
               default='',
               help=_('Glance image tag for the VThunder image to boot. '
                      'Use this option to be able to update the image '
                      'without reconfiguring Octavia. '
                      'Ignored if amp_image_id is defined.')),
    cfg.BoolOpt('user_data_config_drive', default=False,
                help=_('If True, build cloud-init user-data that is passed '
                       'to the config drive on VThunder boot instead of '
                       'personality files. If False, utilize personality '
                       'files.'))

]

# Register the configuration options
cfg.CONF.register_opts(a10_core_opts)
cfg.CONF.register_opts(a10_amphora_agent_opts, group='a10_amphora_agent')
cfg.CONF.register_opts(a10_networking_opts, group='a10_networking')
cfg.CONF.register_opts(a10_oslo_messaging_opts, group='a10_oslo_messaging')
cfg.CONF.register_opts(a10_haproxy_amphora_opts, group='a10_haproxy_amphora')
cfg.CONF.register_opts(a10_controller_worker_opts, group='a10_controller_worker')
cfg.CONF.register_opts(a10_task_flow_opts, group='a10_task_flow')
cfg.CONF.register_opts(a10_house_keeping_opts, group='a10_house_keeping')
cfg.CONF.register_opts(a10_anchor_opts, group='a10_anchor')
cfg.CONF.register_cli_opts(a10_healthmanager_opts, group='a10_health_manager')
cfg.CONF.register_opts(a10_nova_opts, group='a10_nova')
cfg.CONF.register_opts(a10_neutron_opts, group='a10_neutron')
cfg.CONF.register_opts(a10_octavia_opts, group='a10_octavia')

cfg.CONF.register_opts(a10_vthunder_opts, group='VTHUNDER')
cfg.CONF.register_opts(a10_slb_opts, group='SLB')
cfg.CONF.register_opts(a10_listener_opts, group='LISTENER')
cfg.CONF.register_opts(a10_service_group_opts, group='SERVICE-GROUP')
cfg.CONF.register_opts(a10_l7_policy_opts, group='L7POLICY')
cfg.CONF.register_opts(a10_l7_rule_opts, group='L7RULE')
cfg.CONF.register_opts(a10_server_opts, group='SERVER')
cfg.CONF.register_opts(a10_rack_vthunder_opts, group='RACK_VTHUNDER')


# Ensure that the control exchange is set correctly
messaging.set_transport_defaults(control_exchange='octavia')
_SQL_CONNECTION_DEFAULT = 'sqlite://'
# Update the default QueuePool parameters. These can be tweaked by the
# configuration variables - max_pool_size, max_overflow and pool_timeout
db_options.set_defaults(cfg.CONF, connection=_SQL_CONNECTION_DEFAULT,
                        max_pool_size=10, max_overflow=20, pool_timeout=10)

logging.register_options(cfg.CONF)

ks_loading.register_auth_conf_options(cfg.CONF, constants.SERVICE_AUTH)
ks_loading.register_session_conf_options(cfg.CONF, constants.SERVICE_AUTH)


def init(args, **kwargs):
    cfg.CONF(args=args, project='octavia',
             version='%%prog %s' % version.version_info.release_string(),
             **kwargs)
    handle_deprecation_compatibility()


def setup_logging(conf):
    """Sets up the logging options for a log with supplied name.

    :param conf: a cfg.ConfOpts object
    """
    product_name = "octavia"
    logging.setup(conf, product_name)
    LOG.info("Logging enabled!")
    LOG.info("%(prog)s version %(version)s",
             {'prog': sys.argv[0],
              'version': version.version_info.release_string()})
    LOG.debug("command line: %s", " ".join(sys.argv))


# Use cfg.CONF.set_default to override the new configuration setting
# default value.  This allows a value set, at the new location, to override
# a value set in the previous location while allowing settings that have
# not yet been moved to be utilized.
def handle_deprecation_compatibility():
    # TODO(johnsom) Remove in or after "R" release
    if cfg.CONF.bind_host is not None:
        cfg.CONF.set_default('bind_host', cfg.CONF.bind_host,
                             group='api_settings')
    # TODO(johnsom) Remove in or after "R" release
    if cfg.CONF.bind_port is not None:
        cfg.CONF.set_default('bind_port', cfg.CONF.bind_port,
                             group='api_settings')
    # TODO(johnsom) Remove in or after "R" release
    if cfg.CONF.auth_strategy is not None:
        cfg.CONF.set_default('auth_strategy', cfg.CONF.auth_strategy,
                             group='api_settings')
    # TODO(johnsom) Remove in or after "R" release
    if cfg.CONF.api_handler is not None:
        cfg.CONF.set_default('api_handler', cfg.CONF.api_handler,
                             group='api_settings')
    if cfg.CONF.health_manager.status_update_threads is not None:
        cfg.CONF.set_default('health_update_threads',
                             cfg.CONF.health_manager.status_update_threads,
                             group='health_manager')
        cfg.CONF.set_default('stats_update_threads',
                             cfg.CONF.health_manager.status_update_threads,
                             group='health_manager')
