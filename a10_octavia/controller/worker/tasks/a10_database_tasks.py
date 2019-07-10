from oslo_config import cfg
from oslo_db import exception as odb_exceptions
from oslo_log import log as logging
from oslo_utils import excutils
from oslo_utils import uuidutils
import six
import sqlalchemy
from sqlalchemy.orm import exc
from taskflow import task
from taskflow.types import failure

from octavia.common import constants
from octavia.common import data_models
import octavia.common.tls_utils.cert_parser as cert_parser
from octavia.controller.worker import task_utils as task_utilities
from octavia.db import api as db_apis
from octavia.db import repositories as repo
from a10_octavia.db import repositories as a10_repo
from octavia.api.drivers import driver_lib
from a10_octavia import a10_config

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class BaseDatabaseTask(task.Task):
    """Base task to load drivers common to the tasks."""

    def __init__(self, **kwargs):
        self.repos = repo.Repositories()
        self.vthunder_repo = a10_repo.VThunderRepository()
        self.amphora_repo = repo.AmphoraRepository()
        super(BaseDatabaseTask, self).__init__(**kwargs)


class GetVThunderTask(BaseDatabaseTask):
    """Test Vthunder entry"""
    def execute(self, amphora):
        vthunder = self.vthunder_repo.get(db_apis.get_session(), id=123)
        LOG.info("check this vthunder bro" ) 
        return vthunder


class CreteVthunderEntry(BaseDatabaseTask):
    """ Create VThunder device entry in DB"""
    def execute(self, amphora, loadbalancer):
        vthunder_id = uuidutils.generate_uuid()
        a10_cfg = a10_config.A10Config()
        username = a10_cfg.get('DEFAULT_VTHUNDER_USERNAME')
        password = a10_cfg.get('DEFAULT_VTHUNDER_PASSWORD')
        axapi_version = int(a10_cfg.get('DEFAULT_AXAPI_VERSION'))
        compute_id = amphora.compute_id
        vthunder = self.vthunder_repo.create(db_apis.get_session(), vthunder_id=vthunder_id, 
                                        amphora_id = amphora.id,
                                        device_name = vthunder_id, username = username, 
                                        password = password, ip_address = amphora.lb_network_ip,
                                        undercloud = False, axapi_version = axapi_version, 
                                        loadbalancer_id = loadbalancer.id, 
                                        project_id = loadbalancer.project_id,
                                        compute_id = compute_id)
        LOG.info("Successfully created vthunder entry in database.")

class DeleteVthunderEntry(BaseDatabaseTask):
    """ Delete VThunder device entry in DB  """
    def execute(self, loadbalancer): 
        self.vthunder_repo.delete(db_apis.get_session(), loadbalancer_id=loadbalancer.id)
        LOG.info("Successfully deleted vthunder entry in database.")

class GetVThunderByLoadBalancer(BaseDatabaseTask):
    """ Get VThunder details from LoadBalancer"""
    def execute(self, loadbalancer):
        loadbalancer_id = loadbalancer.id
        vthunder = self.vthunder_repo.getVThunderFromLB(db_apis.get_session(), loadbalancer_id)
        return vthunder
        LOG.info("Successfully fetched vThunder details for LB")

class GetVThunderByLoadBalancerID(BaseDatabaseTask):
    """ Get VThunder details from LoadBalancer ID """
    def execute(self, loadbalancer_id):
        vthunder = self.vthunder_repo.getVThunderFromLB(db_apis.get_session(), loadbalancer_id)
        return vthunder
        LOG.info("Successfully fetched vThunder details for LB")


class GetComputeForProject(BaseDatabaseTask):
    """ Get Compute details form Loadbalancer object -> project ID"""
    def execute(self, loadbalancer):
        vthunder = self.vthunder_repo.getVThunderByProjectID(db_apis.get_session(), loadbalancer.project_id)
        amphora_id = vthunder.amphora_id
        amphora = self.amphora_repo.get(db_apis.get_session(), id=amphora_id)
        compute_id = amphora.compute_id
        return compute_id
        LOG.info("Provided compute ID for existing vThunder device")

class MapLoadbalancerToAmphora(BaseDatabaseTask):
    """Maps and assigns a load balancer to an amphora in the database."""

    def execute(self, loadbalancer, server_group_id=None):
        """Allocates an Amphora for the load balancer in the database.

        :param loadbalancer_id: The load balancer id to map to an amphora
        :returns: Amphora ID if one was allocated, None if it was
                  unable to allocate an Amphora
        """

        

        if server_group_id is not None:
            LOG.debug("Load balancer is using anti-affinity. Skipping spares "
                      "pool allocation.")
            return None

        vthunder = self.vthunder_repo.getVThunderByProjectID(
            db_apis.get_session(),
            loadbalancer.project_id)
            
        if vthunder is None:
            LOG.debug("No Amphora available for load balancer with id %s",
                      loadbalancer.id)
            return None

        return vthunder.id
