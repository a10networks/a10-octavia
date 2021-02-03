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
import json
import sqlalchemy
from sqlalchemy.orm.exc import NoResultFound

from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import uuidutils
from taskflow import task
from taskflow.types import failure

from octavia.common import constants
from octavia.db import api as db_apis
from octavia.db import repositories as repo

from a10_octavia.common import a10constants
from a10_octavia.common import exceptions
from a10_octavia.common import utils
from a10_octavia.db import repositories as a10_repo

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class BaseDatabaseTask(task.Task):
    """Base task to load drivers common to the tasks."""

    def __init__(self, **kwargs):
        self.repos = repo.Repositories()
        self.vthunder_repo = a10_repo.VThunderRepository()
        self.vrid_repo = a10_repo.VRIDRepository()
        self.amphora_repo = repo.AmphoraRepository()
        self.member_repo = a10_repo.MemberRepository()
        self.loadbalancer_repo = a10_repo.LoadBalancerRepository()
        self.vip_repo = repo.VipRepository()
        self.listener_repo = repo.ListenerRepository()
        self.flavor_repo = repo.FlavorRepository()
        self.flavor_profile_repo = repo.FlavorProfileRepository()
        self.nat_pool_repo = a10_repo.NatPoolRepository()
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
            LOG.error(
                "Failed to delete vThunder entry for load balancer: %s",
                loadbalancer.id)


class CheckExistingProjectToThunderMappedEntries(BaseDatabaseTask):
    """ Check existing Thunder entry with same project id.
        If exists, ensure the existing IPAddress:Partition
        is used to configure, otherwise Raise ConfigValueError
    """

    def execute(self, loadbalancer, vthunder_config):
        hierarchical_mt = vthunder_config.hierarchical_multitenancy
        if hierarchical_mt == 'enable':
            vthunder_config.partition_name = loadbalancer.project_id[:14]
            if CONF.a10_global.use_parent_partition:
                parent_project_id = utils.get_parent_project(
                    vthunder_config.project_id)
                if parent_project_id:
                    if parent_project_id != 'default':
                        vthunder_config.partition_name = parent_project_id[:14]
                else:
                    LOG.error(
                        "The parent project for project %s does not exist. ",
                        vthunder_config.project_id)
                    raise exceptions.ParentProjectNotFound(
                        vthunder_config.project_id)
            else:
                LOG.warning(
                    "Hierarchical multitenancy is disabled, use_parent_partition "
                    "configuration will not be applied for loadbalancer: %s",
                    loadbalancer.id)
        vthunder_ids = self.vthunder_repo.get_vthunders_by_project_id(
            db_apis.get_session(),
            project_id=loadbalancer.project_id)

        for vthunder_id in vthunder_ids:
            vthunder = self.vthunder_repo.get(
                db_apis.get_session(),
                id=vthunder_id)
            if vthunder is None:
                return
            existing_ip_addr_partition = '{}:{}'.format(
                vthunder.ip_address, vthunder.partition_name)
            config_ip_addr_partition = '{}:{}'.format(
                vthunder_config.ip_address, vthunder_config.partition_name)
            if existing_ip_addr_partition != config_ip_addr_partition:
                raise exceptions.ThunderInUseByExistingProjectError(
                    config_ip_addr_partition, existing_ip_addr_partition, loadbalancer.project_id)
        return vthunder_config


