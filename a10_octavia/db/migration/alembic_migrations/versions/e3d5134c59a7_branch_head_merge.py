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
"""Branch head merge

Revision ID: e3d5134c59a7
Revises: 08dacae1fb67, bc5626a5af2a
Create Date: 2016-12-13 18:33:01.305065

"""

# revision identifiers, used by Alembic.
revision = 'e3d5134c59a7'
down_revision = ('08dacae1fb67', 'bc5626a5af2a')
branch_labels = None
depends_on = None

from alembic import op  # noqa
import sqlalchemy as sa  # noqa


def upgrade():
    pass


def downgrade():
    pass
