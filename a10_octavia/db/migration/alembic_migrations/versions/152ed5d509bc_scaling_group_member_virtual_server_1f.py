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

"""scaling_group_member_virtual_server_1f

Revision ID: 152ed5d509bc
Revises: 556f41dfda67
Create Date: 2016-05-19 18:05:13.665808

"""

# revision identifiers, used by Alembic.
revision = '152ed5d509bc'
down_revision = '556f41dfda67'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table(
        "a10_scaling_group_member_virtual_server_ports",
        sa.Column('id',
                  sa.String(36),
                  primary_key=True,
                  nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False),
        sa.Column('virtual_server_id',
                  sa.String(36),
                  sa.ForeignKey(u'a10_scaling_group_member_virtual_servers.id'),
                  nullable=False),
        sa.Column('port',
                  sa.Integer,
                  nullable=False),
        sa.Column('protocol',
                  sa.String(255),
                  nullable=False),
        sa.Column('sflow_uuid',
                  sa.String(36),
                  nullable=False),
    )


def downgrade():
    op.drop_table("a10_scaling_group_member_virtual_server_ports")