class CheckExistingThunderToProjectMappedEntries(BaseDatabaseTask):
    """ Check for all existing Thunder entries to ensure
        all belong to different projects, otherwise
        raise ConfigValueError
    """

    def execute(self, loadbalancer, vthunder_config):
        hierarchical_mt = vthunder_config.hierarchical_multitenancy
        if hierarchical_mt == 'enable' and CONF.a10_global.use_parent_partition:
            return
        vthunder_ids = self.vthunder_repo.get_vthunders_by_ip_address(
            db_apis.get_session(),
            ip_address=vthunder_config.ip_address)

        for vthunder_id in vthunder_ids:
            vthunder = self.vthunder_repo.get(
                db_apis.get_session(),
                id=vthunder_id)
            if vthunder is None:
                return

            existing_ip_addr_partition = '{}:{}'.format(
                vthunder.ip_address, vthunder.partition_name)
            config_ip_addr_partition = '{}:{}'.format(
                vthunder_config.ip_address, vthunder_config.partition_name)
            if existing_ip_addr_partition == config_ip_addr_partition:
                if loadbalancer.project_id not in (vthunder.project_id,
                                                   utils.get_parent_project(vthunder.project_id)):
                    raise exceptions.ProjectInUseByExistingThunderError(
                        config_ip_addr_partition, vthunder.project_id, loadbalancer.project_id)


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
    """Get VThunder from db using LoadBalancer"""

    def execute(self, loadbalancer):
        loadbalancer_id = loadbalancer.id
        vthunder = self.vthunder_repo.get_vthunder_from_lb(
            db_apis.get_session(), loadbalancer_id)
        if vthunder is None:
            return None
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
            self.vthunder_repo.update(
                db_apis.get_session(),
                vthunder.id,
                status="USED_SPARE",
                updated_at=datetime.utcnow())
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
            vthunder = self.vthunder_repo.get_spare_vthunder(
                db_apis.get_session())
            if vthunder is None:
                LOG.debug("No Amphora available for load balancer with id %s",
                          loadbalancer.id)
                return None

        return vthunder.id


class CreateRackVthunderEntry(BaseDatabaseTask):
    """ Create VThunder device entry in DB """

    def execute(self, loadbalancer, vthunder_config):
        hierarchical_mt = vthunder_config.hierarchical_multitenancy
        try:
            vthunder = self.vthunder_repo.create(
                db_apis.get_session(),
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
                updated_at=datetime.utcnow(),
                partition_name=vthunder_config.partition_name,
                hierarchical_multitenancy=hierarchical_mt)
            LOG.info("Successfully created vthunder entry in database.")
            return vthunder
        except Exception as e:
            LOG.error(
                'Failed to create vThunder entry in db for load balancer: %s.',
                loadbalancer.id)
            raise e

    def revert(self, result, loadbalancer, vthunder_config, *args, **kwargs):
        if isinstance(result, failure.Failure):
            # This task's execute failed, so nothing needed to be done to
            # revert
            return

        LOG.warning(
            'Reverting create Rack VThunder in DB for load balancer: %s',
            loadbalancer.id)
        try:
            self.vthunder_repo.delete(
                db_apis.get_session(), loadbalancer_id=loadbalancer.id)
        except Exception:
            LOG.error(
                "Failed to delete vThunder entry for load balancer: %s",
                loadbalancer.id)


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
                self.vthunder_repo.update(
                    db_apis.get_session(),
                    vthunder.id,
                    status=status,
                    updated_at=datetime.utcnow())
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


class GetVRIDForLoadbalancerResource(BaseDatabaseTask):

    def execute(self, partition_project_list):
        if partition_project_list:
            try:
                vrid_list = self.vrid_repo.get_vrid_from_project_ids(
                    db_apis.get_session(), project_ids=partition_project_list)
                return vrid_list
            except Exception as e:
                LOG.exception(
                    "Failed to get VRID list for given project list  %s due to %s",
                    partition_project_list,
                    str(e))
                raise e


