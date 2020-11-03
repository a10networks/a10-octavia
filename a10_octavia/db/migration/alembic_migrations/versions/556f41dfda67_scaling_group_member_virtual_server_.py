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

"""scaling_group_member_virtual_server_

Revision ID: 556f41dfda67
Revises: 2782f2bd94aa
Create Date: 2016-05-19 18:04:48.965907

"""

# revision identifiers, used by Alembic.
revision = '556f41dfda67'
down_revision = '2782f2bd94aa'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table(
        "a10_scaling_group_member_virtual_servers",
        sa.Column('id',
                  sa.String(36),
                  primary_key=True,
                  nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False),
        sa.Column('member_id',
                  sa.String(36),
                  sa.ForeignKey(u'a10_scaling_group_members.id'),
                  nullable=False),
        sa.Column('neutron_id',
                  sa.String(36),
                  nullable=False),
        sa.Column('ip_address',
                  sa.String(50),
                  nullable=False),
        sa.Column('interface_ip_address',
                  sa.String(50),
                  nullable=True),
        sa.Column('sflow_uuid',
                  sa.String(36),
                  nullable=False),
    )


def downgrade():
    op.drop_table("a10_scaling_group_member_virtual_servers")
