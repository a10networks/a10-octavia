"""Updated vrid table to use a uuid for its primary key

Revision ID: 9bfc38df2582
Revises: cfce01f4010d
Create Date: 2021-05-17 08:42:42.132368

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '9bfc38df2582'
down_revision = 'cfce01f4010d'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('ALTER TABLE vrid DROP PRIMARY KEY, CHANGE id id int(11)')
    op.alter_column('vrid', 'id',
        existing_type=mysql.VARCHAR(length=36),
        type_=sa.String(36))
    op.execute('ALTER TABLE vrid ADD PRIMARY KEY (id)')
    op.alter_column('vrid', 'vrid_floating_ip',
        existing_type=mysql.VARCHAR(length=40),
        nullable=False)

def downgrade():
    op.execute('ALTER TABLE vrid DROP PRIMARY KEY')
    op.alter_column('vrid', 'id', type_=sa.Integer)
    op.execute('ALTER TABLE vrid ADD PRIMARY KEY (id)')
    op.execute('ALTER TABLE vrid MODIFY id INTEGER NOT NULL AUTO_INCREMENT')
    op.alter_column('vrid', 'vrid_floating_ip',
        existing_type=mysql.VARCHAR(length=40),
        nullable=True)
