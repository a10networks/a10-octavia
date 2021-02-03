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

""" This module takes care of the Configuration Options set by config files for a10-octavia"""

import sys

from keystoneauth1 import loading as ks_loading
from oslo_config import cfg
from oslo_db import options as db_options
from oslo_log import log as logging
import oslo_messaging as messaging

from octavia.common import constants
from octavia.i18n import _
from octavia import version

from a10_octavia.common import a10constants
from a10_octavia.common import config_types

LOG = logging.getLogger(__name__)


A10_GLOBAL_OPTS = [
    cfg.BoolOpt('use_parent_partition', default=False,
                help=_('Use parent project partition on Thunder device '
                       'in hierarchical project architecture.')),
    cfg.IntOpt('vrid', default=0,
               help=_('VRID value')),
    cfg.StrOpt('vrid_floating_ip', default=None,
               help=_('Enable VRID floating IP feature')),
    cfg.StrOpt('network_type',
               default=a10constants.FLAT,
               choices=a10constants.SUPPORTED_NETWORK_TYPE,
               help=_('Neutron ML2 Tenent Network Type')),
    cfg.BoolOpt('use_shared_for_template_lookup',
                default=False,
                help=_('Use shared for template')),
]

A10_VTHUNDER_OPTS = [
    cfg.StrOpt('default_vthunder_username',
               default='admin',
               help=_('VThunder username')),
    cfg.StrOpt('default_vthunder_password',
               default='a10',
               help=_('VThunder password')),
    cfg.IntOpt('default_axapi_version',
               default=30,
               help=_('VThunder axapi version')),
]

A10_SLB_OPTS = [
    cfg.BoolOpt('arp_disable', default=False,
                help=_('Disable Respond to Virtual Server ARP request')),
    cfg.IntOpt('default_virtual_server_vrid',
               default=0,
               help=_('Default Virtual Server VRID')),
]

A10_HEALTH_MONITOR_OPTS = [
    cfg.StrOpt('post_data',
               help=_('HTTP Content for "--http-method POST" case.')),
]

A10_LISTENER_OPTS = [
    cfg.BoolOpt('ipinip', default=False,
                help=_('Enable IP in IP.')),
    cfg.BoolOpt('no_dest_nat',
                default=False,
                help=_('Disable destination NAT')),
    cfg.BoolOpt('ha_conn_mirror',
                default=None,
                help=_('Enable for HA Conn sync')),
    cfg.StrOpt('template_virtual_port',
               default=None,
               max_length=127,
               help=_('Provide an existing Virtual port template name on VThunder '
                      'to associate with virtual port')),
    cfg.StrOpt('template_tcp',
               default=None,
               max_length=127,
               help=_('Provide an existing TCP template name on VThunder '
                      'to associate with virtual port')),
    cfg.StrOpt('template_policy',
               default=None,
               max_length=127,
               help=_('Provide an existing Policy template name on VThunder '
                      'to associate with virtual port')),
    cfg.BoolOpt('autosnat', default=False,
                help=_('Enable autosnat')),
    cfg.IntOpt('conn_limit', min=1, max=64000000,
               default=64000000,
               help=_('Connection Limit')),
    cfg.StrOpt('template_http',
               default=None,
               max_length=127,
               help=_('Provide an existing HTTP template name on VThunder '
                      'to associate with virtual port')),
    cfg.BoolOpt('use_rcv_hop_for_resp',
                default=False,
                help=_('Use receive hop for response to client')),
]

A10_SERVICE_GROUP_OPTS = [
    cfg.StrOpt('template_server',
               default=None,
               help=_('Provide an existing Service Group Server template name on VThunder '
                      'to associate with service group')),
    cfg.StrOpt('template_port',
               default=None,
               help=_('Provide an existing Service Group Port template name on VThunder '
                      'to associate with service group')),
    cfg.StrOpt('template_policy',
               default=None,
               help=_('Provide an existing Service Group Policy template name on VThunder '
                      'to associate with service group')),
]