class UpdateVRIDForLoadbalancerResource(BaseDatabaseTask):

    def execute(self, lb_resource, vrid_list):
        if not vrid_list:
            # delete all vrids from DB for the lB resource's project.
            try:
                self.vrid_repo.delete(db_apis.get_session(),
                                      project_id=lb_resource.project_id)
                LOG.debug("Successfully deleted DB vrid from project %s",
                          lb_resource.project_id)
            except Exception as e:
                LOG.error(
                    "Failed to delete VRID data for project %s due to %s",
                    lb_resource.project_id,
                    str(e))
                raise e
            return
        for vrid in vrid_list:
            if self.vrid_repo.exists(db_apis.get_session(), vrid.id):
                try:
                    self.vrid_repo.update(
                        db_apis.get_session(),
                        vrid.id,
                        vrid_floating_ip=vrid.vrid_floating_ip,
                        vrid_port_id=vrid.vrid_port_id,
                        vrid=vrid.vrid,
                        subnet_id=vrid.subnet_id)
                    LOG.debug(
                        "Successfully updated DB vrid %s entry for loadbalancer resource %s",
                        vrid.id,
                        lb_resource.id)
                except Exception as e:
                    LOG.error(
                        "Failed to update VRID data for VRID FIP %s due to %s",
                        vrid.vrid_floating_ip,
                        str(e))
                    raise e

            else:
                try:
                    self.vrid_repo.create(
                        db_apis.get_session(),
                        project_id=vrid.project_id,
                        vrid_floating_ip=vrid.vrid_floating_ip,
                        vrid_port_id=vrid.vrid_port_id,
                        vrid=vrid.vrid,
                        subnet_id=vrid.subnet_id)
                except Exception as e:
                    LOG.error(
                        "Failed to create VRID data for VRID FIP %s due to %s",
                        vrid.vrid_floating_ip,
                        str(e))
                    raise e


class CountLoadbalancersInProjectBySubnet(BaseDatabaseTask):

    def execute(self, subnet, partition_project_list):
        if partition_project_list:
            try:
                return self.loadbalancer_repo.get_lb_count_by_subnet(
                    db_apis.get_session(),
                    project_ids=partition_project_list, subnet_id=subnet.id)
            except Exception as e:
                LOG.exception("Failed to get LB count for subnet %s due to %s ",
                              subnet.id, str(e))
                raise e
        return 0


class CountMembersInProjectBySubnet(BaseDatabaseTask):

    def execute(self, subnet, partition_project_list):
        if partition_project_list:
            try:
                return self.member_repo.get_member_count_by_subnet(
                    db_apis.get_session(),
                    project_ids=partition_project_list, subnet_id=subnet.id)
            except Exception as e:
                LOG.exception(
                    "Failed to get LB member count for subnet %s due to %s",
                    subnet.id, str(e))
                raise e
        return 0


class DeleteVRIDEntry(BaseDatabaseTask):
    def execute(self, vrid, delete_vrid):
        if vrid and delete_vrid:
            try:
                self.vrid_repo.delete(db_apis.get_session(), id=vrid.id)
            except Exception as e:
                LOG.exception(
                    "Failed to delete VRID entry from vrid table: %s", str(e))
                raise e


class DeleteMultiVRIDEntry(BaseDatabaseTask):
    def execute(self, vrid_list):
        if vrid_list:
            try:
                self.vrid_repo.delete_batch(
                    db_apis.get_session(), ids=[
                        vrid.id for vrid in vrid_list])
            except Exception as e:
                LOG.exception(
                    "Failed to delete VRID entry from vrid table: %s", str(e))
                raise e


class CheckVLANCanBeDeletedParent(object):
    """ Checks all vip and member subnet_ids for project ID"""

    def is_vlan_deletable(self, project_id, subnet_id, is_vip):
        if project_id not in CONF.rack_vthunder.devices:
            return False

        subnet_usage_count = 0

        lbs = db_apis.get_session().query(self.loadbalancer_repo.model_class).filter(
            self.loadbalancer_repo.model_class.project_id == project_id).all()
        for lb in lbs:
            vips = db_apis.get_session().query(
                self.vip_repo.model_class).filter(
                self.vip_repo.model_class.load_balancer_id == lb.id).all()
            for vip in vips:
                if vip.subnet_id == subnet_id:
                    subnet_usage_count += 1

        members = db_apis.get_session().query(
            self.member_repo.model_class).filter(
            self.member_repo.model_class.project_id == project_id).all()
        for member in members:
            if member.subnet_id == subnet_id:
                subnet_usage_count += 1

        if is_vip and subnet_usage_count == 1:
            return True
        elif subnet_usage_count == 0:
            return True

        return False


class CheckVipVLANCanBeDeleted(CheckVLANCanBeDeletedParent, BaseDatabaseTask):
    default_provides = a10constants.DELETE_VLAN

    def execute(self, loadbalancer):
        return self.is_vlan_deletable(loadbalancer.project_id,
                                      loadbalancer.vip.subnet_id,
                                      True)


