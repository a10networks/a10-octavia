"""add write_memory protocol port columns

Revision ID: a6e9b9b69494
Revises: 05b1446c7f20
Create Date: 2020-12-02 10:31:36.286722

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a6e9b9b69494'
down_revision = '05b1446c7f20'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('vthunders', sa.Column('write_memory', sa.Boolean, nullable=False))
    op.add_column('vthunders', sa.Column('protocol', sa.String(32), nullable=False))
    op.add_column('vthunders', sa.Column('port', sa.Integer, nullable=False))


def downgrade():
    op.drop_column('vthunders', 'port')
    op.drop_column('vthunders', 'protocol')
    op.drop_column('vthunders', 'write_memory')
