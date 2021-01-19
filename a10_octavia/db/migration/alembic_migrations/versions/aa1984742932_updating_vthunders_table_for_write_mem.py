"""updating_vthunders_table_with_last_write_mem

Revision ID: aa1984742932
Revises: a41260fb4ccd
Create Date: 2021-01-19 14:57:39.782860

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'aa1984742932'
down_revision = 'a41260fb4ccd'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('vthunders', sa.Column('last_write_mem', sa.DateTime(), default=None, nullable=True))


def downgrade():
    op.drop_column('vthunders', 'last_write_mem')
    pass
