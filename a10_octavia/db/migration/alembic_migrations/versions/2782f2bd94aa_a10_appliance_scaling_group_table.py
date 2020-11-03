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

"""a10_appliance_scaling_group_table

Revision ID: 2782f2bd94aa
Revises: 2a280aba7701
Create Date: 2016-05-19 18:04:17.611550

"""

# revision identifiers, used by Alembic.
revision = '2782f2bd94aa'
down_revision = '2a280aba7701'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table(
        "a10_scaling_policies",
        sa.Column('id',
                  sa.String(36),
                  primary_key=True,
                  nullable=False),
        sa.Column('tenant_id', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False),
        sa.Column('name', sa.String(255), nullable=True),
        sa.Column('description', sa.String(255), nullable=True),

        sa.Column('cooldown', sa.Integer, nullable=False),
        sa.Column('min_instances', sa.Integer, nullable=False),
        sa.Column('max_instances', sa.Integer, nullable=True)
    )

    op.create_table(
        'a10_scaling_alarms',
        sa.Column('id',
                  sa.String(36),
                  primary_key=True,
                  nullable=False),
        sa.Column('tenant_id', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False),
        sa.Column('name', sa.String(255), nullable=True),
        sa.Column('description', sa.String(255), nullable=True),

        sa.Column('aggregation', sa.String(50), nullable=False),
        sa.Column('measurement', sa.String(50), nullable=False),
        sa.Column('operator', sa.String(50), nullable=False),
        sa.Column('threshold', sa.Float(), nullable=False),
        sa.Column('unit', sa.String(50), nullable=False),
        sa.Column('period', sa.Integer, nullable=False),
        sa.Column('period_unit', sa.String(50), nullable=False)
    )

    op.create_table(
        'a10_scaling_actions',
        sa.Column('id',
                  sa.String(36),
                  primary_key=True,
                  nullable=False),
        sa.Column('tenant_id', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False),
        sa.Column('name', sa.String(255), nullable=True),
        sa.Column('description', sa.String(255), nullable=True),

        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('amount', sa.Integer)
    )

    op.create_table(
        'a10_scaling_policy_reactions',
        sa.Column('id',
                  sa.String(36),
                  primary_key=True,
                  nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False),
        sa.Column('scaling_policy_id',
                  sa.String(36),
                  sa.ForeignKey('a10_scaling_policies.id'),
                  nullable=False),
        sa.Column('position',
                  sa.Integer,
                  nullable=False),
        sa.Column('alarm_id',
                  sa.String(36),
                  sa.ForeignKey('a10_scaling_alarms.id'),
                  nullable=False),
        sa.Column('action_id',
                  sa.String(36),
                  sa.ForeignKey('a10_scaling_actions.id'),
                  nullable=False)
    )

    op.create_table(
        "a10_scaling_groups",
        sa.Column('id', sa.String(36),
                  primary_key=True,
                  nullable=False),

        sa.Column('tenant_id', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False),
        sa.Column('name', sa.String(255), nullable=True),
        sa.Column('description', sa.String(255), nullable=True),

        sa.Column('scaling_policy_id',
                  sa.String(36),
                  sa.ForeignKey('a10_scaling_policies.id'),
                  nullable=True)
    )

    op.create_table(
        "a10_scaling_group_members",
        sa.Column('id', sa.String(36),
                  primary_key=True,
                  nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False),
        sa.Column('type', sa.String(50), nullable=False),
        sa.Column('scaling_group_id', sa.String(36),
                  sa.ForeignKey('a10_scaling_groups.id'),
                  nullable=False),
        sa.Column('tenant_id', sa.String(255), nullable=True),
        sa.Column('name', sa.String(255), nullable=True),
        sa.Column('description', sa.String(255), nullable=True),
        sa.Column('host', sa.String(255), nullable=False),
        sa.Column('api_version', sa.String(12), nullable=False),
        sa.Column('username', sa.String(255), nullable=False),
        sa.Column('password', sa.String(255), nullable=False),
        sa.Column('protocol', sa.String(255), nullable=False),
        sa.Column('port', sa.Integer, nullable=False),
        sa.Column('nova_instance_id', sa.String(36), nullable=False)
    )

    op.create_table(
        "a10_scaling_group_switches",
        sa.Column('id', sa.String(36),
                  sa.ForeignKey(u'a10_scaling_group_members.id'),
                  primary_key=True,
                  nullable=False),
    )

    op.create_table(
        "a10_scaling_group_workers",
        sa.Column('id', sa.String(36),
                  sa.ForeignKey(u'a10_scaling_group_members.id'),
                  primary_key=True,
                  nullable=False),
    )


def downgrade():
    op.drop_table('a10_scaling_group_workers')
    op.drop_table('a10_scaling_group_switches')
    op.drop_table('a10_scaling_group_members')
    op.drop_table('a10_scaling_groups')
    op.drop_table('a10_scaling_policy_reactions')
    op.drop_table('a10_scaling_alarms')
    op.drop_table('a10_scaling_actions')
    op.drop_table("a10_scaling_policies")
