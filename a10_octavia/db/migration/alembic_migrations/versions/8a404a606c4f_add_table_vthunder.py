"""Add table vthunder

Revision ID: 8a404a606c4f
Revises: 64e2eaba72d5
Create Date: 2019-05-29 14:49:13.076098

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8a404a606c4f'
down_revision = ''
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
    'vthunders',
    sa.Column('id',sa.String(36), primary_key=True),
    sa.Column('amphora_id', sa.String(36), nullable=True),
    sa.Column('device_name', sa.String(1024), nullable=False),
    sa.Column('ip_address', sa.String(64), nullable=False),
    sa.Column('username', sa.String(1024), nullable=False),
    sa.Column('password', sa.String(50), nullable= False),
    sa.Column('axapi_version', sa.Integer, default=30, nullable=False),
    sa.Column('undercloud',sa.Boolean(), default=False, nullable=False),
    sa.Column('loadbalancer_id', sa.String(36))

    )

def downgrade():
    pass
