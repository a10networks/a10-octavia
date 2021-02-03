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


import datetime

from oslo_config import cfg
from oslo_log import log as logging
from sqlalchemy.orm import noload
from sqlalchemy import or_
from sqlalchemy import and_

from octavia.common import constants as consts
from octavia.db import models as base_models
from octavia.db import repositories as repo

from a10_octavia.db import models

CONF = cfg.CONF

LOG = logging.getLogger(__name__)


class BaseRepository(object):
    model_class = None

    def count(self, session, **filters):
        """Retrieves a count of entities from the database.

        :param session: A Sql Alchemy database session.
        :param filters: Filters to decide which entities should be retrieved.
        :returns: int
        """
        return session.query(self.model_class).filter_by(**filters).count()

    def create(self, session, **model_kwargs):
        """Base create method for a database entity.

        :param session: A Sql Alchemy database session.
        :param model_kwargs: Attributes of the model to insert.
        :returns: octavia.common.data_model
        """
        with session.begin(subtransactions=True):
            model = self.model_class(**model_kwargs)
            session.add(model)
        return model.to_data_model()

    def delete(self, session, **filters):
        """Deletes entities from the database.

        :param session: A Sql Alchemy database session.
        :param filters: Filters to decide which entity should be deleted.
        :returns: None
        :raises: sqlalchemy.orm.exc.NoResultFound
        """
        models = session.query(self.model_class).filter_by(**filters).all()
        for model in models:
            with session.begin(subtransactions=True):
                session.delete(model)
                session.flush()

    def delete_batch(self, session, ids=None):
        """Batch deletes by entity ids."""
        ids = ids or []
        for id in ids:
            self.delete(session, id=id)

    def update(self, session, id, **model_kwargs):
        """Updates an entity in the database.

        :param session: A Sql Alchemy database session.
        :param model_kwargs: Entity attributes that should be updates.
        :returns: octavia.common.data_model
        """
        with session.begin(subtransactions=True):
            session.query(self.model_class).filter_by(
                id=id).update(model_kwargs)

    def get(self, session, **filters):
        """Retrieves an entity from the database.

        :param session: A Sql Alchemy database session.
        :param filters: Filters to decide which entity should be retrieved.
        :returns: octavia.common.data_model
        """
        deleted = filters.pop('show_deleted', True)
        model = session.query(self.model_class).filter_by(**filters)

        if not deleted:
            if hasattr(self.model_class, 'status'):
                model = model.filter(
                    self.model_class.status != consts.DELETED)
            else:
                model = model.filter(
                    self.model_class.provisioning_status != consts.DELETED)

        model = model.first()

        if not model:
            return None

        return model.to_data_model()

    def get_all(self, session, pagination_helper=None,
                query_options=None, **filters):
        """Retrieves a list of entities from the database.

        :param session: A Sql Alchemy database session.
        :param pagination_helper: Helper to apply pagination and sorting.
        :param query_options: Optional query options to apply.
        :param filters: Filters to decide which entities should be retrieved.
        :returns: [octavia.common.data_model]
        """
        deleted = filters.pop('show_deleted', True)
        query = session.query(self.model_class).filter_by(**filters)
        if query_options:
            query = query.options(query_options)

        if not deleted:
            if hasattr(self.model_class, 'status'):
                query = query.filter(
                    self.model_class.status != consts.DELETED)
            else:
                query = query.filter(
                    self.model_class.provisioning_status != consts.DELETED)

        if pagination_helper:
            model_list, links = pagination_helper.apply(
                query, self.model_class)
        else:
            links = None
            model_list = query.all()

        data_model_list = [model.to_data_model() for model in model_list]
        return data_model_list, links

    def exists(self, session, id):
        """Determines whether an entity exists in the database by its id.

        :param session: A Sql Alchemy database session.
        :param id: id of entity to check for existence.
        :returns: octavia.common.data_model
        """
        return bool(session.query(self.model_class).filter_by(id=id).first())

    def get_all_deleted_expiring(self, session, exp_age):
        """Get all previously deleted resources that are now expiring.

        :param session: A Sql Alchemy database session.
        :param exp_age: A standard datetime delta which is used to see for how
                        long can a resource live without updates before
                        it is considered expired
        :returns: A list of resource IDs
                """

        expiry_time = datetime.datetime.utcnow() - exp_age

        query = session.query(self.model_class).filter(
            self.model_class.updated_at < expiry_time)
        if hasattr(self.model_class, 'status'):
            query = query.filter_by(status=consts.DELETED)
        else:
            query = query.filter_by(provisioning_status=consts.DELETED)
        # Do not load any relationship
        query = query.options(noload('*'))
        model_list = query.all()

        id_list = [model.id for model in model_list]
        return id_list


