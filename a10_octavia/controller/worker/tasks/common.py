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


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class BaseVThunderTask(task.Task):
    """Base task to instansiate common classes."""

    def __init__(self, **kwargs):
        self.task_utils = task_utilities.TaskUtils()
        super(BaseVThunderTask, self).__init__(**kwargs)

