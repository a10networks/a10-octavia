"""Added vrid table

Revision ID: 4028e5f7a198
Revises: b02c78488551
Create Date: 2020-05-27 14:46:46.139384

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4028e5f7a198'
down_revision = 'b02c78488551'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'vrid',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('project_id', sa.String(36), nullable=False),
        sa.Column('vrid', sa.Integer, default=0, nullable=False),
        sa.Column('vrid_port_id', sa.String(36), nullable=False),
        sa.Column('vrid_floating_ip', sa.String(40), nullable=False)
    )


def downgrade():
    op.drop_table('vrid')
