from oslo_config import cfg
from taskflow.patterns import graph_flow
from taskflow.patterns import linear_flow
from taskflow.patterns import unordered_flow

from octavia.common import constants
from a10_octavia.controller.worker.tasks import vthunder_tasks
from octavia.controller.worker.tasks import cert_task
from octavia.controller.worker.tasks import compute_tasks
from a10_octavia.controller.worker.tasks import database_tasks
from octavia.controller.worker.tasks import lifecycle_tasks
from octavia.controller.worker.tasks import network_tasks

CONF = cfg.CONF

class VThunderFlows(object):
    def __init__(self):
        # for some reason only this has the values from the config file
        #self.REST_AMPHORA_DRIVER = (CONF.controller_worker.amphora_driver ==
                                    'amphora_haproxy_rest_driver')

    def get_create_vthunder_flow(self):
        """Creates a flow to create an amphora.

        :returns: The flow for creating the amphora
        """
        create_vthunder_flow = linear_flow.Flow(constants.CREATE_AMPHORA_FLOW)
        create_vthunder_flow.add(database_tasks.CreateVThunderInDB(
                                provides=constants.AMPHORA_ID))

        return create_vthunder_flow
