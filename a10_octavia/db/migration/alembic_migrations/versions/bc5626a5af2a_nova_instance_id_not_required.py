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

"""Nova instance ID not required

Revision ID: bc5626a5af2a
Revises: 3c7123f2aeba
Create Date: 2016-10-27 18:47:41.163902

"""

# revision identifiers, used by Alembic.
revision = 'bc5626a5af2a'
down_revision = '3c7123f2aeba'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.alter_column('a10_device_instances',
                    sa.Column('nova_instance_id', sa.String(36), nullable=True))


def downgrade():
    op.alter_column('a10_device_instances',
                    sa.Column('nova_instance_id', sa.String(36), nullable=False))