class CheckMemberVLANCanBeDeleted(
        CheckVLANCanBeDeletedParent,
        BaseDatabaseTask):
    default_provides = a10constants.DELETE_VLAN

    def execute(self, member):
        return self.is_vlan_deletable(
            member.project_id, member.subnet_id, False)


class MarkLBAndListenerActiveInDB(BaseDatabaseTask):
    """Mark the load balancer and specified listener active in the DB"""

    def execute(self, loadbalancer, listener):
        """Mark the load balancer and listener as active in DB"""

        self.loadbalancer_repo.update(db_apis.get_session(),
                                      loadbalancer.id,
                                      provisioning_status=constants.ACTIVE)
        self.listener_repo.prov_status_active_if_not_error(
            db_apis.get_session(), listener.id)

    def revert(self, loadbalancer, listener, *args, **kwargs):
        """Mark the load balancer and listener in error state"""
        try:
            self.loadbalancer_repo.update(db_apis.get_session(),
                                          id=loadbalancer.id,
                                          provisioning_status=constants.ERROR)
        except Exception as e:
            LOG.error("Failed to update load balancer %(lb) "
                      "provisioning status to ERROR due to: "
                      "%(except)s", {'lb': loadbalancer.id, 'except': e})
        try:
            self.listener_repo.update(db_apis.get_session(),
                                      id=listener.id,
                                      provisioning_status=constants.ERROR)
        except Exception as e:
            LOG.error("Failed to update listener %(list) "
                      "provisioning status to ERROR due to: "
                      "%(except)s", {'list': listener.id, 'except': e})


# class GetVRIDForLBResourceSubnet(BaseDatabaseTask):
#     def execute(self, lb_resource, subnet):
#         project_id = lb_resource.project_id
#         vrid = self.vrid_repo.get_vrid_for_subnet(
#             db_apis.get_session(), project_id=project_id, subnet_id=subnet.id)
#         return vrid


class CountMembersWithIP(BaseDatabaseTask):
    def execute(self, member):
        try:
            return self.member_repo.get_member_count_by_ip_address(
                db_apis.get_session(), member.ip_address, member.project_id)
        except Exception as e:
            LOG.exception(
                "Failed to get count of members with given IP for a pool: %s",
                str(e))
            raise e


class CountMembersWithIPPortProtocol(BaseDatabaseTask):
    def execute(self, member, pool):
        try:
            return self.member_repo.get_member_count_by_ip_address_port_protocol(
                db_apis.get_session(), member.ip_address, member.project_id,
                member.protocol_port, pool.protocol)
        except Exception as e:
            LOG.exception(
                "Failed to get count of members with given IP fnd port for a pool: %s",
                str(e))
            raise e


class PoolCountforIP(BaseDatabaseTask):
    def execute(self, member):
        try:
            return self.member_repo.get_pool_count_by_ip(
                db_apis.get_session(), member.ip_address, member.project_id)
        except Exception as e:
            LOG.exception(
                "Failed to get pool count with same IP address: %s",
                str(e))
            raise e


class GetSubnetForDeletionInPool(BaseDatabaseTask):

    def execute(self, member_list, partition_project_list):
        """

        :param member_list: Receives the list of members, under specific pool.
        :param partition_project_list: list of projects under partition.
        :return: returns the list subnet those used in a pool's members only.
        Description: Iterates over the member list, to check if member's  subnet is
        anywhere else, along with pool count is also takes LB into account.
        """
        try:
            subnet_list = []
            member_subnet = []
            for member in member_list:
                if member.subnet_id not in member_subnet:
                    pool_count_subnet = self.member_repo.get_pool_count_subnet(
                        db_apis.get_session(), partition_project_list, member.subnet_id)
                    lb_count_subnet = self.loadbalancer_repo.get_lb_count_by_subnet(
                        db_apis.get_session(), partition_project_list, member.subnet_id)
                    if pool_count_subnet <= 1 and lb_count_subnet == 0:
                        subnet_list.append(member.subnet_id)
                    member_subnet.append(member.subnet_id)
            return subnet_list
        except Exception as e:
            LOG.exception("Failed to get subnet list for members: %s", str(e))
            raise e


