"""add acos version column to vthunders table

Revision ID: 34a0d811941d
Revises: aa1984742932
Create Date: 2021-03-01 05:09:40.157396

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '34a0d811941d'
down_revision = 'aa1984742932'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('vthunders', sa.Column('acos_version', sa.String(36), nullable=True))


def downgrade():
    op.drop_column('vthunders', 'acos_version')
