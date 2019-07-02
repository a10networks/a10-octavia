"""upgrade2

Revision ID: a058dc662cc4
Revises: 2d0bd8e6648f
Create Date: 2019-07-01 11:57:39.020218

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a058dc662cc4'
down_revision = '2d0bd8e6648f'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
    'vthunders',
    sa.Column('vid', sa.String(36), primary_key=True),
    sa.Column('vthunder_id', sa.String(36), nullable=False),
    sa.Column('amphora_id', sa.String(36), nullable=True),
    sa.Column('device_name', sa.String(1024), nullable=False),
    sa.Column('ip_address', sa.String(64), nullable=False),
    sa.Column('username', sa.String(1024), nullable=False),
    sa.Column('password', sa.String(50), nullable= False),
    sa.Column('axapi_version', sa.Integer, default=30, nullable=False),
    sa.Column('undercloud', sa.Boolean(), default=False, nullable=False),
    sa.Column('loadbalancer_id', sa.String(36)),
    sa.Column('project_id', sa.String(36))
    )


def downgrade():
    pass
