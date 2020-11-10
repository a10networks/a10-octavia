"""migrate_vthunders_to_amphora_meta

Revision ID: 896487fad87d
Revises: 5176feaaed39
Create Date: 2020-11-09 11:15:39.982882

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from a10_octavia import a10_config
from a10_octavia.db.models import Amphora_Meta


# revision identifiers, used by Alembic.
revision = '896487fad87d'
down_revision = 'b63ad99c9123'
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
        amphora_meta = []
        for _row in results:
            amphora_meta.append(Amphora_Meta(id=_row[2],
                                             last_udp_update=_row[14],
                                             status=_row[15],
                                             created_at=_row[16],
                                             updated_at=_row[17]))
        sess.add_all(amphora_meta)
        sess.commit()
    sess.close()


def downgrade():
    sess.query(Amphora_Meta).filter().delete()
    sess.commit()
    sess.close()
