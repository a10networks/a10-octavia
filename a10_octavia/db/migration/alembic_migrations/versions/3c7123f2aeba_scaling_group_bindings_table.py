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

"""scaling group bindings table

Revision ID: 3c7123f2aeba
Revises: 152ed5d509bc
Create Date: 2016-05-25 17:10:18.890070

"""

# revision identifiers, used by Alembic.
revision = '3c7123f2aeba'
down_revision = '152ed5d509bc'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table(
        "a10_scaling_group_bindings",
        sa.Column('id',
                  sa.String(36),
                  primary_key=True,
                  nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False),
        sa.Column('scaling_group_id', sa.String(36),
                  sa.ForeignKey('a10_scaling_groups.id'),
                  nullable=False),
        sa.Column('lbaas_loadbalancer_id', sa.String(36),
                  nullable=False),
    )


def downgrade():
    op.drop_table("a10_scaling_group_bindings")
