#    Copyright 2019, A10 Networks
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


from datetime import datetime
import sqlalchemy
from sqlalchemy.orm.exc import NoResultFound

from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import uuidutils
from taskflow import task

from octavia.common import constants
from octavia.db import api as db_apis
from octavia.db import repositories as repo

from a10_octavia.db import repositories as a10_repo

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

    """Test VThunder entry"""

    def execute(self, amphora):
        vthunder = self.vthunder_repo.get(db_apis.get_session(), id=123)
        return vthunder


class CreateVThunderEntry(BaseDatabaseTask):

    """ Create VThunder device entry in DB"""

    def execute(self, amphora, loadbalancer, role, status):
        vthunder_id = uuidutils.generate_uuid()

        username = CONF.vthunder.default_vthunder_username
        password = CONF.vthunder.default_vthunder_password
        axapi_version = CONF.vthunder.default_axapi_version

        if role == constants.ROLE_MASTER:
            topology = "ACTIVE_STANDBY"
            role = "MASTER"
        elif role == constants.ROLE_BACKUP:
            topology = "ACTIVE_STANDBY"
            role = "BACKUP"
        else:
            topology = "STANDALONE"
            role = "MASTER"

        self.vthunder_repo.create(
            db_apis.get_session(), vthunder_id=vthunder_id,
            amphora_id=amphora.id,
            device_name=vthunder_id, username=username,
            password=password, ip_address=amphora.lb_network_ip,
            undercloud=False, axapi_version=axapi_version,
            loadbalancer_id=loadbalancer.id,
            project_id=loadbalancer.project_id,
            compute_id=amphora.compute_id,
            topology=topology,
            role=role,
            last_udp_update=datetime.utcnow(),
            status=status,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow())

        LOG.info("Successfully created vthunder entry in database.")

    def revert(self, amphora, loadbalancer, role, status=constants.ACTIVE,
               *args, **kwargs):
        try:
            self.vthunder_repo.delete(
                db_apis.get_session(), loadbalancer_id=loadbalancer.id)
        except NoResultFound:
            LOG.error("Failed to delete vThunder entry for load balancer: %s", loadbalancer.id)


class DeleteVThunderEntry(BaseDatabaseTask):

    """ Delete VThunder device entry in DB  """

    def execute(self, loadbalancer):
        try:
            self.vthunder_repo.delete(
                db_apis.get_session(), loadbalancer_id=loadbalancer.id)
        except NoResultFound:
            pass
        LOG.info("Successfully deleted vthunder entry in database.")


class GetVThunderByLoadBalancer(BaseDatabaseTask):

    """ Get VThunder details from LoadBalancer"""

    def execute(self, loadbalancer):
        loadbalancer_id = loadbalancer.id
        vthunder = self.vthunder_repo.get_vthunder_from_lb(
            db_apis.get_session(), loadbalancer_id)
        LOG.info("Successfully fetched vThunder details for LB")
        return vthunder


class GetBackupVThunderByLoadBalancer(BaseDatabaseTask):

    """ Get VThunder details from LoadBalancer"""

    def execute(self, loadbalancer):
        loadbalancer_id = loadbalancer.id
        vthunder = self.vthunder_repo.get_backup_vthunder_from_lb(
            db_apis.get_session(), loadbalancer_id)
        return vthunder
        LOG.info("Successfully fetched vThunder details for LB")

# class GetVThunderByLoadBalancerID(BaseDatabaseTask):
#     """ Get VThunder details from LoadBalancer ID """
#     def execute(self, loadbalancer_id):
#         vthunder = self.vthunder_repo.get_vthunder_from_lb(db_apis.get_session(), loadbalancer_id)
#         return vthunder
#         LOG.info("Successfully fetched vThunder details for LB")


