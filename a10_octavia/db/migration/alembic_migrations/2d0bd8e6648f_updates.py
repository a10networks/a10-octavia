"""updates

Revision ID: 2d0bd8e6648f
Revises: 3446633d0749
Create Date: 2019-06-28 15:26:52.227260

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2d0bd8e6648f'
down_revision = '3446633d0749'
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
        sa.Column('project_id', sa.String(36))
    )


def downgrade():
    pass
