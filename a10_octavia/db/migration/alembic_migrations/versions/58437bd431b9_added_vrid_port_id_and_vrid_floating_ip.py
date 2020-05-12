"""Added vrid port_id and vrid floating_ip

Revision ID: 58437bd431b9
Revises: ed9c523cf8ee
Create Date: 2020-05-07 12:17:08.987483

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '58437bd431b9'
down_revision = 'ed9c523cf8ee'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('vthunders', sa.Column('vrid_port_id', sa.String(36), nullable=True))
    op.add_column('vthunders', sa.Column('vrid_floating_ip', sa.String(64), nullable=True))


def downgrade():
    op.drop_column('vthunders', 'vrid_floating_ip')
    op.drop_column('vthunders', 'vrid_port_id')
