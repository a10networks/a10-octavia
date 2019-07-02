"""id_update

Revision ID: 2a6dc7e020db
Revises: a058dc662cc4
Create Date: 2019-07-01 12:10:18.700832

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2a6dc7e020db'
down_revision = 'a058dc662cc4'
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
    sa.Column('password', sa.String(50), nullable= False),
    sa.Column('axapi_version', sa.Integer, default=30, nullable=False),
    sa.Column('undercloud', sa.Boolean(), default=False, nullable=False),
    sa.Column('loadbalancer_id', sa.String(36)),
    sa.Column('project_id', sa.String(36))
    )

def downgrade():
    pass
