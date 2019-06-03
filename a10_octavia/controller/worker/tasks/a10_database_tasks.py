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
from a10_octavia.db import repositories as repo2
from octavia.api.drivers import driver_lib

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class BaseDatabaseTask(task.Task):
    """Base task to load drivers common to the tasks."""

    def __init__(self, **kwargs):
        self.repos = repo.Repositories()
        self.amphora_repo = repo.AmphoraRepository()
        self.task_utils = task_utilities.TaskUtils()
        self._octavia_driver_db = driver_lib.DriverLibrary()
        super(BaseDatabaseTask, self).__init__(**kwargs)


class CreateVThunderInDB(BaseDatabaseTask):
    """Task to create an initial vthunder entry in the Database."""

    def execute(self, load_balancer_ip, cached_zone, *args, **kwargs):
        """Creates an pending create vthunder record in the database.

        :returns: The created vthunder object id
        """

        amphora = self.amphora_repo.create(db_apis.get_session(),
                                           id=uuidutils.generate_uuid(),
                                           lb_network_ip=load_balancer_ip,
                                           status=constants.PENDING_CREATE,
                                           cert_busy=False,
                                           cached_zone=cached_zone)

        LOG.info("Created vThunder in DB with id %s", amphora.id)
        return amphora.id

class GetVThunderFromDB(BaseDatabaseTask):
    """Get VThunder details from the database"""

    def execute(self, vthuder_id):
        """reads the entry from Amphora database for VThunder

        :returns: The VThunder object molded as amphora
        """

        vthunder = self.amphora_repo.get(db_apis.get_session(), id=vthuder_id)

        LOG.info("Get VThunder in DB with id %s", vthuder_id)
        return vthunder

class UpdateLBStatusTask(BaseDatabaseTask):
    """ update loadbalancer status in database """
    def execute(self, status):
        self._octavia_driver_db.update_loadbalancer_status(status)
        LOG.info("here comes the status")
        LOG.info(str(status))
        LOG.info("updated the DB status in here")

class TestVThunderTask(BaseDatabaseTask):
    """Test Vthunder entry"""
    def execute(self, amphora):
        vthunder_repo = repo2.VThunderRepository()
        vthunder = vthunder_repo.get(db_apis.get_session(), id=123)
        LOG.info("check this vthunder bro" ) 
        return vthunder

class CreateVThunderinDBTask(BaseDatabaseTask):
    """ Create VThunder device entry in DB"""
    def execute(self, amphora):
        vthunder_repo = repo2.VThunderRepository()
        vthunder = vthunder_repo.create(db_apis.get_session(), id="321", amphora_id="someid",
                                        device_name="device1", username="uysername", 
                                        password="pass", ip_address="10.43.2.122",
                                        undercloud=False, axapi_version=30, loadbalancer_id="lbid")
        LOG.info("successfully created vthunder entry in database.")
