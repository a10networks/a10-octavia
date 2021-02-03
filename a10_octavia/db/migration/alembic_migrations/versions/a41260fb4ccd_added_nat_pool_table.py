"""Added NAT Pool table

Revision ID: a41260fb4ccd
Revises: 05b1446c7f20
Create Date: 2020-12-21 16:52:42.793854

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = 'a41260fb4ccd'
down_revision = '05b1446c7f20'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('nat_pool',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=64), nullable=False),
    sa.Column('subnet_id', sa.String(length=64), nullable=False),
    sa.Column('start_address', sa.String(length=64), nullable=False),
    sa.Column('end_address', sa.String(length=64), nullable=False),
    sa.Column('member_ref_count', sa.Integer(), nullable=True),
    sa.Column('port_id', sa.String(length=64), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name', 'subnet_id', name='unique_name_subnet_id')
    )


def downgrade():
    op.drop_table('nat_pool')
