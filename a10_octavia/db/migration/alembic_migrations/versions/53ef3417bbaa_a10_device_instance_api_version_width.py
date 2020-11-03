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

"""a10_device_instance api_version width

Revision ID: 53ef3417bbaa
Revises: 357cd913dae6
Create Date: 2016-08-05 20:08:16.496817

"""

# revision identifiers, used by Alembic.
revision = '53ef3417bbaa'
down_revision = '357cd913dae6'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.alter_column('a10_device_instances', 'api_version',
                    type_=sa.String(12), nullable=False,
                    existing_type=sa.String(255), existing_nullable=False)


def downgrade():
    pass
