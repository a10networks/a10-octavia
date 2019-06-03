"""create vthunder table

Revision ID: 64e2eaba72d5
Revises: 
Create Date: 2019-05-29 11:57:28.253533

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '64e2eaba72d5'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
    'vthunders',
    sa.Column(sa.Integer(), primary_key=True),
    sa.Column(sa.String(36), nullable=True),
    sa.Column(sa.String(1024), nullable=False),
    sa.Column('ip_address', sa.String(64), nullable=False),
    sa.Column(sa.String(1024), nullable=False),
    sa.Column(sa.String(50), nullable= False),
    sa.Column(sa.Integer, default=30, nullable=False),
    sa.Column(sa.Boolean(), default=False, nullable=False),
    sa.Column(sa.String(36))

    )



def downgrade():
    pass
