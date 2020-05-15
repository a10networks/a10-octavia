"""Adding interface vlan map
  
Revision ID: a2f081b7a25d
Revises: ed9c523cf8ee
Create Date: 2020-05-06 14:00:44.676068

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a2f081b7a25d'
down_revision = 'b02c78488551'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('vthunders', sa.Column('interface_vlan_map', sa.String(256), nullable=True))


def downgrade():
    op.drop_column('vthunders', 'interface_vlan_map')
