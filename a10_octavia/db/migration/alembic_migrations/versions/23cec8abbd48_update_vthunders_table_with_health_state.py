"""update_vthunders_table_with_health_state

Revision ID: 23cec8abbd48
Revises: 1722c3166462
Create Date: 2021-07-28 06:00:39.571878

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '23cec8abbd48'
down_revision = '1722c3166462'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('vthunders', sa.Column('health_state', sa.String(36), nullable=True))


def downgrade():
    op.drop_column('vthunders', 'health_state')