class VThunderRepository(BaseRepository):
    model_class = models.VThunder

    def get_recently_updated_thunders(self, session):
        query = session.query(self.model_class).filter(
            or_(self.model_class.updated_at >= self.model_class.last_write_mem,
                self.model_class.last_write_mem == None)).filter(
            or_(self.model_class.status == 'ACTIVE', self.model_class.status == 'DELETED'))
        query = query.options(noload('*'))
        return query.all()

    def get_stale_vthunders(self, session, initial_setup_wait_time, failover_wait_time):
        model = session.query(self.model_class).filter(
            self.model_class.created_at < initial_setup_wait_time).filter(
            self.model_class.last_udp_update < failover_wait_time).filter(
            self.model_class.status == 'ACTIVE').filter(
            or_(self.model_class.role == "MASTER",
                self.model_class.role == "BACKUP")).first()
        if model is None:
            return None
        return model.to_data_model()

    def get_vthunder_from_lb(self, session, lb_id):
        model = session.query(self.model_class).filter(
            self.model_class.loadbalancer_id == lb_id).filter(
            or_(self.model_class.role == "STANDALONE",
                self.model_class.role == "MASTER")).first()

        if not model:
            return None

        return model.to_data_model()

    def get_backup_vthunder_from_lb(self, session, lb_id):
        model = session.query(self.model_class).filter(
            self.model_class.loadbalancer_id == lb_id).filter(
            or_(self.model_class.role == "STANDALONE",
                self.model_class.role == "BACKUP")).first()

        if not model:
            return None

        return model.to_data_model()

    def get_vthunder_by_project_id(self, session, project_id):
        model = session.query(self.model_class).filter(
            self.model_class.project_id == project_id).filter(
            and_(self.model_class.status == "ACTIVE",
                 or_(self.model_class.role == "STANDALONE",
                     self.model_class.role == "MASTER"))).first()

        if not model:
            return None

        return model.to_data_model()

    def get_vthunders_by_project_id(self, session, project_id):
        model_list = session.query(self.model_class).filter(
            self.model_class.project_id == project_id).filter(
            and_(self.model_class.status == "ACTIVE",
                 or_(self.model_class.role == "STANDALONE",
                     self.model_class.role == "MASTER")))
        id_list = [model.id for model in model_list]
        return id_list

    def get_vthunders_by_ip_address(self, session, ip_address):
        model_list = session.query(self.model_class).filter(
            self.model_class.ip_address == ip_address).filter(
            and_(self.model_class.status == "ACTIVE",
                 or_(self.model_class.role == "STANDALONE",
                     self.model_class.role == "MASTER")))

        id_list = [model.id for model in model_list]
        return id_list

    def get_delete_compute_flag(self, session, compute_id):
        if compute_id:
            count = session.query(self.model_class).filter(
                self.model_class.compute_id == compute_id).count()
            if count < 2:
                return True

            else:
                return False
        else:
            return False

    def get_vthunder_from_src_addr(self, session, srcaddr):
        model = session.query(self.model_class).filter(
            self.model_class.ip_address == srcaddr).first()

        if not model:
            return None
        return model.id

    def get_spare_vthunder(self, session):
        model = session.query(self.model_class).filter(
            self.model_class.status == "READY").first()

        if not model:
            return None

        return model.to_data_model()

    def get_spare_vthunder_count(self, session):
        with session.begin(subtransactions=True):
            count = session.query(self.model_class).filter_by(
                status="READY", loadbalancer_id=None).count()

        return count

    def get_all_deleted_expiring(self, session, exp_age):

        expiry_time = datetime.datetime.utcnow() - exp_age

        query = session.query(self.model_class).filter(
            self.model_class.updated_at < expiry_time)
        if hasattr(self.model_class, 'status'):
            query = query.filter(or_(self.model_class.status == "USED_SPARE",
                                     self.model_class.status == consts.DELETED))
        else:
            query = query.filter_by(operating_status=consts.DELETED)
        # Do not load any relationship
        query = query.options(noload('*'))
        model_list = query.all()

        id_list = [model.id for model in model_list]
        return id_list

    def get_project_list_using_partition(self, session, partition_name, ip_address):
        queryset_vthunders = session.query(self.model_class.project_id.distinct()).filter(
            and_(self.model_class.partition_name == partition_name,
                 self.model_class.ip_address == ip_address,
                 or_(self.model_class.role == "STANDALONE",
                     self.model_class.role == "MASTER")))
        list_projects = [project[0] for project in queryset_vthunders]
        return list_projects

    def update_last_write_mem(self, session, ip_address, partition, **model_kwargs):
        with session.begin(subtransactions=True):
            session.query(self.model_class).filter_by(ip_address=ip_address, partition_name=partition).update(model_kwargs)


