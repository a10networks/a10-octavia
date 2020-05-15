"""adding HA features

Revision ID: ed9c523cf8ee
Revises: 8151f374ba74
Create Date: 2019-09-03 12:19:44.353070

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "ed9c523cf8ee"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'vthunders',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('vthunder_id', sa.String(36), nullable=False),
        sa.Column('amphora_id', sa.String(36), nullable=True),
        sa.Column('device_name', sa.String(1024), nullable=False),
        sa.Column('ip_address', sa.String(64), nullable=False),
        sa.Column('username', sa.String(1024), nullable=False),
        sa.Column('password', sa.String(50), nullable=False),
        sa.Column('axapi_version', sa.Integer, default=30, nullable=False),
        sa.Column('undercloud', sa.Boolean(), default=False, nullable=False),
        sa.Column('loadbalancer_id', sa.String(36)),
        sa.Column('project_id', sa.String(36)),
        sa.Column('compute_id', sa.String(36)),
        sa.Column('topology', sa.String(50)),
        sa.Column('role', sa.String(50)),
        sa.Column('last_udp_update', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(36), default='ACTIVE', nullable=False),
        sa.Column(u'created_at', sa.DateTime(), nullable=True),
        sa.Column(u'updated_at', sa.DateTime(), nullable=True),
        sa.Column('partition_name', sa.String(14), nullable=True)
    )


def downgrade():
    op.drop_table('vthunders')
