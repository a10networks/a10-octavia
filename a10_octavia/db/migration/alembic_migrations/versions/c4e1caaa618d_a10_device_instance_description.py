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

"""a10_device_instance description

Revision ID: c4e1caaa618d
Revises: 78d283c111ac
Create Date: 2017-02-23 15:06:26.630570

"""

# revision identifiers, used by Alembic.
revision = 'c4e1caaa618d'
down_revision = '78d283c111ac'
branch_labels = None
depends_on = None

from alembic import op  # noqa
import sqlalchemy as sa  # noqa


def upgrade():
    op.add_column('a10_device_instances',
                  sa.Column('description', sa.String(255), nullable=True)
                  )


def downgrade():
    op.drop_column('a10_device_instances', 'description')
