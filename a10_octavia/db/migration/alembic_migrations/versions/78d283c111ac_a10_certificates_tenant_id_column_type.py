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

"""a10_certificates tenant_id column type

Revision ID: 78d283c111ac
Revises: 9458ad898897
Create Date: 2017-02-01 22:53:47.229207

"""

# revision identifiers, used by Alembic.
revision = '78d283c111ac'
down_revision = '9458ad898897'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.alter_column('a10_certificates', 'tenant_id', type_=sa.String(36), nullable=False)


def downgrade():
    op.alter_column('a10_certificates', 'tenant_id', type_=sa.String(255), nullable=True)
