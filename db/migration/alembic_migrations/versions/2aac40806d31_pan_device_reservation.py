# vim: tabstop=4 shiftwidth=4 softtabstop=4
#
# Copyright 2014 OpenStack Foundation
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
#

"""pan_device_reservation

Revision ID: 2aac40806d31
Revises: icehouse
Create Date: 2014-05-20 09:14:48.572515

"""

# revision identifiers, used by Alembic.
revision = '2aac40806d31'
down_revision = 'icehouse'

# Change to ['*'] if this migration applies to all plugins

migration_for_plugins = ['*']

from alembic import op
import sqlalchemy as sa

from neutron.db import migration


def upgrade(active_plugins=None, options=None):
    if not migration.should_run(active_plugins, migration_for_plugins):
        return

    op.create_table(
        u'pan_device_reservations',
        sa.Column('router_id', sa.String(36), nullable=False),
        sa.Column('device_sn', sa.String(16), nullable=False),
        sa.PrimaryKeyConstraint('device_sn')
    )


def downgrade(active_plugins=None, options=None):
    if not migration.should_run(active_plugins, migration_for_plugins):
        return
    op.drop_table('pan_device_reservations')