class LoadBalancerRepository(repo.LoadBalancerRepository):
    thunder_model_class = models.VThunder

    def get_active_lbs_by_thunder(self, session, vthunder):
        lb_list = []
        query = session.query(self.model_class).filter(
            and_(vthunder.loadbalancer_id == self.model_class.id,
                 self.model_class.provisioning_status == consts.ACTIVE))
        model_list = query.all()
        for data in model_list:
            lb_list.append(data.to_data_model())
        return lb_list

    def get_lb_count_by_subnet(self, session, project_ids, subnet_id):
        return session.query(self.model_class).join(base_models.Vip).filter(
            and_(self.model_class.project_id.in_(project_ids),
                 base_models.Vip.subnet_id == subnet_id,
                 or_(self.model_class.provisioning_status == consts.PENDING_DELETE,
                     self.model_class.provisioning_status == consts.ACTIVE))).count()

    def get_lb_count_by_flavor(self, session, project_id, flavor_id):
        return session.query(self.model_class).filter(
            self.model_class.project_id == project_id).filter(
                self.model_class.flavor_id == flavor_id,
                or_(self.model_class.provisioning_status == consts.PENDING_DELETE,
                    self.model_class.provisioning_status == consts.ACTIVE)).count()


class VRIDRepository(BaseRepository):
    model_class = models.VRID

    # A project can have multiple VRIDs, so need to convert each vrid object through
    # "to_data_model"
    def get_vrid_from_project_ids(self, session, project_ids):
        vrid_obj_list = []

        model = session.query(self.model_class).filter(
            self.model_class.project_id.in_(project_ids))
        for data in model:
            vrid_obj_list.append(data.to_data_model())

        return vrid_obj_list


class MemberRepository(repo.MemberRepository):

    def get_member_count(self, session, project_id):
        count = session.query(self.model_class).filter(
            and_(self.model_class.project_id == project_id,
                 or_(self.model_class.provisioning_status == consts.PENDING_DELETE,
                     self.model_class.provisioning_status == consts.ACTIVE))).count()
        return count

    def get_member_count_by_subnet(self, session, project_ids, subnet_id):
        return session.query(self.model_class).filter(
            and_(self.model_class.project_id.in_(project_ids),
                 self.model_class.subnet_id == subnet_id,
                 or_(self.model_class.provisioning_status == consts.PENDING_DELETE,
                     self.model_class.provisioning_status == consts.ACTIVE))).count()

    def get_member_count_by_ip_address(self, session, ip_address, project_id):
        return session.query(self.model_class).filter(
            self.model_class.project_id == project_id).filter(
            and_(self.model_class.ip_address == ip_address,
                 or_(self.model_class.provisioning_status == consts.PENDING_DELETE,
                     self.model_class.provisioning_status == consts.ACTIVE))).count()

    def get_member_count_by_ip_address_port_protocol(self, session, ip_address, project_id, port,
                                                     protocol):
        return session.query(self.model_class).join(base_models.Pool).filter(
            self.model_class.project_id == project_id).filter(
            and_(self.model_class.ip_address == ip_address,
                 self.model_class.protocol_port == port,
                 base_models.Pool.protocol == protocol,
                 or_(self.model_class.provisioning_status == consts.PENDING_DELETE,
                     self.model_class.provisioning_status == consts.ACTIVE))).count()

    def get_pool_count_by_ip(self, session, ip_address, project_id):
        return session.query(self.model_class.pool_id.distinct()).filter(
            self.model_class.project_id == project_id).filter(
            and_(self.model_class.ip_address == ip_address,
                 or_(self.model_class.provisioning_status == consts.PENDING_DELETE,
                     self.model_class.provisioning_status == consts.ACTIVE))).count()

    def get_pool_count_subnet(self, session, project_ids, subnet_id):
        return session.query(self.model_class.pool_id.distinct()).filter(
            self.model_class.project_id.in_(project_ids)).filter(
            and_(self.model_class.subnet_id == subnet_id,
                 or_(self.model_class.provisioning_status == consts.PENDING_DELETE,
                     self.model_class.provisioning_status == consts.ACTIVE))).count()

class NatPoolRepository(BaseRepository):
    model_class = models.NATPool
