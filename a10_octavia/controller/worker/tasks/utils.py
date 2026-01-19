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
import base64
import binascii
from datetime import datetime

from oslo_config import cfg

import acos_client.errors as acos_errors

from octavia.common import constants
from octavia_lib.common import constants as lib_consts

from a10_octavia.common import a10constants
from a10_octavia.common.data_models import Certificate
from a10_octavia.common import utils as a10_utils


CONF = cfg.CONF
LOG = logging.getLogger(__name__)

def get_password(barbican_client, project_id, secret_name = None):
    """
    Retrieve a password secret from Barbican.
    Ensures the secret exists, is not expired (if expiration is set), and has a payload.
    """
    try:
        if secret_name is None:
            secret_name = project_id + '_vthunder_password'
        secrets = barbican_client.secrets.list(name=secret_name)
        if not secrets:
            LOG.error("No secret found with name: '%s'", secret_name)
            return None

        secret_ref = secrets[0].secret_ref
        secret = barbican_client.secrets.get(secret_ref)

        if secret.expiration:
            try:
                # Parse expiration (ISO 8601 format: "YYYY-MM-DDTHH:MM:SS")
                expiration_dt = datetime.strptime(secret.expiration, "%Y-%m-%dT%H:%M:%S")
                if expiration_dt < datetime.utcnow():
                    LOG.error("Secret '%s' is expired (expired at %s)", secret_name, secret.expiration)
                    return None
            except ValueError as ve:
                LOG.warning("Secret '%s' has invalid expiration format: %s", secret_name, secret.expiration)
        else:
            LOG.debug("Secret '%s' has no expiration; assuming it's valid", secret_name)

        payload = secret.payload
        if not payload:
            LOG.error("Secret '%s' exists but has no payload", secret_name)
            return None
        return payload

    except Exception as e:
        LOG.exception("Failed to retrieve secret '%s': %s", secret_name, str(e))
        return None

def decode_base64(encoded_str):
    try:
        return base64.b64decode(encoded_str).decode('utf-8')
    except (binascii.Error, UnicodeDecodeError):
        return encoded_str

def get_cert_data(barbican_client, listener):
    cert_data = Certificate()
    cert_ref = listener.get(constants.TLS_CERTIFICATE_ID)
    LOG.info("Cert ID: %s", cert_ref)

    try:
        cert_container = barbican_client.containers.get(container_ref=cert_ref)
        cert_data = Certificate(
            cert_filename=cert_container.certificate.name,
            key_filename=cert_container.private_key.name,
            cert_content=cert_container.certificate.payload,
            key_content=cert_container.private_key.payload,
            key_pass=cert_container.private_key_passphrase,
            template_name=listener.get(constants.ID))
        LOG.info("Secret container found: %s", cert_ref)

    except Exception as e:
        LOG.warning("Secret container not found or failed to retrieve %s: %s", cert_ref, str(e))

    return cert_data


def get_sess_pers_templates(pool):
    c_pers, s_pers, sp = None, None, None
    if pool and pool['session_persistence']:
        sp = pool['session_persistence']
        if hasattr(pool['session_persistence'], 'to_dict'):
            sp = pool['session_persistence'].to_dict()
        if sp['type'] == 'HTTP_COOKIE' or sp['type'] == 'APP_COOKIE':
            c_pers = pool[constants.POOL_ID]
        elif sp['type'] == 'SOURCE_IP':
            s_pers = pool[constants.POOL_ID]
    return c_pers, s_pers


def is_proxy_protocol_pool(pool):
    if pool[constants.PROTOCOL] == constants.PROTOCOL_PROXY or (
            pool[constants.PROTOCOL]  == lib_consts.PROTOCOL_PROXYV2):
        return True
    return False


