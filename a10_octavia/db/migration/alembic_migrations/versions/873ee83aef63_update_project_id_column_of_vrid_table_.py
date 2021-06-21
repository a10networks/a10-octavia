"""update project_id column of vrid table as owner

Revision ID: 873ee83aef63
Revises: 9bfc38df2582
Create Date: 2021-06-19 12:39:14.671476

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '873ee83aef63'
down_revision = '9bfc38df2582'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('vrid', 'project_id',
            new_column_name='owner',
            existing_type=sa.String(36), nullable=False)


def downgrade():
    op.alter_column('vrid', 'owner',
            new_column_name='project_id',
            existing_type=sa.String(36), nullable=False)
