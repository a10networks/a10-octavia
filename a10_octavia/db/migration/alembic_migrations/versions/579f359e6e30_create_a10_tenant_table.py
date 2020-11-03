#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""create a10 tenant table

Revision ID: 579f359e6e30
Revises: None
Create Date: 2016-03-17 21:44:11.257126

"""

# revision identifiers, used by Alembic.
revision = '579f359e6e30'
down_revision = None
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table(
        'a10_tenant_bindings',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('created_at', sa.DateTime),
        sa.Column('updated_at', sa.DateTime),
        sa.Column('tenant_id', sa.String(36), nullable=False),
        sa.Column('device_name', sa.String(1024), nullable=False)
    )


def downgrade():
    op.drop_table('a10_tenant_bindings')
