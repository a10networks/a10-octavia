"""create amphora_meta table

Revision ID: f7017d3417ce
Revises: 05b1446c7f20
Create Date: 2020-11-04 05:22:12.860858

"""
from alembic import op
import sqlalchemy as sa


revision = 'f7017d3417ce'
down_revision = '05b1446c7f20'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'amphora_meta',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('last_udp_update', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(36), default='ACTIVE', nullable=False)
    )
    op.create_table(
        'thunder',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('vcs_device_id', sa.String(1), nullable=False),
        sa.Column('management_ip_address', sa.String(64), nullable=False)
    )
    op.create_table(
        'role',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('role', sa.String(36), nullable=False),
        sa.Column('thunder_id', sa.String(36), sa.ForeignKey('thunder.id'))
    )
    op.create_table(
        'thunder_cluster',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('username', sa.String(1024), nullable=False),
        sa.Column('password', sa.String(50), nullable=False),
        sa.Column('cluster_name', sa.String(1024), nullable=False),
        sa.Column('cluster_ip_address', sa.String(64), nullable=False),
        sa.Column('topology', sa.String(50)),
        sa.Column('undercloud', sa.Boolean(), default=False, nullable=False)
    )
    op.create_table(
        'partitions',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('partition_name', sa.String(14), nullable=True),
        sa.Column('hierarchical_multitenancy', sa.String(7), nullable=False),
    )
    op.create_table(
        'project',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('partition_id', sa.String(36), sa.ForeignKey('partitions.id')),
        sa.Column('thunder_cluster_id', sa.String(36), sa.ForeignKey('thunder_cluster.id')),
    )
    op.create_table(
        'ethernet_interface',
        sa.Column('interface_num', sa.Integer, primary_key=True, nullable=False),
        sa.Column('vlan_id', sa.String(36), nullable=False),
        sa.Column('subnet_id', sa.String(36), nullable=False),
        sa.Column('ve_ip_address', sa.String(64), nullable=False),
        sa.Column('port_id', sa.String(36), nullable=False),
        sa.Column('state', sa.String(36), nullable=False)
    )
    op.create_table(
        'trunk_interface',
        sa.Column('interface_num', sa.Integer, primary_key=True, nullable=False),
        sa.Column('vlan_id', sa.String(36), nullable=False),
        sa.Column('subnet_id', sa.String(36), nullable=False),
        sa.Column('ve_ip_address', sa.String(64), nullable=False),
        sa.Column('port_id', sa.String(36), nullable=False),
        sa.Column('state', sa.String(36), nullable=False)
    )
    op.create_table(
        've_interface_cluster',
        sa.Column('thunder_id', sa.String(36), sa.ForeignKey('thunder.id')),
        sa.Column('ethernet_interface_num', sa.Integer,
                  sa.ForeignKey('ethernet_interface.interface_num')),
        sa.Column('trunk_interface_num', sa.Integer, sa.ForeignKey('trunk_interface.interface_num'))
    )


def downgrade():
    op.drop_table('ve_interface_cluster')
    op.drop_table('trunk_interface')
    op.drop_table('ethernet_interface')
    op.drop_table('project')
    op.drop_table('partitions')
    op.drop_table('thunder_cluster')
    op.drop_table('role')
    op.drop_table('thunder')
    op.drop_table('amphora_meta')
