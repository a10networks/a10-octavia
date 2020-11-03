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

"""a10_tenant_bindings created_at nullable

Revision ID: 3a4bbcea6e1e
Revises: 53ef3417bbaa
Create Date: 2016-08-05 20:17:00.492616

"""

# revision identifiers, used by Alembic.
revision = '3a4bbcea6e1e'
down_revision = '53ef3417bbaa'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.alter_column('a10_tenant_bindings', 'created_at',
                    type_=sa.DateTime, nullable=False,
                    existing_type=sa.DateTime, existing_nullable=True)
    op.alter_column('a10_tenant_bindings', 'updated_at',
                    type_=sa.DateTime, nullable=False,
                    existing_type=sa.DateTime, existing_nullable=True)


def downgrade():
    pass