class GetComputeForProject(BaseDatabaseTask):

    """ Get Compute details form Loadbalancer object -> project ID"""

    def execute(self, loadbalancer):
        vthunder = self.vthunder_repo.get_vthunder_by_project_id(
            db_apis.get_session(), loadbalancer.project_id)
        if vthunder is None:
            vthunder = self.vthunder_repo.get_spare_vthunder(
                db_apis.get_session())
            self.vthunder_repo.update(db_apis.get_session(), vthunder.id,
                                      status="USED_SPARE", updated_at=datetime.utcnow())
        amphora_id = vthunder.amphora_id
        self.amphora_repo.get(db_apis.get_session(), id=amphora_id)
        compute_id = vthunder.compute_id
        return compute_id


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

        vthunder = self.vthunder_repo.get_vthunder_by_project_id(
            db_apis.get_session(),
            loadbalancer.project_id)

        if vthunder is None:
            # Check for spare vthunder
            vthunder = self.vthunder_repo.get_spare_vthunder(db_apis.get_session())
            if vthunder is None:
                LOG.debug("No Amphora available for load balancer with id %s",
                          loadbalancer.id)
                return None

        return vthunder.id


class CreateRackVthunderEntry(BaseDatabaseTask):

    """ Create VThunder device entry in DB """

    def execute(self, loadbalancer, vthunder_config):
        self.vthunder_repo.create(db_apis.get_session(),
                                  vthunder_id=uuidutils.generate_uuid(),
                                  device_name=vthunder_config.device_name,
                                  username=vthunder_config.username,
                                  password=vthunder_config.password,
                                  ip_address=vthunder_config.ip_address,
                                  undercloud=vthunder_config.undercloud,
                                  loadbalancer_id=loadbalancer.id,
                                  project_id=vthunder_config.project_id,
                                  axapi_version=vthunder_config.axapi_version,
                                  topology="STANDALONE",
                                  role="MASTER",
                                  status="ACTIVE",
                                  last_udp_update=datetime.utcnow(),
                                  created_at=datetime.utcnow(),
                                  updated_at=datetime.utcnow())
        LOG.info("Successfully created vthunder entry in database.")


class CreateVThunderHealthEntry(BaseDatabaseTask):

    """ Create VThunder Health entry in DB """

    def execute(self, loadbalancer, vthunder_config):
        self.vthunder_repo.create(db_apis.get_session(),
                                  vthunder_id=uuidutils.generate_uuid(),
                                  device_name=vthunder_config.device_name,
                                  username=vthunder_config.username,
                                  password=vthunder_config.password,
                                  ip_address=vthunder_config.ip_address,
                                  undercloud=vthunder_config.undercloud,
                                  loadbalancer_id=loadbalancer.id,
                                  project_id=vthunder_config.project_id,
                                  axapi_version=vthunder_config.axapi_version,
                                  topology="STANDALONE",
                                  role="MASTER")
        LOG.info("Successfully created vthunder entry in database.")


class MarkVThunderStatusInDB(BaseDatabaseTask):

    def execute(self, vthunder, status):
        try:
            if vthunder:
                self.vthunder_repo.update(db_apis.get_session(),
                                          vthunder.id,
                                          status=status, updated_at=datetime.utcnow())
        except (sqlalchemy.orm.exc.NoResultFound,
                sqlalchemy.orm.exc.UnmappedInstanceError):
            LOG.debug('No existing amphora health record to mark busy '
                      'for amphora: %s, skipping.', vthunder.id)


class CreateSpareVThunderEntry(BaseDatabaseTask):

    def execute(self, amphora):
        vthunder_id = uuidutils.generate_uuid()

        username = CONF.vthunder.default_vthunder_username
        password = CONF.vthunder.default_vthunder_password
        axapi_version = CONF.vthunder.default_axapi_version
        vthunder = self.vthunder_repo.create(
            db_apis.get_session(), vthunder_id=vthunder_id,
            amphora_id=amphora.id,
            device_name=vthunder_id, username=username,
            password=password, ip_address=amphora.lb_network_ip,
            undercloud=False, axapi_version=axapi_version,
            loadbalancer_id=None,
            project_id=None,
            compute_id=amphora.compute_id,
            topology="SINGLE",
            role="MASTER",
            status="READY",
            created_at=datetime.utcnow(),
            last_udp_update=datetime.utcnow(),
            updated_at=datetime.utcnow())
        LOG.info("Successfully created vthunder entry in database.")
        return vthunder
