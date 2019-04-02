from oslo_config import cfg
from taskflow.patterns import graph_flow
from taskflow.patterns import linear_flow
from taskflow.patterns import unordered_flow

from octavia.common import constants
from a10_octavia.controller.worker.tasks import vthunder_tasks
from octavia.controller.worker.tasks import cert_task
from octavia.controller.worker.tasks import compute_tasks
from octavia.controller.worker.tasks import database_tasks
from a10_octavia.controller.worker.tasks import a10_database_tasks
from octavia.controller.worker.tasks import lifecycle_tasks
from octavia.controller.worker.tasks import network_tasks

CONF = cfg.CONF

class VThunderFlows(object):
    def __init__(self):
        # for some reason only this has the values from the config file
        #self.REST_AMPHORA_DRIVER = (CONF.controller_worker.amphora_driver ==
        #                            'amphora_haproxy_rest_driver')
        pass

    def get_create_vthunder_flow(self):
        """Creates a flow to create an amphora.

        :returns: The flow for creating the amphora
        """
        create_vthunder_flow = linear_flow.Flow(constants.CREATE_AMPHORA_FLOW)
        create_vthunder_flow.add(a10_database_tasks.CreateVThunderInDB(
                                provides=constants.AMPHORA_ID))

        return create_vthunder_flow

    def get_vthunder_for_lb_subflow(
            self, prefix, role=constants.ROLE_STANDALONE):
        """Tries to allocate a spare vthunder to a loadbalancer if none

        exists, create a new vthunder.
        """

        sf_name = prefix + '-' + constants.GET_AMPHORA_FOR_LB_SUBFLOW

        # We need a graph flow here for a conditional flow
        amp_for_lb_flow = linear_flow.Flow(sf_name)

        # Setup the task that maps an amphora to a load balancer
        allocate_and_associate_amp = database_tasks.MapLoadbalancerToAmphora(
            name=sf_name + '-' + constants.MAP_LOADBALANCER_TO_AMPHORA,
            requires=constants.LOADBALANCER_ID,
            provides=constants.AMPHORA_ID)
        amp_for_lb_flow.add(allocate_and_associate_amp)

        # adding amphora details in LB
        map_lb_to_amp = self._get_post_map_lb_subflow(prefix, role)
        amp_for_lb_flow.add(map_lb_to_amp) 

        
        # IMP: needs to be converted in graph flow for not having amphora entry
        # Define a subflow for if we successfully map an amphora
        ##map_lb_to_amp = self._get_post_map_lb_subflow(prefix, role)
        # Define a subflow for if we can't map an amphora
        ##create_amp = self._get_create_amp_for_lb_subflow(prefix, role)

        # Add them to the graph flow
        ##amp_for_lb_flow.add(allocate_and_associate_amp,
        ##                    map_lb_to_amp, create_amp)

        # Setup the decider for the path if we can map an amphora
        ##amp_for_lb_flow.link(allocate_and_associate_amp, map_lb_to_amp,
        ##                     decider=self._allocate_amp_to_lb_decider,
        ##                     decider_depth='flow')
        # Setup the decider for the path if we can't map an amphora
        ##amp_for_lb_flow.link(allocate_and_associate_amp, create_amp,
        ##                     decider=self._create_new_amp_for_lb_decider,
        ##                    decider_depth='flow')

        return amp_for_lb_flow

    def _get_post_map_lb_subflow(self, prefix, role):
        """Set amphora type after mapped to lb."""

        sf_name = prefix + '-' + constants.POST_MAP_AMP_TO_LB_SUBFLOW
        post_map_amp_to_lb = linear_flow.Flow(
            sf_name)

        post_map_amp_to_lb.add(database_tasks.ReloadAmphora(
            name=sf_name + '-' + constants.RELOAD_AMPHORA,
            requires=constants.AMPHORA_ID,
            provides=constants.AMPHORA))

        if role == constants.ROLE_MASTER:
            post_map_amp_to_lb.add(database_tasks.MarkAmphoraMasterInDB(
                name=sf_name + '-' + constants.MARK_AMP_MASTER_INDB,
                requires=constants.AMPHORA))
        elif role == constants.ROLE_BACKUP:
            post_map_amp_to_lb.add(database_tasks.MarkAmphoraBackupInDB(
                name=sf_name + '-' + constants.MARK_AMP_BACKUP_INDB,
                requires=constants.AMPHORA))
        elif role == constants.ROLE_STANDALONE:
            post_map_amp_to_lb.add(database_tasks.MarkAmphoraStandAloneInDB(
                name=sf_name + '-' + constants.MARK_AMP_STANDALONE_INDB,
                requires=constants.AMPHORA))

        return post_map_amp_to_lb

