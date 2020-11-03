# Copyright (C) 2016, A10 Networks Inc. All rights reserved.
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

"""v2 SSL Certificates

Revision ID: 08dacae1fb67
Revises: 3c7123f2aeba
Create Date: 2016-06-21 06:18:58.773598

"""

# revision identifiers, used by Alembic.
revision = '08dacae1fb67'
down_revision = '3c7123f2aeba'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table(
        'a10_certificates',
        sa.Column('tenant_id', sa.String(255), nullable=True),
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(1024), nullable=True),
        sa.Column('cert_data', sa.Text(8000), nullable=False),
        sa.Column('key_data', sa.Text(8000), nullable=False),
        sa.Column('intermediate_data', sa.Text(8000), nullable=True),
        sa.Column('password', sa.String(1024), nullable=True),
    )

    op.create_table(
        'a10_certificatelistenerbindings',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False),
        sa.Column('tenant_id', sa.String(36), nullable=False),
        sa.Column('certificate_id', sa.String(36),
                  sa.ForeignKey(u'a10_certificates.id'),
                  nullable=False),
        sa.Column('listener_id', sa.String(36), nullable=False)
    )


def downgrade():
    op.drop_table('a10_certificatelistenerbindings')
    op.drop_table('a10_certificates')
