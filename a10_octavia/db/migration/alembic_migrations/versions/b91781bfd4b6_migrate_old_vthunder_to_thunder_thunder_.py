"""migrate_old_vthunder_to_thunder_thunder_cluster

Revision ID: b91781bfd4b6
Revises: 896487fad87d
Create Date: 2020-11-10 19:43:14.075829

"""
from alembic import op
import sqlalchemy as sa

from sqlalchemy.orm import sessionmaker
from oslo_utils import uuidutils

from a10_octavia import a10_config
from a10_octavia.db.models import Thunder, Thunder_Cluster

# revision identifiers, used by Alembic.
revision = 'b91781bfd4b6'
down_revision = '896487fad87d'
branch_labels = None
depends_on = None

bind = op.get_bind()
session = sessionmaker(bind=bind)
sess = session()


def upgrade():
    a10_cfg = a10_config.A10Config()
    db_str = a10_cfg.get('a10_database_connection')
    db_engine = sa.create_engine(db_str)
    with db_engine.connect() as con:
        results = con.execute('select * from vthunders')
        thunder = []
        thunder_cluster = []
        for _row in results:
            thunder_cluster_id = uuidutils.generate_uuid()
            thunder_cluster.append(Thunder_Cluster(
                id=thunder_cluster_id,
                username=_row[5],
                password=_row[6],
                cluster_name=_row[3],
                cluster_ip_address=_row[4],
                topology=_row[12],
                undercloud=_row[8]
            ))
            thunder.append(Thunder(
                cluster_id=thunder_cluster_id
            ))
        sess.add_all(thunder)
        sess.add_all(thunder_cluster)
        sess.commit()
    sess.close()


def downgrade():
    sess.query(Thunder).filter().delete()
    sess.query(Thunder_Cluster).filter().delete()
    sess.commit()
    sess.close()
