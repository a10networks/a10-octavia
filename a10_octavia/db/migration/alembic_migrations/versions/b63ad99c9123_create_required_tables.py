"""create required tables

Revision ID: b63ad99c9123
Revises: 05b1446c7f20
Create Date: 2020-11-12 11:59:15.173270

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b63ad99c9123'
down_revision = '05b1446c7f20'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('amphora_meta',
                    sa.Column('id', sa.String(length=36), nullable=False),
                    sa.Column('created_at', sa.DateTime(), nullable=True),
                    sa.Column('updated_at', sa.DateTime(), nullable=True),
                    sa.Column('last_udp_update', sa.DateTime(), nullable=False),
                    sa.Column('status', sa.String(length=36), nullable=False),
                    sa.PrimaryKeyConstraint('id')
                    )
    op.create_table('ethernet_interface',
                    sa.Column('interface_num', sa.Integer(), nullable=False),
                    sa.Column('created_at', sa.DateTime(), nullable=True),
                    sa.Column('updated_at', sa.DateTime(), nullable=True),
                    sa.Column('vlan_id', sa.String(length=36), nullable=False),
                    sa.Column('subnet_id', sa.String(length=36), nullable=False),
                    sa.Column('ve_ip_address', sa.String(length=64), nullable=False),
                    sa.Column('port_id', sa.String(length=36), nullable=False),
                    sa.PrimaryKeyConstraint('interface_num')
                    )
    op.create_table('partitions',
                    sa.Column('id', sa.String(length=36), nullable=False),
                    sa.Column('created_at', sa.DateTime(), nullable=True),
                    sa.Column('updated_at', sa.DateTime(), nullable=True),
                    sa.Column('name', sa.String(length=14), nullable=True),
                    sa.Column('hierarchical_multitenancy', sa.String(length=7), nullable=False),
                    sa.PrimaryKeyConstraint('id')
                    )
    op.create_table('thunder_cluster',
                    sa.Column('id', sa.String(length=36), nullable=False),
                    sa.Column('created_at', sa.DateTime(), nullable=True),
                    sa.Column('updated_at', sa.DateTime(), nullable=True),
                    sa.Column('username', sa.String(length=1024), nullable=False),
                    sa.Column('password', sa.String(length=50), nullable=False),
                    sa.Column('cluster_name', sa.String(length=1024), nullable=False),
                    sa.Column('cluster_ip_address', sa.String(length=64), nullable=False),
                    sa.Column('topology', sa.String(length=50), nullable=True),
                    sa.Column('undercloud', sa.Boolean(), nullable=False),
                    sa.PrimaryKeyConstraint('id')
                    )
    op.create_table('trunk_interface',
                    sa.Column('interface_num', sa.Integer(), nullable=False),
                    sa.Column('created_at', sa.DateTime(), nullable=True),
                    sa.Column('updated_at', sa.DateTime(), nullable=True),
                    sa.Column('vlan_id', sa.String(length=36), nullable=False),
                    sa.Column('subnet_id', sa.String(length=36), nullable=False),
                    sa.Column('ve_ip_address', sa.String(length=64), nullable=False),
                    sa.Column('port_id', sa.String(length=36), nullable=False),
                    sa.PrimaryKeyConstraint('interface_num')
                    )
    op.create_table('project',
                    sa.Column('id', sa.String(length=36), nullable=False),
                    sa.Column('created_at', sa.DateTime(), nullable=True),
                    sa.Column('updated_at', sa.DateTime(), nullable=True),
                    sa.Column('partition_id', sa.String(length=36), nullable=False),
                    sa.Column('thunder_cluster_id', sa.String(length=36), nullable=False),
                    sa.ForeignKeyConstraint(['partition_id'], ['partitions.id'], ),
                    sa.ForeignKeyConstraint(['thunder_cluster_id'], ['thunder_cluster.id'], ),
                    sa.PrimaryKeyConstraint('id')
                    )
    op.create_table('thunder',
                    sa.Column('id', sa.String(length=36), nullable=False),
                    sa.Column('created_at', sa.DateTime(), nullable=True),
                    sa.Column('updated_at', sa.DateTime(), nullable=True),
                    sa.Column('vcs_device_id', sa.String(length=1), nullable=False),
                    sa.Column('management_ip_address', sa.String(length=64), nullable=False),
                    sa.Column('cluster_id', sa.String(length=36), nullable=True),
                    sa.ForeignKeyConstraint(['cluster_id'], ['thunder_cluster.id'], ),
                    sa.PrimaryKeyConstraint('id')
                    )
    op.create_table('device_network_cluster',
                    sa.Column('id', sa.String(length=36), nullable=False),
                    sa.Column('created_at', sa.DateTime(), nullable=True),
                    sa.Column('updated_at', sa.DateTime(), nullable=True),
                    sa.Column('thunder_id', sa.String(length=36), nullable=True),
                    sa.Column('ethernet_interface_num', sa.Integer(), nullable=True),
                    sa.Column('trunk_interface_num', sa.Integer(), nullable=True),
                    sa.ForeignKeyConstraint(['ethernet_interface_num'], [
                                            'ethernet_interface.interface_num'], ),
                    sa.ForeignKeyConstraint(['thunder_id'], ['thunder.id'], ),
                    sa.ForeignKeyConstraint(['trunk_interface_num'], [
                                            'trunk_interface.interface_num'], ),
                    sa.PrimaryKeyConstraint('id')
                    )
    op.create_table('role',
                    sa.Column('id', sa.String(length=36), nullable=False),
                    sa.Column('created_at', sa.DateTime(), nullable=True),
                    sa.Column('updated_at', sa.DateTime(), nullable=True),
                    sa.Column('state', sa.String(length=36), nullable=False),
                    sa.Column('thunder_id', sa.String(length=36), nullable=True),
                    sa.ForeignKeyConstraint(['thunder_id'], ['thunder.id'], ),
                    sa.PrimaryKeyConstraint('id')
                    )
    op.add_column(u'vrid', sa.Column('created_at', sa.DateTime(), nullable=True))
    op.add_column(u'vrid', sa.Column('updated_at', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column(u'vrid', 'updated_at')
    op.drop_column(u'vrid', 'created_at')
    op.drop_table('role')
    op.drop_table('device_network_cluster')
    op.drop_table('thunder')
    op.drop_table('project')
    op.drop_table('trunk_interface')
    op.drop_table('thunder_cluster')
    op.drop_table('partitions')
    op.drop_table('ethernet_interface')
    op.drop_table('amphora_meta')
