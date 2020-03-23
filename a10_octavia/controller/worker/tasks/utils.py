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

from a10_octavia.common.data_models import Certificate

LOG = logging.getLogger(__name__)


def get_cert_data(barbican_client, listener):
    cert_data = Certificate()
    cert_ref = listener.tls_certificate_id
    try:
        cert_container = barbican_client.containers.get(container_ref=cert_ref)
        cert_data = Certificate(cert_filename=cert_container.certificate.name,
                                key_filename=cert_container.private_key.name,
                                cert_content=cert_container.certificate.payload,
                                key_content=cert_container.private_key.payload,
                                key_pass=cert_container.private_key_passphrase,
                                template_name=listener.id)
    except Exception as e:
        LOG.exception("Failed to fetch cert containers: %s", str(e))
        raise
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
