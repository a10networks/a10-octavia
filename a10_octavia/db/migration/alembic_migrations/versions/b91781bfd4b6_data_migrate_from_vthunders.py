"""migrate_old_vthunder_to_thunder_thunder_cluster

Revision ID: b91781bfd4b6
Revises: b63ad99c9123
Create Date: 2020-11-10 19:43:14.075829

"""
import sqlalchemy as sa
from alembic import op
from oslo_utils import uuidutils
from sqlalchemy.orm import sessionmaker

from a10_octavia import a10_config
from a10_octavia.db.models import Amphora_Meta
from a10_octavia.db.models import Partitions
from a10_octavia.db.models import Thunder_Cluster
from a10_octavia.db.models import Topology

# revision identifiers, used by Alembic.
revision = 'b91781bfd4b6'
down_revision = 'b63ad99c9123'
branch_labels = None
depends_on = None

try:
    bind = op.get_bind()
except NameError:
    pass
else:
    session = sessionmaker(bind=bind)
    sess = session()


def upgrade():
    a10_cfg = a10_config.A10Config()
    db_str = a10_cfg.get('a10_database_connection')
    db_engine = sa.create_engine(db_str)
    with db_engine.connect() as con:
        results = con.execute('select * from vthunders')
        thunder_cluster = []
        partitions = []
        amphora_meta = []
        for _row in results:
            try:
                topology = getattr(Topology, _row[12]).value
            except AttributeError:
                topology = Topology.STANDALONE.value

            thunder_cluster.append(Thunder_Cluster(
                id=_row[1],
                username=_row[5],
                password=_row[6],
                cluster_name=_row[3],
                cluster_ip_address=_row[4],
                topology=topology,
                undercloud=_row[8]
            ))
            partition_id = uuidutils.generate_uuid()
            partitions.append(Partitions(id=partition_id,
                                         name=_row[18],
                                         hierarchical_multitenancy=_row[19],
                                         created_at=_row[16],
                                         updated_at=_row[17]))
            amphora_meta.append(Amphora_Meta(id=_row[2],
                                             last_udp_update=_row[14],
                                             status=_row[15],
                                             created_at=_row[16],
                                             updated_at=_row[17]))
        sess.add_all(thunder_cluster)
        sess.add_all(partitions)
        sess.add_all(amphora_meta)
        sess.commit()
    sess.close()


def downgrade():
    sess.query(Amphora_Meta).filter().delete()
    sess.query(Partitions).filter().delete()
    sess.query(Thunder_Cluster).filter().delete()
    sess.commit()
    sess.close()