def proxy_protocol_use_aflex(listener, pool):
    if pool[constants.PROTOCOL] == constants.PROTOCOL_PROXY:
        if listener is not None and (listener[constants.PROTOCOL] == constants.PROTOCOL_TCP or
                                     listener[constants.PROTOCOL] == 'tcp'):
            use_aflex_proxy = CONF.service_group.use_aflex_proxy
            if use_aflex_proxy and use_aflex_proxy is True:
                return True
    return False


def get_tcp_proxy_template(listener, pool):
    tcp_proxy = None
    aflex = None
    if pool is None:
        return tcp_proxy, aflex
    if pool.get(constants.PROVISIONING_STATUS) != constants.PENDING_DELETE and (
            is_proxy_protocol_pool(pool) is True):
        if proxy_protocol_use_aflex(listener, pool) is True:
            aflex = a10constants.PROXY_PROTOCPL_AFLEX_NAME
        else:
            tcp_proxy = a10constants.PROXY_PROTOCPL_TEMPLATE_NAME
            if pool[constants.PROTOCOL] != constants.PROTOCOL_PROXY:
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
    if isinstance(lb_resource, dict):
        if attr_name in lb_resource:
            return lb_resource[attr_name]
        # Check common nested keys
        for key in ('pool', 'listener', 'load_balancer'):
            if key in lb_resource:
                return attribute_search(lb_resource[key], attr_name)

    elif hasattr(lb_resource, attr_name):
        return getattr(lb_resource, attr_name)
    elif hasattr(lb_resource, 'pool'):
        return attribute_search(lb_resource.pool, attr_name)
    elif hasattr(lb_resource, 'listener'):
        return attribute_search(lb_resource.listener, attr_name)
    elif hasattr(lb_resource, 'load_balancer'):
        return attribute_search(lb_resource.load_balancer, attr_name)
    return None


def get_member_server_name(axapi_client, member, raise_not_found=True):
    ip = member.get(constants.ADDRESS) or member.get(constants.IP_ADDRESS)
    default_name = '{}_{}'.format(member[constants.PROJECT_ID][:5], ip.replace('.', '_'))
    server_name = default_name
    try:
        server_name = axapi_client.slb.server.get(server_name)
    except (acos_errors.NotFound):
        # Backwards compatability with a10-neutron-lbaas
        if CONF.a10_global.use_parent_partition:
            try:
                parent_project_id = a10_utils.get_parent_project(member[constants.PROJECT_ID])
                server_name = '_{}_{}_neutron'.format(parent_project_id[:5],
                                                      ip.replace('.', '_'))
                server_name = axapi_client.slb.server.get(server_name)
            except (acos_errors.NotFound):
                server_name = '_{}_{}_neutron'.format(member[constants.PROJECT_ID][:5],
                                                      ip.replace('.', '_'))
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


def acos_version_str2int(ver):
    if ver.isdigit():
        return int(ver)
    else:
        vnum = ""
        for index in range(len(ver)):
            if ver[index].isdigit():
                vnum = vnum + ver[index]
            else:
                break
        return int(vnum)


def acos_revision_parse(revision):
    rev = []
    revision_list = ['GR', 'P', 'SP']
    for tag in revision_list:
        tag_index = revision.find(tag)
        if tag_index >= 0:
            tag_len = len(tag)
            rev.append(acos_version_str2int(revision[(tag_index + tag_len):]))
        else:
            rev.append(0)

    return tuple(rev)


def acos_version(acos_version):
    major = acos_version_str2int(acos_version.split('.')[0])
    minor = acos_version_str2int(acos_version.split('.')[1])
    patch = acos_version_str2int(acos_version.split('.')[2])

    revision = ""
    prev = acos_version.find('-')
    if prev > 0:
        revision = acos_version[prev + 1:].upper()
    gr, p, sp = acos_revision_parse(revision)

    return (major, minor, patch, gr, p, sp)


def acos_version_cmp(ver1, ver2):
    vtup1 = acos_version(ver1)
    vtup2 = acos_version(ver2)
    for index in range(len(vtup1)):
        if vtup1[index] != vtup2[index]:
            return vtup1[index] - vtup2[index]
    return 0
