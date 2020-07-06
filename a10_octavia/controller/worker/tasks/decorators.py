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


import acos_client
from oslo_config import cfg
from oslo_log import log as logging
from requests.exceptions import ConnectionError

from a10_octavia.common import a10constants

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


def activate_partition(vthunder_client, partition):
    try:
        if vthunder_client.system.partition.exists(partition):
            vthunder_client.system.partition.active(partition)
    except Exception as e:
        LOG.exception("Failed to activate partition: %s", str(e))
        raise


def axapi_client_decorator(func):
    def wrapper(self, *args, **kwargs):
        vthunder = kwargs.get('vthunder')
        if vthunder:
            api_ver = acos_client.AXAPI_21 if vthunder.axapi_version == 21 else acos_client.AXAPI_30
            self.axapi_client = acos_client.Client(vthunder.ip_address, api_ver,
                                                   vthunder.username, vthunder.password,
                                                   timeout=30)

            if vthunder.partition_name != a10constants.SHARED_PARTITION:
                activate_partition(self.axapi_client, vthunder.partition_name)

        else:
            self.axapi_client = None
        result = func(self, *args, **kwargs)

        try:
            self.axapi_client.session.close()
        except ConnectionError as e:
            LOG.debug("Failed to close the vThunder session: %s", str(e))
        except AttributeError:
            pass

        return result

    return wrapper
