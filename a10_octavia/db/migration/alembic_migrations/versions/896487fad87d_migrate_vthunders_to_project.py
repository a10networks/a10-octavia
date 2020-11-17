"""migrate_vthunders_to_project

Revision ID: 896487fad87d
Revises: b91781bfd4b6
Create Date: 2020-11-09 11:15:39.982882

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import sessionmaker

from a10_octavia import a10_config
from a10_octavia.db.models import Project

# revision identifiers, used by Alembic.
revision = '896487fad87d'
down_revision = 'b91781bfd4b6'
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
        project = []
        join_result = con.execute(
            'select vthunders.project_id, vthunders.created_at, '
            'vthunders.updated_at, partitions.id, thunder_cluster.id from '
            '(partitions, thunder_cluster) left join vthunders on '
            '(vthunders.partition_name = partitions.name and '
            'vthunders.vthunder_id = thunder_cluster.id);')
        for _row in join_result:
            project.append(Project(id=_row[0],
                                   created_at=_row[1],
                                   updated_at=_row[2],
                                   partition_id=_row[3],
                                   thunder_cluster_id=_row[4]))
        sess.add_all(project)
        sess.commit()
    sess.close()


def downgrade():
    sess.query(Project).filter().delete()
    sess.commit()
    sess.close()
