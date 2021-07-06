"""vrid_table_extend_owner_size

Revision ID: 1722c3166462
Revises: 873ee83aef63
Create Date: 2021-06-25 18:36:26.122495

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1722c3166462'
down_revision = '873ee83aef63'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('vrid', 'owner',
            existing_type=sa.String(128), nullable=False)


def downgrade():
    op.alter_column('vrid', 'owner',
            existing_type=sa.String(36), nullable=False)
