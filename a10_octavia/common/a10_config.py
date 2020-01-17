# Copyright 2020 A10 Networks
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


import sys

from keystoneauth1 import loading as ks_loading
from oslo_config import cfg
from oslo_db import options as db_options
from oslo_log import log as logging
import oslo_messaging as messaging

from octavia.common import constants
from octavia.i18n import _
from octavia import version
from a10_octavia.common import a10_types

LOG = logging.getLogger(__name__)


A10_VTHUNDER_OPTS = [
    cfg.StrOpt('DEFAULT_VTHUNDER_USERNAME',
               default='admin',
               help=_('VThunder username')),
    cfg.StrOpt('DEFAULT_VTHUNDER_PASSWORD',
               default='a10',
               help=_('VThunder password')),
    cfg.IntOpt('DEFAULT_AXAPI_VERSION',
               default=30,
               help=_('VThunder axapi version')),

]

A10_SLB_OPTS = [
    cfg.BoolOpt('arp_disable', default=False,
                help=_('slb arp_disable')),
    cfg.IntOpt('default_virtual_server_vrid',
               default=0,
               help=_('default_virtual_server_vrid')),
    cfg.StrOpt('logging_template',
               default=None,
               help=_('logging_template')),
    cfg.StrOpt('policy_template',
               default=None,
               help=_('policy_template')),
    cfg.StrOpt('template_virtual_server',
               default=None,
               help=_('template_virtual_server')),
]

A10_LISTENER_OPTS = [
    cfg.BoolOpt('ipinip', default=False,
                help=_('ipinip')),
    cfg.BoolOpt('no_dest_nat',
                default=False,
                help=_('no_dest_nat')),
    cfg.BoolOpt('ha_conn_mirror',
                default=False,
                help=_('ha_conn_mirror')),
    cfg.StrOpt('template_virtual_port',
               default=None,
               help=_('template_virtual_port')),
    cfg.StrOpt('template_tcp',
               default=None,
               help=_('template_tcp')),
    cfg.StrOpt('template_policy',
               default=None,
               help=_('template_policy')),
    cfg.BoolOpt('autosnat', default=True,
                help=_('autosnat')),
    cfg.IntOpt('conn_limit', min=1, max=8000000,
               default=8000000,
               help=_('conn_limit')),
    cfg.StrOpt('template_http',
               default=None,
               help=_('template_http')),
]

A10_SERVICE_GROUP_OPTS = [
    cfg.StrOpt('templates',
               default=None,
               help=_('templates')),
]

A10_L7_POLICY_OPTS = [
    cfg.StrOpt('P1',
               default=None,
               help=_('P1')),
    cfg.StrOpt('P2',
               default=None,
               help=_('P2')),
]

A10_L7_RULE_OPTS = [
    cfg.StrOpt('R1',
               default=None,
               help=_('R1')),
    cfg.StrOpt('R2',
               default=None,
               help=_('R2')),
]

A10_SERVER_OPTS = [
    cfg.IntOpt('conn_limit', min=1, max=8000000,
               default=8000000,
               help=_('conn_limit')),
    cfg.IntOpt('conn_resume', min=1, max=1000000,
               default=1000000,
               help=_('conn_resume')),
    cfg.StrOpt('templates',
               default=None,
               help=_('templates')),
]

A10_RACK_VTHUNDER_OPTS = [
    a10_types.ListOfDictOpt('devices', default=[],
                            item_type=a10_types.ListOfObjects(),
                            bounds=True,
                            help=_('list of all device configuration'))
]

A10_HEALTH_MANAGER_OPTS = [
    cfg.IPOpt('udp_server_ip_address',
              help=_('Server IP address that sends udp packets for '
                     'health manager.')),
    cfg.IPOpt('bind_ip', default='127.0.0.1',
              help=_('IP address the controller will listen on for '
                     'heart beats')),
    cfg.PortOpt('bind_port', default=5550,
                help=_('Port number the controller will listen on'
                       'for heart beats')),
    cfg.IntOpt('failover_threads',
               default=10,
               help=_('Number of threads performing vthunder failovers.')),
    cfg.IntOpt('status_update_threads',
               default=None,
               help=_('Number of processes for vthunder status update.')),
    cfg.IntOpt('health_update_threads',
               default=None,
               help=_('Number of processes for vthunder health update.')),
    cfg.IntOpt('stats_update_threads',
               default=None,
               help=_('Number of processes for vthunder stats update.')),
    cfg.StrOpt('heartbeat_key',
               help=_('key used to validate vthunder sending'
                      'the message'), secret=True),
    cfg.IntOpt('heartbeat_timeout',
               default=60,
               help=_('Interval, in seconds, to wait before failing over an '
                      'vthunder.')),
    cfg.IntOpt('health_check_interval',
               default=3,
               help=_('Sleep time between health checks in seconds.')),
    cfg.IntOpt('sock_rlimit', default=0,
               help=_(' sets the value of the heartbeat recv buffer')),

    cfg.ListOpt('controller_ip_port_list',
                help=_('List of controller ip and port pairs for the '
                       'heartbeat receivers. Example 127.0.0.1:5550, '
                       '192.168.0.1:5550'),
                default=[]),
    cfg.IntOpt('heartbeat_interval',
               default=10,
               help=_('Sleep time between sending heartbeats.')),

]

