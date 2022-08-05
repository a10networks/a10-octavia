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

import json
import logging
import re

from oslo_config import cfg

import acos_client.errors as acos_errors

from octavia.common import constants
from octavia_lib.common import constants as lib_consts

from a10_octavia.common import a10constants
from a10_octavia.common.data_models import Certificate
from a10_octavia.common import utils as a10_utils


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


def get_cert_data(barbican_client, listener):
    cert_data = Certificate()
    cert_ref = listener.tls_certificate_id
    cert_container = barbican_client.containers.get(container_ref=cert_ref)
    cert_data = Certificate(cert_filename=cert_container.certificate.name,
                            key_filename=cert_container.private_key.name,
                            cert_content=cert_container.certificate.payload,
                            key_content=cert_container.private_key.payload,
                            key_pass=cert_container.private_key_passphrase,
                            template_name=listener.id)
    return cert_data


def get_sess_pers_templates(pool):
    c_pers, s_pers, sp = None, None, None
    if pool and pool.session_persistence:
        sp = pool.session_persistence
        if hasattr(pool.session_persistence, 'to_dict'):
            sp = pool.session_persistence.to_dict()
        if sp['type'] == 'HTTP_COOKIE' or sp['type'] == 'APP_COOKIE':
            c_pers = pool.id
        elif sp['type'] == 'SOURCE_IP':
            s_pers = pool.id
    return c_pers, s_pers


def is_proxy_protocol_pool(pool):
    if pool.protocol == constants.PROTOCOL_PROXY or (
            pool.protocol == lib_consts.PROTOCOL_PROXYV2):
        return True
    return False


def proxy_protocol_use_aflex(listener, pool):
    if pool.protocol == constants.PROTOCOL_PROXY:
        if listener is not None and (listener.protocol == constants.PROTOCOL_TCP or
                                     listener.protocol == 'tcp'):
            use_aflex_proxy = CONF.service_group.use_aflex_proxy
            if use_aflex_proxy and use_aflex_proxy is True:
                return True
    return False


def get_tcp_proxy_template(listener, pool):
    tcp_proxy = None
    aflex = None
    if pool is None:
        return tcp_proxy, aflex
    if pool.provisioning_status != constants.PENDING_DELETE and (
            is_proxy_protocol_pool(pool) is True):
        if proxy_protocol_use_aflex(listener, pool) is True:
            aflex = a10constants.PROXY_PROTOCPL_AFLEX_NAME
        else:
            tcp_proxy = a10constants.PROXY_PROTOCPL_TEMPLATE_NAME
            if pool.protocol != constants.PROTOCOL_PROXY:
                tcp_proxy = a10constants.PROXY_PROTOCPL_V2_TEMPLATE_NAME
    return tcp_proxy, aflex


def get_proxy_aflex_list(curr, proxy_aflex, exclude_aflex):
    new_aflex_scripts = []
    if curr is not None and 'aflex-scripts' in curr['port']:
        aflexs = curr['port']['aflex-scripts']
        for aflex in aflexs:
            if exclude_aflex is None or aflex['aflex'] != exclude_aflex:
                new_aflex_scripts.append(aflex)
    if proxy_aflex is not None:
        new_aflex_scripts.append({"aflex": proxy_aflex})
    return new_aflex_scripts


def meta(lbaas_obj, key, default):
    if isinstance(lbaas_obj, dict):
        meta = lbaas_obj.get('a10_meta', '{}')
    elif hasattr(lbaas_obj, 'a10_meta'):
        meta = lbaas_obj.a10_meta
    else:
        return default
    try:
        meta_json = json.loads(meta)
    except Exception:
        return default
    return meta_json.get(key, default)


def shared_template_modifier(template_type, template_name, device_templates):
    resource_type = template_type.split('-', 1)[1]
    resource_list_key = "{0}-list".format(resource_type)
    if resource_list_key in device_templates:
        for device_template in device_templates['template'][resource_list_key]:
            device_template_name = device_template[resource_type].get("name")
            if template_name == device_template_name:
                break
            template_type = "{0}-shared".format(template_type)
    else:
        template_type = "{0}-shared".format(template_type)
    return template_type


def parse_name_expressions(name, name_expressions):
    flavor_data = {}
    if name and name_expressions:
        for expression in name_expressions:
            if 'regex' in expression:
                if re.search(expression['regex'], name):
                    flavor_data.update(expression['json'])
    return flavor_data


def dash_to_underscore(my_dict):
    if type(my_dict) is list:
        item_list = []
        for item in my_dict:
            item_list.append(dash_to_underscore(item))
        return item_list
    elif type(my_dict) is dict:
        item_dict = {}
        for k, v in my_dict.items():
            item_dict[k.replace('-', '_')] = dash_to_underscore(v)
        return item_dict
    else:
        return my_dict


def attribute_search(lb_resource, attr_name):
    """This helper method will recursively walk up the slb tree
    starting from the provided lb_resource and find an attribute
    with the provided name. Though objects like pool refrence a
    listener and loadbalancer, the following discrete
    search orders are used:

    1: member -> pool -> listener -> loadbalancer
    2: healthmonitor -> pool -> listener -> loadbalancer

    :param lb_resource: An slb data model
    :param obj_type: String name of an slb object
    (ie 'loadbalancer', 'pool')

    :return: Returns the requested attribute value or none
    """
    if hasattr(lb_resource, attr_name):
        return getattr(lb_resource, attr_name)
    elif hasattr(lb_resource, 'pool'):
        return attribute_search(lb_resource.pool, attr_name)
    elif hasattr(lb_resource, 'listener'):
        return attribute_search(lb_resource.listener, attr_name)
    elif hasattr(lb_resource, 'load_balancer'):
        return attribute_search(lb_resource.load_balancer, attr_name)
    return None


def get_member_server_name(axapi_client, member, raise_not_found=True):
    default_name = '{}_{}'.format(member.project_id[:5], member.ip_address.replace('.', '_'))
    server_name = default_name
    try:
        server_name = axapi_client.slb.server.get(server_name)
    except (acos_errors.NotFound):
        # Backwards compatability with a10-neutron-lbaas
        if CONF.a10_global.use_parent_partition:
            try:
                parent_project_id = a10_utils.get_parent_project(member.project_id)
                server_name = '_{}_{}_neutron'.format(parent_project_id[:5],
                                                      member.ip_address.replace('.', '_'))
                server_name = axapi_client.slb.server.get(server_name)
            except (acos_errors.NotFound):
                server_name = '_{}_{}_neutron'.format(member.project_id[:5],
                                                      member.ip_address.replace('.', '_'))
                try:
                    server_name = axapi_client.slb.server.get(server_name)
                except (acos_errors.NotFound) as e:
                    if raise_not_found:
                        raise e
                    return default_name
        else:
            try:
                server_name = axapi_client.slb.server.get('_{}_{}'.format(server_name, 'neutron'))
            except (acos_errors.NotFound) as e:
                if raise_not_found:
                    raise e
                return default_name
    return server_name['server']['name']
