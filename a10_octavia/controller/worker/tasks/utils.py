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

from a10_octavia.common.data_models import Certificate

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
        if sp.type == 'HTTP_COOKIE' or sp.type == 'APP_COOKIE':
            c_pers = pool.id
        elif sp.type == 'SOURCE_IP':
            s_pers = pool.id
    return c_pers, s_pers


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
    if name_expressions:
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