A10_SERVER_OPTS = [
    cfg.IntOpt('conn_limit', min=1, max=64000000,
               default=64000000,
               help=_('Connection Limit')),
    cfg.IntOpt('conn_resume', min=1, max=1000000,
               default=None,
               help=_('Connection Resume')),
    cfg.StrOpt('template_server',
               default=None,
               help=_('Provide an existing Server template name on VThunder '
                      'to associate with server')),
]

A10_HARDWARE_THUNDER_OPTS = [
    config_types.ListOfDictOpt('devices', default=[],
                               item_type=config_types.ListOfObjects(),
                               bounds=True,
                               help=_('List of all device configuration'))
]

A10_HEALTH_MANAGER_OPTS = [
    cfg.IPOpt('udp_server_ip_address',
              help=_('Server IP address that sends udp packets for '
                     'health manager.')),
    cfg.IPOpt('bind_ip', default='127.0.0.1',
              help=_('IP address the controller will listen on for '
                     'heart beats')),
    cfg.IntOpt('failover_timeout',
               default=600,
               help=_('Interval(in seconds) to wait before considering '
                      'a vThunder is eligible for failover.')),
    cfg.IntOpt('health_check_timeout', min=1, max=180,
               default=3,
               help=_('Specify the Healthcheck timeout(in seconds) in '
                      ' vThunder. ')),
    cfg.IntOpt('health_check_max_retries', min=1, max=10,
               default=3,
               help=_('Specify the Healthcheck Retries in '
                      'a vThunder. ')),
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
               default=90,
               help=_('Interval(in seconds) to wait before failing over a '
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
    cfg.ListOpt('amp_boot_network_list',
                default='',
                help=_('List of networks to attach to the VThunder. '
                       'All networks defined in the list will '
                       'be attached to each vthunder.')),
    cfg.ListOpt('amp_secgroup_list',
                default='',
                help=_('List of security groups to attach to the VThunder.')),
    cfg.IntOpt('build_rate_limit',
               default=-1,
               help=_('Number of vThunders that could be built per controller '
                      'worker, simultaneously.')),
    cfg.StrOpt('network_driver',
               default='network_noop_driver',
               help=_('Name of the network driver to use')),
    cfg.StrOpt('loadbalancer_topology',
               default=constants.TOPOLOGY_SINGLE,
               choices=constants.SUPPORTED_LB_TOPOLOGIES,
               help=_('Load balancer topology configuration. '
                      'SINGLE - One vthunder per load balancer. '
                      'ACTIVE_STANDBY - Two vthunder per load balancer.'))
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
                      ' rotation')),
    cfg.IntOpt('write_mem_interval',
               default=3600,
               min=300,
               help=_('Write Memory interval in seconds')),
    cfg.StrOpt('use_periodic_write_memory',
               choices=['enable', 'disable'],
               default='disable',
               help=_('Enable to use periodic write memory on all thunders'))
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
cfg.CONF.register_opts(A10_GLOBAL_OPTS, group='a10_global')
cfg.CONF.register_opts(A10_CONTROLLER_WORKER_OPTS, group='a10_controller_worker')
cfg.CONF.register_opts(A10_HOUSE_KEEPING_OPTS, group='a10_house_keeping')
cfg.CONF.register_cli_opts(A10_HEALTH_MANAGER_OPTS, group='a10_health_manager')
cfg.CONF.register_opts(A10_NOVA_OPTS, group='a10_nova')
cfg.CONF.register_opts(A10_VTHUNDER_OPTS, group='vthunder')
cfg.CONF.register_opts(A10_SLB_OPTS, group='slb')
cfg.CONF.register_opts(A10_HEALTH_MONITOR_OPTS, group='health_monitor')
cfg.CONF.register_opts(A10_LISTENER_OPTS, group='listener')
cfg.CONF.register_opts(A10_SERVICE_GROUP_OPTS, group='service_group')
cfg.CONF.register_opts(A10_SERVER_OPTS, group='server')
cfg.CONF.register_opts(A10_HARDWARE_THUNDER_OPTS, group='hardware_thunder')


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


def init(*args, **kwargs):
    """ Initialize the cfg.CONF object for octavia project"""
    cfg.CONF(*args, project='octavia',
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
