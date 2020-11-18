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

import copy
import datetime

from oslo_utils import uuidutils

from a10_octavia.common import data_models
from a10_octavia.tests.unit import base


class TestDataModels(base.BaseTaskTestCase):

    def setUp(self):

        super(TestDataModels, self).setUp()
        self.AMP_ID = uuidutils.generate_uuid()
        self.THUDER_CLUSTER_ID = uuidutils.generate_uuid()
        self.CREATED_AT = datetime.datetime.now()
        self.UPDATED_AT = datetime.datetime.utcnow()
        self.LAST_UDP_UPDATE = datetime.datetime.utcnow()
        self.SUBNET_ID = uuidutils.generate_uuid()
        self.VLAN_ID = uuidutils.generate_uuid()
        self.PORT_ID = uuidutils.generate_uuid()
        self.DEVICE_ID = uuidutils.generate_uuid()
        self.THUNDER_ID = uuidutils.generate_uuid()

        self.AMP_obj = data_models.AmphoraMeta(
            id=self.AMP_ID,
            created_at=self.CREATED_AT,
            updated_at=self.UPDATED_AT,
            last_udp_update=self.LAST_UDP_UPDATE,
            status="ACTIVE"
        )

        self.THUNDER_CLUSTER_obj = data_models.ThunderCluster(
            id=self.THUDER_CLUSTER_ID,
            created_at=self.CREATED_AT,
            updated_at=self.UPDATED_AT,
            username="USER1",
            password="pwd",
            cluster_name="cluster1",
            cluster_ip_address="192.0.2.10",
            undercloud=False,
            topology="STANDALONE"
        )

        self.ETH_INT_obj = data_models.EthernetInterface(
            interface_num=1,
            created_at=self.CREATED_AT,
            updated_at=self.UPDATED_AT,
            subnet_id=self.SUBNET_ID,
            vlan_id=self.VLAN_ID,
            ve_ip_address="192.0.2.11",
            port_id=self.PORT_ID
        )

        self.TRUNK_INT_obj = data_models.TrunkInterface(
            interface_num=2,
            created_at=self.CREATED_AT,
            updated_at=self.UPDATED_AT,
            subnet_id=self.SUBNET_ID,
            vlan_id=self.VLAN_ID,
            ve_ip_address="192.0.2.12",
            port_id=self.PORT_ID
        )

        self.DEVICE_NET_obj = data_models.DeviceNetworkCluster(
            id=self.DEVICE_ID,
            created_at=self.CREATED_AT,
            updated_at=self.UPDATED_AT,
            thunder_id=self.THUNDER_ID,
            ethernet_interface_num=1,
            trunk_interface_num=2
        )

    def test_AmphoraMeta_update(self):

        new_id = uuidutils.generate_uuid()
        new_created_at = self.CREATED_AT + datetime.timedelta(minutes=5)
        new_updated_at = self.UPDATED_AT + datetime.timedelta(minutes=10)
        new_last_udp_update = self.LAST_UDP_UPDATE + datetime.timedelta(minutes=5)
        new_status = "STANDBY"

        update_dict = {
            'id': new_id,
            'created_at': new_created_at,
            'updated_at': new_updated_at,
            'last_udp_update': new_last_udp_update,
            'status': new_status
        }

        test_Amp_obj = copy.deepcopy(self.AMP_obj)

        reference_Amp_obj = data_models.AmphoraMeta(
            id=new_id,
            created_at=new_created_at,
            updated_at=new_updated_at,
            last_udp_update=new_last_udp_update,
            status=new_status
        )

        test_Amp_obj.update(update_dict)

        self.assertEqual(reference_Amp_obj, test_Amp_obj)

    def test_ThunderCluster_update(self):

        new_id = uuidutils.generate_uuid()
        new_created_at = self.CREATED_AT + datetime.timedelta(minutes=5)
        new_updated_at = self.UPDATED_AT + datetime.timedelta(minutes=10)
        new_username = "USER2"
        new_password = "pwd2"
        new_cluster_name = "cluster2"
        new_cluster_ip_address = "10.10.10.10"
        new_undercloud = False
        new_topology = "STANDALONE"

        update_dict = {
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

        test_Thunder_Cluster_obj = copy.deepcopy(self.THUNDER_CLUSTER_obj)

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

        test_Thunder_Cluster_obj.update(update_dict)

        self.assertEqual(reference_Thunder_Cluster_obj, test_Thunder_Cluster_obj)

    def test_Eth_Interface_update(self):

        new_interface_num = 2
        new_created_at = self.CREATED_AT + datetime.timedelta(minutes=5)
        new_updated_at = self.UPDATED_AT + datetime.timedelta(minutes=10)
        new_subnet_id = uuidutils.generate_uuid()
        new_vlan_id = uuidutils.generate_uuid()
        new_ve_ip_address = "192.0.2.10"
        new_port_id = uuidutils.generate_uuid()

        update_dict = {
            'interface_num': new_interface_num,
            'created_at': new_created_at,
            'updated_at': new_updated_at,
            'subnet_id': new_subnet_id,
            'vlan_id': new_vlan_id,
            've_ip_address': new_ve_ip_address,
            'port_id': new_port_id
        }

        test_Eth_Int_obj = copy.deepcopy(self.ETH_INT_obj)

        reference_Eth_Int_obj = data_models.EthernetInterface(
            interface_num=new_interface_num,
            created_at=new_created_at,
            updated_at=new_updated_at,
            subnet_id=new_subnet_id,
            vlan_id=new_vlan_id,
            ve_ip_address=new_ve_ip_address,
            port_id=new_port_id
        )

        test_Eth_Int_obj.update(update_dict)

        self.assertEqual(reference_Eth_Int_obj, test_Eth_Int_obj)

    def test_Trunk_Interface_update(self):

        new_interface_num = 3
        new_created_at = self.CREATED_AT + datetime.timedelta(minutes=5)
        new_updated_at = self.UPDATED_AT + datetime.timedelta(minutes=10)
        new_subnet_id = uuidutils.generate_uuid()
        new_vlan_id = uuidutils.generate_uuid()
        new_ve_ip_address = "192.0.2.10"
        new_port_id = uuidutils.generate_uuid()

        update_dict = {
            'interface_num': new_interface_num,
            'created_at': new_created_at,
            'updated_at': new_updated_at,
            'subnet_id': new_subnet_id,
            'vlan_id': new_vlan_id,
            've_ip_address': new_ve_ip_address,
            'port_id': new_port_id
        }

        test_Trunk_Int_obj = copy.deepcopy(self.TRUNK_INT_obj)

        reference_Trunk_Int_obj = data_models.TrunkInterface(
            interface_num=new_interface_num,
            created_at=new_created_at,
            updated_at=new_updated_at,
            subnet_id=new_subnet_id,
            vlan_id=new_vlan_id,
            ve_ip_address=new_ve_ip_address,
            port_id=new_port_id
        )

        test_Trunk_Int_obj.update(update_dict)

        self.assertEqual(reference_Trunk_Int_obj, test_Trunk_Int_obj)

    def test_DeviceNetworkCluster_update(self):

        new_id = uuidutils.generate_uuid()
        new_created_at = self.CREATED_AT + datetime.timedelta(minutes=5)
        new_updated_at = self.UPDATED_AT + datetime.timedelta(minutes=10)
        new_thunder_id = uuidutils.generate_uuid()
        new_ethernet_interface_num = 3
        new_trunk_interface_num = 4

        update_dict = {
            'id': new_id,
            'created_at': new_created_at,
            'updated_at': new_updated_at,
            'thunder_id': new_thunder_id,
            'ethernet_interface_num': new_ethernet_interface_num,
            'trunk_interface_num': new_trunk_interface_num
        }

        test_Device_Net_obj = copy.deepcopy(self.DEVICE_NET_obj)

        reference_Device_Net_obj = data_models.DeviceNetworkCluster(
            id=new_id,
            created_at=new_created_at,
            updated_at=new_updated_at,
            thunder_id=new_thunder_id,
            ethernet_interface_num=new_ethernet_interface_num,
            trunk_interface_num=new_trunk_interface_num
        )

        test_Device_Net_obj.update(update_dict)

        self.assertEqual(reference_Device_Net_obj, test_Device_Net_obj)
