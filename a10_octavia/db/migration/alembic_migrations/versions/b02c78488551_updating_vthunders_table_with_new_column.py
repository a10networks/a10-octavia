"""Updating vthunders table with new column

Revision ID: b02c78488551
Revises: ed9c523cf8ee
Create Date: 2020-04-23 06:05:04.792826

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b02c78488551'
down_revision = 'ed9c523cf8ee'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('vthunders', sa.Column('hierarchical_multitenancy', sa.String(7), default=None, nullable=True))

def downgrade():
    op.drop_column('vthunders', 'hierarchical_multitenancy')
