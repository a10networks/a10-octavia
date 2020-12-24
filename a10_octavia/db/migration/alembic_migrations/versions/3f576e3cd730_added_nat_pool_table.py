"""Added NAT Pool table

Revision ID: 3f576e3cd730
Revises: 896487fad87d
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
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=1024), nullable=False),
    sa.Column('subnet_id', sa.String(length=36), nullable=False),
    sa.Column('start_ip_address', sa.String(length=64), nullable=False),
    sa.Column('end_ip_address', sa.String(length=64), nullable=False),
    sa.Column('member_ref_count', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('nat_pool')
