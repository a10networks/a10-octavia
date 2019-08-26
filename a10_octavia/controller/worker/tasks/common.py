from taskflow import task

from octavia.controller.worker import task_utils as task_utilities
from octavia.common import constants
import acos_client
from octavia.amphorae.driver_exceptions import exceptions as driver_except
import time
from oslo_log import log as logging
from oslo_config import cfg
from a10_octavia.common import openstack_mappings
from a10_octavia.controller.worker.tasks.policy import PolicyUtil
from a10_octavia.controller.worker.tasks import persist
from a10_octavia import a10_config



CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class BaseVThunderTask(task.Task):
    """Base task to instansiate common classes."""

    def __init__(self, **kwargs):
        a10_conf =a10_config. A10Config()
        self.config = a10_conf.get_conf()
        self.task_utils = task_utilities.TaskUtils()
        super(BaseVThunderTask, self).__init__(**kwargs)

    def client_factory(self, vthunder):
        axapi_version = acos_client.AXAPI_21 if vthunder.axapi_version == 21 else acos_client.AXAPI_30
        c = acos_client.Client(vthunder.ip_address, axapi_version, vthunder.username, vthunder.password)
        return c

    def meta(self, lbaas_obj, key, default):
        if isinstance(lbaas_obj, dict):
            m = lbaas_obj.get('a10_meta', '{}')
        elif hasattr(lbaas_obj, 'a10_meta'):
            m = lbaas_obj.a10_meta
        else:
            return default
        try:
            d = json.loads(m)
        except Exception:
            return default
        return d.get(key, default)

