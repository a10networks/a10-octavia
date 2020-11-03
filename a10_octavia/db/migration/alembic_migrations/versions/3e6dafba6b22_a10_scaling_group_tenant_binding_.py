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

"""a10_scaling_group_tenant_binding_loadbalancers

Revision ID: 3e6dafba6b22
Revises: 3a4bbcea6e1e
Create Date: 2016-08-05 22:22:55.910160

"""

# revision identifiers, used by Alembic.
revision = '3e6dafba6b22'
down_revision = '3a4bbcea6e1e'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table(
        "a10_scaling_group_tenant_binding_loadbalancers",
        sa.Column('id',
                  sa.String(36),
                  primary_key=True,
                  nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False),
        sa.Column('tenant_binding_id',
                  sa.String(36),
                  sa.ForeignKey('a10_scaling_group_tenant_bindings.id'),
                  nullable=False),
        sa.Column('lbaas_loadbalancer_id',
                  sa.String(36),
                  unique=True,
                  nullable=False)
    )


def downgrade():
    op.drop_table('a10_scaling_group_tenant_binding_loadbalancers')