class GetChildProjectsOfParentPartition(BaseDatabaseTask):

    def execute(self, lb_resource, vthunder):
        if vthunder:
            try:
                partition_project_list = self.vthunder_repo.get_project_list_using_partition(
                    db_apis.get_session(),
                    partition_name=vthunder.partition_name,
                    ip_address=vthunder.ip_address)
                return partition_project_list
            except Exception as e:
                LOG.exception(
                    "Failed to fetch list of projects, if multi-tenancy and use parent partition "
                    "is enabled due to %s", str(e))
                raise e


class GetFlavorData(BaseDatabaseTask):

    def _flavor_search(self, lb_resource):
        if hasattr(lb_resource, 'flavor_id'):
            return lb_resource.flavor_id
        elif hasattr(lb_resource, 'pool'):
            return self._flavor_search(lb_resource.pool)
        elif hasattr(lb_resource, 'load_balancer'):
            return self._flavor_search(lb_resource.load_balancer)
        return None

    def _format_keys(self, flavor_data):
        if type(flavor_data) is list:
            item_list = []
            for item in flavor_data:
                item_list.append(self._format_keys(item))
            return item_list
        elif type(flavor_data) is dict:
            item_dict = {}
            for k, v in flavor_data.items():
                item_dict[k.replace('-', '_')] = self._format_keys(v)
            return item_dict
        else:
            return flavor_data

    def execute(self, lb_resource):
        flavor_id = self._flavor_search(lb_resource)
        if flavor_id:
            flavor = self.flavor_repo.get(db_apis.get_session(), id=flavor_id)
            if flavor and flavor.flavor_profile_id:
                flavor_profile = self.flavor_profile_repo.get(
                    db_apis.get_session(),
                    id=flavor.flavor_profile_id)
                flavor_data = json.loads(flavor_profile.flavor_data)
                return self._format_keys(flavor_data)


class GetNatPoolEntry(BaseDatabaseTask):

    def execute(self, member, nat_flavor=None):
        if nat_flavor and 'pool_name' in nat_flavor:
            try:
                return self.nat_pool_repo.get(db_apis.get_session(), name=nat_flavor['pool_name'],
                                              subnet_id=member.subnet_id)
            except Exception as e:
                LOG.exception("Failed to fetch subnet %s NAT pool %s entry from database: %s",
                              nat_flavor['pool_name'], member.subnet_id, str(e))
                raise e


class UpdateNatPoolDB(BaseDatabaseTask):

    def execute(self, member, nat_flavor=None, nat_pool=None, subnet_port=None):
        if nat_flavor is None:
            return

        if nat_pool is None:
            if subnet_port is None:
                # NAT pool addresses are not in member subnet. a10-octavia allows it
                # but not able to reerve ip for it. So, no database entry is needed.
                return

            try:
                id = uuidutils.generate_uuid()
                pool_name = nat_flavor.get('pool_name')
                subnet_id = member.subnet_id
                start_address = nat_flavor.get('start_address')
                end_address = nat_flavor.get('end_address')
                port_id = subnet_port.id
                self.nat_pool_repo.create(
                    db_apis.get_session(), id=id, name=pool_name, subnet_id=subnet_id,
                    start_address=start_address, end_address=end_address,
                    member_ref_count=1, port_id=port_id)
                LOG.info("Successfully created nat pool entry in database.")
            except Exception as e:
                LOG.exception("Failed to create subnet %s NAT pool %s entry to database: %s",
                              subnet_id, pool_name, str(e))
                raise e
        else:
            try:
                ref = nat_pool.member_ref_count + 1
                self.nat_pool_repo.update(
                    db_apis.get_session(), nat_pool.id, member_ref_count=ref)
            except Exception as e:
                LOG.exception("Failed to update NAT pool entry %s to database: %s",
                              nat_pool.id, str(e))
                raise e