A10_CONTROLLER_WORKER_OPTS = [
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
    cfg.StrOpt('amp_flavor_id',
               default='',
               help=_('Nova instance flavor id for the VThunder')),
    cfg.StrOpt('amp_image_tag',
               default='',
               help=_('Glance image tag for the VThunder image to boot. '
                      'Use this option to be able to update the image '
                      'without reconfiguring Octavia. '
                      'Ignored if amp_image_id is defined.')),
    cfg.StrOpt('amp_image_id',
               default='',
               deprecated_for_removal=True,
               deprecated_reason='Superseded by amp_image_tag option.',
               help=_('Glance image id for the VThunder image to boot')),
    cfg.StrOpt('amp_image_owner_id',
               default='',
               help=_('Restrict glance image selection to a specific '
                      'owner ID.  This is a recommended security setting.')),
    cfg.StrOpt('amp_ssh_key_name',
               default='',
               help=_('SSH key name used to boot the VThunder')),
    cfg.BoolOpt('amp_ssh_access_allowed',
                default=True,
                deprecated_for_removal=True,
                deprecated_reason='This option and amp_ssh_key_name overlap '
                                  'in functionality, and only one is needed. '
                                  'SSH access can be enabled/disabled simply '
                                  'by setting amp_ssh_key_name, or not.',
                help=_('Determines whether or not to allow access '
                       'to the VThunder')),
    cfg.ListOpt('amp_boot_network_list',
                default='',
                help=_('List of networks to attach to the VThunder. '
                       'All networks defined in the list will '
                       'be attached to each vthunder.')),
    cfg.ListOpt('amp_secgroup_list',
                default='',
                help=_('List of security groups to attach to the VThunder.')),
    cfg.StrOpt('client_ca',
               default='/etc/octavia/certs/ca_01.pem',
               help=_('Client CA for the vthunder agent to use')),
    cfg.StrOpt('amphora_driver',
               default='amphora_noop_driver',
               help=_('Name of the vthunder driver to use')),
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
                      'SINGLE - One vthunder per load balancer. '
                      'ACTIVE_STANDBY - Two vthunder per load balancer.')),
    cfg.BoolOpt('user_data_config_drive', default=False,
                help=_('If True, build cloud-init user-data that is passed '
                       'to the config drive on VThunder boot instead of '
                       'personality files. If False, utilize personality '
                       'files.'))
]

A10_HOUSE_KEEPING_OPTS = [
    cfg.IntOpt('spare_check_interval',
               default=30,
               help=_('Spare check interval in seconds')),
    cfg.IntOpt('spare_amphora_pool_size',
               default=0,
               help=_('Number of spare vthunders')),
    cfg.IntOpt('cleanup_interval',
               default=30,
               help=_('DB cleanup interval in seconds')),
    cfg.IntOpt('amphora_expiry_age',
               default=604800,
               help=_('VThunder expiry age in seconds')),
    cfg.IntOpt('load_balancer_expiry_age',
               default=604800,
               help=_('Load balancer expiry age in seconds')),
    cfg.IntOpt('cert_interval',
               default=3600,
               help=_('Certificate check interval in seconds')),
    cfg.IntOpt('cert_expiry_buffer',
               default=1209600,
               help=_('Seconds until certificate expiration')),
    cfg.IntOpt('cert_rotate_threads',
               default=10,
               help=_('Number of threads performing vthunder certificate'
                      ' rotation'))
]

A10_NOVA_OPTS = [
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
                      'provided for each vthunder, in the format "a[A-Z0-9]*". '
                      'Otherwise, the default name format will be used: '
                      '"amphora-{UUID}".')),
    cfg.StrOpt('availability_zone', default=None,
               help=_('Availability zone to use for creating Amphorae')),
]


# Register the configuration options
cfg.CONF.register_opts(A10_CONTROLLER_WORKER_OPTS, group='a10_controller_worker')
cfg.CONF.register_opts(A10_HOUSE_KEEPING_OPTS, group='a10_house_keeping')
cfg.CONF.register_cli_opts(A10_HEALTH_MANAGER_OPTS, group='a10_health_manager')
cfg.CONF.register_opts(A10_NOVA_OPTS, group='a10_nova')
cfg.CONF.register_opts(A10_VTHUNDER_OPTS, group='VTHUNDER')
cfg.CONF.register_opts(A10_SLB_OPTS, group='SLB')
cfg.CONF.register_opts(A10_LISTENER_OPTS, group='LISTENER')
cfg.CONF.register_opts(A10_SERVICE_GROUP_OPTS, group='SERVICE-GROUP')
cfg.CONF.register_opts(A10_L7_POLICY_OPTS, group='L7POLICY')
cfg.CONF.register_opts(A10_L7_RULE_OPTS, group='L7RULE')
cfg.CONF.register_opts(A10_SERVER_OPTS, group='SERVER')
cfg.CONF.register_opts(A10_RACK_VTHUNDER_OPTS, group='RACK_VTHUNDER')


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
