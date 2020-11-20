# Copyright 2020, A10 Networks.
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

import datetime

from oslo_utils import uuidutils

from a10_octavia.common import data_models
from a10_octavia.tests.unit import base


class TestDataModels(base.BaseTaskTestCase):

    def setUp(self):

        super(TestDataModels, self).setUp()
        self.CREATED_AT = datetime.datetime.now()
        self.UPDATED_AT = datetime.datetime.utcnow()
        self.LAST_UDP_UPDATE = datetime.datetime.utcnow()

    def test_AmphoraMeta(self):

        new_id = uuidutils.generate_uuid()
        new_created_at = self.CREATED_AT + datetime.timedelta(minutes=5)
        new_updated_at = self.UPDATED_AT + datetime.timedelta(minutes=10)
        new_last_udp_update = self.LAST_UDP_UPDATE + datetime.timedelta(minutes=5)

        amphora_meta_data = {
            'id': new_id,
            'created_at': new_created_at,
            'updated_at': new_updated_at,
            'last_udp_update': new_last_udp_update,
            'status': None
        }

        reference_Amp_obj = data_models.AmphoraMeta(
            id=new_id,
            created_at=new_created_at,
            updated_at=new_updated_at,
            last_udp_update=new_last_udp_update,
        )

        self.assertEqual(reference_Amp_obj.__dict__, amphora_meta_data)

    def test_ThunderCluster(self):

        new_id = uuidutils.generate_uuid()
        new_created_at = self.CREATED_AT + datetime.timedelta(minutes=5)
        new_updated_at = self.UPDATED_AT + datetime.timedelta(minutes=10)
        new_username = "USER2"
        new_password = "pwd2"
        new_cluster_name = "cluster2"
        new_cluster_ip_address = "10.10.10.10"
        new_undercloud = False
        new_topology = "STANDALONE"

        thunder_cluster_data = {
            'id': new_id,
            'created_at': new_created_at,
            'updated_at': new_updated_at,
            'username': new_username,
            'password': new_password,
            'cluster_name': new_cluster_name,
            'cluster_ip_address': new_cluster_ip_address,
            'undercloud': new_undercloud,
            'topology': new_topology
        }

        reference_Thunder_Cluster_obj = data_models.ThunderCluster(
            id=new_id,
            created_at=new_created_at,
            updated_at=new_updated_at,
            username=new_username,
            password=new_password,
            cluster_name=new_cluster_name,
            cluster_ip_address=new_cluster_ip_address,
            undercloud=new_undercloud,
            topology=new_topology
        )

        self.assertEqual(reference_Thunder_Cluster_obj.__dict__, thunder_cluster_data)

    def test_Eth_Interface(self):

        new_interface_num = 2
        new_created_at = self.CREATED_AT + datetime.timedelta(minutes=5)
        new_updated_at = self.UPDATED_AT + datetime.timedelta(minutes=10)
        new_subnet_id = uuidutils.generate_uuid()
        new_vlan_id = uuidutils.generate_uuid()
        new_ve_ip_address = "192.0.2.10"
        new_port_id = uuidutils.generate_uuid()

        ethernet_interface_data = {
            'interface_num': new_interface_num,
            'created_at': new_created_at,
            'updated_at': new_updated_at,
            'subnet_id': new_subnet_id,
            'vlan_id': new_vlan_id,
            've_ip_address': new_ve_ip_address,
            'port_id': new_port_id
        }

        reference_Eth_Int_obj = data_models.EthernetInterface(
            interface_num=new_interface_num,
            created_at=new_created_at,
            updated_at=new_updated_at,
            subnet_id=new_subnet_id,
            vlan_id=new_vlan_id,
            ve_ip_address=new_ve_ip_address,
            port_id=new_port_id
        )

        self.assertEqual(reference_Eth_Int_obj.__dict__, ethernet_interface_data)

    def test_Trunk_Interface(self):

        new_interface_num = 3
        new_created_at = self.CREATED_AT + datetime.timedelta(minutes=5)
        new_updated_at = self.UPDATED_AT + datetime.timedelta(minutes=10)
        new_subnet_id = uuidutils.generate_uuid()
        new_vlan_id = uuidutils.generate_uuid()
        new_ve_ip_address = "192.0.2.10"
        new_port_id = uuidutils.generate_uuid()

        trunk_interface_data = {
            'interface_num': new_interface_num,
            'created_at': new_created_at,
            'updated_at': new_updated_at,
            'subnet_id': new_subnet_id,
            'vlan_id': new_vlan_id,
            've_ip_address': new_ve_ip_address,
            'port_id': new_port_id
        }

        reference_Trunk_Int_obj = data_models.TrunkInterface(
            interface_num=new_interface_num,
            created_at=new_created_at,
            updated_at=new_updated_at,
            subnet_id=new_subnet_id,
            vlan_id=new_vlan_id,
            ve_ip_address=new_ve_ip_address,
            port_id=new_port_id
        )

        self.assertEqual(reference_Trunk_Int_obj.__dict__, trunk_interface_data)

    def test_DeviceNetworkCluster(self):

        new_id = uuidutils.generate_uuid()
        new_created_at = self.CREATED_AT + datetime.timedelta(minutes=5)
        new_updated_at = self.UPDATED_AT + datetime.timedelta(minutes=10)
        new_thunder_id = uuidutils.generate_uuid()
        new_ethernet_interface_num = 3
        new_trunk_interface_num = 4

        device_network_cluster_data = {
            'id': new_id,
            'created_at': new_created_at,
            'updated_at': new_updated_at,
            'thunder_id': new_thunder_id,
            'ethernet_interface_num': new_ethernet_interface_num,
            'trunk_interface_num': new_trunk_interface_num
        }

        reference_Device_Net_obj = data_models.DeviceNetworkCluster(
            id=new_id,
            created_at=new_created_at,
            updated_at=new_updated_at,
            thunder_id=new_thunder_id,
            ethernet_interface_num=new_ethernet_interface_num,
            trunk_interface_num=new_trunk_interface_num
        )

        self.assertEqual(reference_Device_Net_obj.__dict__, device_network_cluster_data)

    def test_Partitions(self):

        new_id = uuidutils.generate_uuid()
        new_created_at = self.CREATED_AT + datetime.timedelta(minutes=5)
        new_updated_at = self.UPDATED_AT + datetime.timedelta(minutes=10)
        new_name = "partition-alpha"
        new_hierarchical_multitenancy = "enable"

        partition_data = {
            'id': new_id,
            'created_at': new_created_at,
            'updated_at': new_updated_at,
            'name': new_name,
            'hierarchical_multitenancy': new_hierarchical_multitenancy
        }

        partition_data_obj = data_models.Partitions(
            id=new_id,
            name=new_name,
            hierarchical_multitenancy=new_hierarchical_multitenancy,
            created_at=new_created_at,
            updated_at=new_updated_at
        )

        self.assertEqual(partition_data_obj.__dict__, partition_data)

    def test_Thunder(self):

        new_id = uuidutils.generate_uuid()
        new_created_at = self.CREATED_AT + datetime.timedelta(minutes=5)
        new_updated_at = self.UPDATED_AT + datetime.timedelta(minutes=10)
        new_vcs_device_id = 1
        new_management_ip_address = "10.0.0.74"
        new_cluster_id = uuidutils.generate_uuid()

        thunder_data = {
            'id': new_id,
            'vcs_device_id': new_vcs_device_id,
            'management_ip_address': new_management_ip_address,
            'cluster_id': new_cluster_id,
            'created_at': new_created_at,
            'updated_at': new_updated_at,
        }

        thunder_data_obj = data_models.Thunder(
            id=new_id,
            vcs_device_id=new_vcs_device_id,
            management_ip_address=new_management_ip_address,
            cluster_id=new_cluster_id,
            created_at=new_created_at,
            updated_at=new_updated_at
        )

        self.assertEqual(thunder_data_obj.__dict__, thunder_data)
