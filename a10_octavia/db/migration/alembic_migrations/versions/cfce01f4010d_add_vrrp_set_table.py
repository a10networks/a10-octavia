"""add_vrrp_set_table

Revision ID: cfce01f4010d
Revises: a3c90b57952d
Create Date: 2021-04-26 05:34:36.527145

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'cfce01f4010d'
down_revision = 'a3c90b57952d'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('vrrp_set',
    sa.Column('mgmt_subnet', sa.String(length=64), nullable=False),
    sa.Column('project_id', sa.String(length=64), nullable=False),
    sa.Column('set_id', sa.Integer(), nullable=False),
    sa.UniqueConstraint('mgmt_subnet', 'project_id', name='unique_name_project_subnet_set_id')
    )


def downgrade():
    op.drop_table('vrrp_set')
