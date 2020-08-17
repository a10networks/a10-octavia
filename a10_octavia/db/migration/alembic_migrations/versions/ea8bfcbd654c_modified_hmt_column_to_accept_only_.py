"""Modified hmt column to accept only enable/disable

Revision ID: ea8bfcbd654c
Revises: 4028e5f7a198
Create Date: 2020-08-10 19:11:58.780617

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy_utils.types.choice import ChoiceType

from a10_octavia.db.models import VThunder

# revision identifiers, used by Alembic.
revision = 'ea8bfcbd654c'
down_revision = '4028e5f7a198'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        table_name='vthunders',
        column_name='hierarchical_multitenancy',
        nullable=False,
        type_=ChoiceType(VThunder.HIERARCHICAL_MT_TYPES)
    )


def downgrade():
    op.alter_column(
        table_name='vthunders',
        column_name='hierarchical_multitenancy',
        nullable=False,
        type_=sa.Boolean(),
        server_default=False
    )
