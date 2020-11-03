# Copyright 2016, A10 Networks
#
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

"""Added status column to bindings table

Revision ID: 4ffd7ee0f175
Revises: e3d5134c59a7
Create Date: 2016-12-14 01:01:28.281713

"""

# revision identifiers, used by Alembic.
revision = '4ffd7ee0f175'
down_revision = 'e3d5134c59a7'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('a10_certificatelistenerbindings',
                  sa.Column('status', sa.Integer, nullable=False, default=0, server_default='0')
                  )


def downgrade():
    op.drop_column('a10_certificatelistenerbindings', 'status')
