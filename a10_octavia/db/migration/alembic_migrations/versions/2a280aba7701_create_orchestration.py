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

"""create orchestration

Revision ID: 2a280aba7701
Revises: 579f359e6e30
Create Date: 2016-04-12 18:25:17.910876

"""

# revision identifiers, used by Alembic.
revision = '2a280aba7701'
down_revision = '579f359e6e30'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table(
        'a10_device_instances',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False),
        sa.Column('tenant_id', sa.String(36), nullable=False),
        sa.Column('name', sa.String(1024), nullable=False),
        sa.Column('username', sa.String(255), nullable=False),
        sa.Column('password', sa.String(255), nullable=False),

        sa.Column('api_version', sa.String(255), nullable=False),
        sa.Column('protocol', sa.String(32), nullable=False),
        sa.Column('port', sa.Integer, nullable=False),
        sa.Column('autosnat', sa.Boolean(), nullable=False),
        sa.Column('v_method', sa.String(32), nullable=False),
        sa.Column('shared_partition', sa.String(1024), nullable=False),
        sa.Column('use_float', sa.Boolean(), nullable=False),
        sa.Column('default_virtual_server_vrid', sa.Integer, nullable=True),
        sa.Column('ipinip', sa.Boolean(), nullable=False),
        sa.Column('write_memory', sa.Boolean(), nullable=False),

        sa.Column('nova_instance_id', sa.String(36), nullable=False),
        sa.Column('host', sa.String(255), nullable=False)
    )
    op.create_table(
        'a10_slbs',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False),
        sa.Column('tenant_id', sa.String(36), nullable=False),
        sa.Column('device_name', sa.String(1024), nullable=False),
        sa.Column('pool_id', sa.String(36)),
        sa.Column('loadbalancer_id', sa.String(36)),
    )
    pass


def downgrade():
    op.drop_table('a10_slbs')
    op.drop_table('a10_device_instances')
    pass
