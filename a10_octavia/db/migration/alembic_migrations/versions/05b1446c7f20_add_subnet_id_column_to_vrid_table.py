"""Add subnet_id column to vrid table

Revision ID: 05b1446c7f20
Revises: ea8bfcbd654c
Create Date: 2020-09-10 07:08:19.928899

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '05b1446c7f20'
down_revision = '4028e5f7a198'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('vrid', sa.Column('subnet_id', sa.String(36), nullable=False))


def downgrade():
    op.drop_column('vrid', 'subnet_id')