class DeleteNatPoolEntry(BaseDatabaseTask):

    def execute(self, nat_pool=None):
        if nat_pool is None:
            return

        if nat_pool.member_ref_count > 1:
            try:
                ref = nat_pool.member_ref_count - 1
                self.nat_pool_repo.update(
                    db_apis.get_session(), nat_pool.id, member_ref_count=ref)
            except Exception as e:
                LOG.exception("Failed to update NAT pool entry %s to database: %s",
                              nat_pool.id, str(e))
                raise e
        else:
            try:
                self.nat_pool_repo.delete(db_apis.get_session(), id=nat_pool.id)
                LOG.info("Successfully deleted nat pool entry in database.")
            except Exception as e:
                LOG.exception("Failed to delete NAT pool entry %s to database: %s",
                              nat_pool.id, str(e))
                raise e


class CountLoadbalancersWithFlavor(BaseDatabaseTask):

    def execute(self, loadbalancer):
        try:
            return self.loadbalancer_repo.get_lb_count_by_flavor(
                db_apis.get_session(),
                loadbalancer.project_id, loadbalancer.flavor_id)
        except Exception as e:
            LOG.exception("Failed to get LB count for flavor %s due to %s ",
                          loadbalancer.flavor_id, str(e))
            raise e
        return 0


class SetThunderUpdatedAt(BaseDatabaseTask):

    def execute(self, vthunder):
        try:
            if vthunder:
                LOG.debug("Updated the updated_at field for thunder : {}:{}"
                          .format(vthunder.ip_address, vthunder.partition_name))
                self.vthunder_repo.update(
                    db_apis.get_session(),
                    vthunder.id,
                    updated_at=datetime.utcnow())
        except Exception as e:
            LOG.exception('Failed to set updated_at field for thunder due to: {}'
                          ', skipping.'.format(str(e)))


class SetThunderLastWriteMem(BaseDatabaseTask):

    def execute(self, vthunder, write_mem_shared=False, write_mem_private=False):
        if write_mem_shared is False or write_mem_private is False:
            return
        try:
            if vthunder:
                LOG.debug("Updated the last_write_mem field for thunder : {}:{}"
                          .format(vthunder.ip_address, vthunder.partition_name))
                self.vthunder_repo.update_last_write_mem(
                    db_apis.get_session(),
                    vthunder.ip_address,
                    vthunder.partition_name,
                    last_write_mem=datetime.utcnow())
        except Exception as e:
            LOG.exception('Failed to set last_write_mem field for thunder due to: {}'
                          ', skipping.'.format(str(e)))


class GetActiveLoadBalancersByThunder(BaseDatabaseTask):

    def execute(self, vthunder):
        try:
            if vthunder:
                loadbalancers_list = self.loadbalancer_repo.get_active_lbs_by_thunder(
                    db_apis.get_session(),
                    vthunder)
                return loadbalancers_list
        except Exception as e:
            LOG.exception('Failed to get active Loadbalancers related to thunder '
                          'due to: {}'.format(str(e)))


class MarkLoadBalancersPendingUpdateInDB(BaseDatabaseTask):

    def execute(self, loadbalancers_list):
        try:
            for lb in loadbalancers_list:
                if lb.provisioning_status == constants.ERROR:
                    continue
                self.loadbalancer_repo.update(
                    db_apis.get_session(),
                    lb.id,
                    provisioning_status='PENDING_UPDATE')
        except Exception as e:
            LOG.exception('Failed to set Loadbalancers to PENDING_UPDATE due to '
                          ': {}'.format(str(e)))


class MarkLoadBalancersActiveInDB(BaseDatabaseTask):

    def execute(self, loadbalancers_list):
        try:
            for lb in loadbalancers_list:
                if lb.provisioning_status == constants.ERROR:
                    continue
                self.loadbalancer_repo.update(
                    db_apis.get_session(),
                    lb.id,
                    provisioning_status='ACTIVE')
        except Exception as e:
            LOG.exception('Failed to set Loadbalancers to ACTIVE due to '
                          ': {}'.format(str(e)))
