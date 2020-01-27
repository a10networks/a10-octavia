"""Added port and protocol

Revision ID: fe7b79c9c935
Revises: ed9c523cf8ee
Create Date: 2020-01-02 10:35:08.796208

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fe7b79c9c935'
down_revision = 'ed9c523cf8ee'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('vthunders', sa.Column('port', sa.Integer, default=443, nullable=False))
    op.add_column('vthunders', sa.Column('protocol', sa.String(10), default='https', nullable=False))


def downgrade():
   op.drop_column('vthunders', 'port')
   op.drop_column('vthunders', 'protocol')
