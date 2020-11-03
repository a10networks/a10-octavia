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

"""scaling group tenant binding table

Revision ID: 357cd913dae6
Revises: 3c7123f2aeba
Create Date: 2016-06-02 17:47:12.736929

"""

# revision identifiers, used by Alembic.
revision = '357cd913dae6'
down_revision = '3c7123f2aeba'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table(
        "a10_scaling_group_tenant_bindings",
        sa.Column('id',
                  sa.String(36),
                  primary_key=True,
                  nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False),
        sa.Column('scaling_group_id', sa.String(36),
                  sa.ForeignKey('a10_scaling_groups.id'),
                  nullable=False),
        sa.Column('tenant_id', sa.String(255),
                  nullable=False),
    )


def downgrade():
    op.drop_table("a10_scaling_group_tenant_bindings")
