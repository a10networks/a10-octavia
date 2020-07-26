# Installation and Usage Guide for Use with Thunders

## Table of Contents
1. [Overview](#Overview)

2. [System Requirements](#System-Requirements)

3. [Installation](#Installation)

4. [Initial Configuration](#Initial-Configuration)

5. [Basic Usage](#Basic-Usage)
    * [Flat Networks](#Flat-Networks)
    * [SLB Creation](#SLB-Creation)
    * [L3v Partitions](#L3v-Partitions)
    * [High Availability](#High-Availability)

6. [Advanced Features](#Advanced-Features)
    * [Terminated HTTPS/SSL Offloading](#Terminated-HTTPS)
    * [Hierarchical Multitenancy](#Hierarchical-Multitenancy)
    * [VRRP-A VRID](#VRRPA-VRID)
    * [VLAN Networks](#VLAN-Networks)

7. [SLB Configuration Options](#SLB-Configuration-Options)

8. [Troubleshooting](#Troubleshooting)

9. [Issues and Inquiries](#Issues-and-Inquiries)

## Overview

**This solution is currently in beta stage with limited support**

The A10 Networks Octavia Driver allows for configuration of Thunder, vThunder, and AX Series Appliances deployed in
an Openstack enviroment. While the default Octavia provider leverages an "Amphora per VIP" architecture,
this provider driver uses a "Thunder per Tenant" architecture. Therefore, each tenant may only be serviced by a single
**active** Thunder device.

Before embarking on this walkthrough, it's advised that the reader has a good understanding of Openstack's Neutron and Octavia services. More information on Neutron can be found here https://docs.openstack.org/neutron/latest/admin/ and information on Octavia can be found here https://docs.openstack.org/octavia/latest/. A surface level understanding OVS will also be required.

## System Requirements 

Openstack Controller Node Minimum Requirements
* Memory: 8GB
* Disk: 20GB 
* OS: Ubuntu 18.04 or later
* OpenStack (Nova, Neutron, Etc): Stein Release
* Octavia version: >=4.1.1, <5.0.0.0rc1 (Stein versions)

Openstack Compute Node Minimum Requirements
* vCPUs: 8
* Memory: 16GB
* Disk: 40GB
* OS: Ubuntu 18.04 or later
* 2 NICs
* Openstack (Nova, Neutron, Etc): Stein Release

ACOS Device Requirements
* ACOS version: ACOS 4.1.4 GR1 P2
* AXAPI version: 3.0

## Installation

*Note: This guide assumes that Openstack has already been deployed and Octavia has already been configured.*

```shell
pip install a10-octavia
```

## Setup and Initial Configuration

*Note: The following configurations should be done as an Openstack admin user*

### Step 1. Enable A10 provider driver in Octavia config file
Add the following to `/etc/octavia/octavia.conf` under the `api-settings` section

```shell
enabled_provider_drivers = a10: 'The A10 Octavia driver.'

default_provider_driver = a10
```

### Step 2. Restart Openstack Octavia services
Use `systemctl` or similar a command to restart the Octavia API service. 

### Step 3. Create the a10-octavia.conf file
```shell
mkdir /etc/a10
touch a10-octavia.conf
```

#### Sample a10-octavia.conf for hardware devices

```shell
[a10_controller_worker]
network_driver = a10_octavia_neutron_driver

[hardware_thunder]
devices = [
                    {
                     "project_id": "demo",
                     "ip_address": "10.0.0.4",
                     "username": "myuser",
                     "password": "mypass",
                     "device_name": "device1"
                     },
                     {
                     "project_id": "alt_demo",
                     "ip_address": "10.0.0.5",
                     "username": "myuser2",
                     "password": "mypass2",
                     "device_name": "device2"
                     }
             ]
```

*Note: It's important to not have trailing commas after final value entires, closing brackets, and closing braces*

### Step 4. Run the database migration


```shell
$ pip show a10-octavia
Name: a10-octavia
Version: 0.2.0
Summary: A10 Octavia Provider Driver
Home-page: https://github.com/a10networks/a10-octavia
Author: A10 Networks
Author-email: opensource@a10networks.com
License: UNKNOWN
Location: /usr/local/lib/python2.7/dist-packages
Requires: octavia, python-novaclient, octavia-lib, tenacity, acos-client, python-barbicanclient, python-glanceclient, pyOpenSSL, taskflow
```

From the `/usr/local/lib/python2.7/dist-packages/a10_octavia/db/migration` folder execute the followinga

```shell
alembic upgrade head
```

If versioning error occurs, delete all entries in the `alembic_version` table from `octavia` database and re-run the above command.

```shell
mysql> use octavia;
mysql> DELETE FROM alembic_version;
```

*Note: Octavia verisons less than 4.1.1 have the `alembic_migrations` table instead*


### Step 5. Register and start a10-octavia services

With `a10-octavia` installed, run the following command to register the services

```shell
install-a10-octavia
```

This will install systemd services with names - `a10-controller-worker.service`, `a10-health-manager.service` and `a10-house-keeper.service`.

#### Make sure the services are up and running.

```shell
systemctl status a10-controller-worker.service a10-health-manager.service a10-house-keeper.service
```

You can start/stop the services using systemctl/service commands.

## Basic Usage

This section will cover how to setup a basic HA deployment in a flat network environment. This requires 2 hardware Thunders connected to an external switch. Documentation on Thunder configuration can be found here https://documentation.a10networks.com/latestversions.html

#### Initial Setup

There will be 2 Apache server instances running in the internal tenant network

```
openstack image create --disk-format qcow2 --container-format bare --public --file Apache_server1.qcow2 apache_server
openstack flavor create --vcpu 1 --ram 2048 --disk 20 apache_flavor
```

Before continuing be sure to have completed the steps in the [#Installation] section

#### Flat Networks

In Openstack, flat networks are simply networks without VLAN tagging or any other forms of network segmentation where all instances reside on the same network. In this deployment, the host has two ethernet interfaces, `eth0` which acts the data interface and `eth1` which acts as the host management interface. The data interface `eth0` is connected to the `18.64.10.0/24` subnet and `eth1` is connected to the `18.64.4.0/24` subnet. 

Each Thunder device should have 2 interfaces. The managment interface should be on `18.64.4.0/24`, but the other must be left unset as the driver will configure it at runtime.

### Step 1: Create an external provider network

```
openstack network create --share --external --provider-physical-network public --provider-network-type flat public_net
openstack subnet create --subnet-range 18.64.10.0/24 --gateway 18.64.10.1 --network public_net public_subnet
```

### Step 2: Configure Security Group

```
openstack security group rule create --ingress --protocol tcp --dst-port 80 apache
```

### Step 3: Launch Apache Servers

```
openstack server create --image apache_server --flavor apache_flavor --security-group apache --network public_net server1
openstack server create --image apache_server --flavor apache_flavor --security-group apache --network public_net server2
```

In this example server1 dhcp's to `18.64.10.227` and server2 dchp's to `18.64.10.54`

### Step 4: Update a10-octavia.conf

We'll start with just a single Thunder device. The `ip_address` is the management IP of the device

```shell
[a10_controller_worker]
network_driver = a10_octavia_neutron_driver

[hardware_thunder]
devices = [
                    {
                     "project_id": "demo",
                     "device_name": "device1"
                     "ip_address": "18.64.10.6",
                     "username": "myuser",
                     "password": "mypass"
                     }
             ]
```

After modifying the `a10-octavia.conf` file be sure to execute `sudo systemctl restart a10-controller-worker.service` so that changes can take effect.

### Step 5: Create the load balancer

```shell
openstack loadbalancer create --vip-subnet-id public_subnet --name lb1
```

### Step 6: Create the listener

```shell
openstack loadbalancer listener create --protocol HTTP --protocol-port 8080 --name l1 lb1 
```

### Step 7: Create the pool

```shell
openstack loadbalancer pool create --protocol HTTP --lb-algorithm ROUND_ROBIN --listener l1 --name pool1
```

### Step 8: Create and associate members with the real servers

```shell
openstack loadbalancer member create --address 18.64.10.227 --subnet-id provider-vlan-12-subnet --protocol-port 80 --name mem1 pool1
openstack loadbalancer member create --address 18.64.10.54 --subnet-id provider-vlan-12-subnet --protocol-port 80 --name mem2 pool1
```

#### Using L3V Partitioning

Partitions that provide Layer 3-7 support are referred to as L3V partitions. Each L3V partition can contain either SLB or CGN application resources, networking resources, and system resources. In essence, each L3V partition can operate as an independent ACOS device. An L3V partition can be created, configured and deleted by a root admin and configured by a partition admin. The partition admin has access to configure all applications, network, and system resources within the partition.

```shell
[a10_controller_worker]
network_driver = a10_octavia_neutron_driver

[hardware_thunder]
devices = [
                    {
                     "project_id": "CorpA_Eng",
                     "device_name": "device1"
                     "ip_address": "18.64.10.6",
                     "username": "myuser",
                     "password": "mypass",
                     "partition_name": "Engineering"
                     }
             ]
```

Two changes have occured in the configuration. The first is the addition of the `partition_name` key. The partition name doesn't have to any correlation with the `project_id`. However, I have changed the `project_id` in this example away from the original `demo` project. It's best practice for each L3V partition to only be assigned to single project given that "each L3V partition can operate as an independent ACOS device" as stated above. This is enforced when more than one device exists in the `devices` list.

#### Configuring High Availability

It is expected for an operator to configure two hardware devices in a VRRPA set and an aVCS cluster. For a guide on this please refrence https://documentation.a10networks.com/ACOS/414x/ACOS_4_1_4-GR1-P2/html/vcs-Responsive%20HTML5/vcs/vcs-deploy/Initial_VCS_Deployment.htm

The IP address provided in the `[hardware_thunder]` configuration group must be the floating IP of the aVCS cluster.

```shell
[a10_controller_worker]
network_driver = a10_octavia_neutron_driver

[hardware_thunder]
devices = [
                    {
                     "project_id": "CorpB_Finance",
                     "device_name": "device1"
                     "ip_address": "18.64.10.112",     <------ aVCS/VRRPA Cluster Floating IP Address
                     "username": "myuser",
                     "password": "mypass"
                     }
             ]
```

No other configuration settings need to be specified when using a flat network topology.

## Advanced Usage

### Terminated HTTPS

### Hierarchical Multitenancy

To enable this set `enable_hierarchical_multitenancy=True` under the `[a10_global]` config group

#### Using Parent Partitions

To enable this set `use_parent_partition=True` under the `[a10_global]` config group. This will not take effect unless `enable_hierarchical_multitenancy=True` also.

### VRRP-A VRID

To support VRRPA floating IP config for hardware devices, `vrid_floating_ip` setting can be included along with above config at global or local level.
The valid values for `vrid_floating_ip` can be set as `dhcp`, partial IP octets such as '45', '.45', '0.0.45' or a full IPv4 address.

##### How is the VRID Floating IP Allocated?

**Case 1: DHCP **

In this case, when a member is created, the VRID floating IP is allocated from the available ip range in the subnet it was created in. Please note, should a member be added to the pool from a different subnet, a VRID floating IP will be allocated from that subnet even if one has already been allocated from another subnet.

**Case 2: Static IP **

In this case, when a member is created, the VRID floating IP is allocated using the provided static IP. If a partial IP be provided, an attempt will be made to join the partial IP with the member's subnet. Should the provided static IP be out of range of the member's subnet, then an error will be thrown.


#### 3da. For setting VRRPA floating IP in a10-octavia.conf at global level

<pre>
[a10_global]
<b>vrid_floating_ip = "dhcp"</b>
</pre>

#### 3db. For setting VRRPA floating IP in a10-octavia.conf at local level

For local, `vrid_floating_ip` setting can be mentioned inside the `[hardware_devices]`.

<pre>
[hardware_thunder]
devices = [
                    {
                     "project_id":"&lt;project_id&gt;",
                     "ip_address":"10.0.0.4",
                     "username":"&lt;username&gt;",
                     "password":"&lt;password&gt;",
                     "device_name":"&lt;device_name&gt;"
                     <b>"vrid_floating_ip": ".45"</b>
                     },
                     {
                     "project_id":"&lt;another_project_id&gt;",
                     "ip_address":"10.0.0.5",
                     "username":"&lt;username&gt;",
                     "password":"&lt;password&gt;",
                     "device_name":"&lt;device_name&gt;",
                     "partition_name" : "&lt;partition_name&gt;"
                     <b>"vrid_floating_ip": "10.10.13.45"</b>
                     }
             ]
</pre>

Note: If the option is set at the local and global level, then the local configuration option shall be used.
 
### VLAN Networks

#### Configuring A10-Octavia to Work with VLAN networks

In the VLAN Network setup, for configuring the VLAN and Virtual Ethernet(VE) interfaces in the hardware thunder device, `network_type` setting in `[A10_GLOBAL]` configuration section should be set to "vlan" string. VLAN and VE configuration for the ethernet interfaces or trunk interfaces should be specified in `interface_vlan_map` setting in the `[hardware_thunder]` device configuration section. The `interface_vlan_map` setting is a json map. For a single device it can have key "device_1" with data or two keys "device_1" and "device_2" for aVCS cluster device. While configuring aVCS cluster, floating IP must be provided in `ip_address` field and respective management IP for both devices in `mgmt_ip_address` fields. The `vcs_device_id` value must be provided as either 1 or 2 based on current aVCS cluster status.

#### Configuring VLAN and VE for Ethernet Interfaces

With each device the ethernet interfaces settings can be specified as an array within the key "ethernet_interfaces". Each interface information contains a key "interface_num" indicating the ethernet interface number on which the "vlan_map" config will be applied. The key "vlan_map" contains an array with VLANs informations corresponding to the interface_num. The VLAN information contains "vlan_id" and the VE information. The VE information consists of either partial or complete "ve_ip" or a flag "use_dhcp" set to "True".

##### Configuring VLAN and VE for Trunk Interfaces

In order to configure VLAN and VE on trunk interfaces, the hardware thunder should have the trunk-group configurations set on the corresponding ethernet interfaces. Also system promiscuous-mode should be enabled on the hardware thunder, before applying the VLAN and VE on trunk interfaces. The "trunk_interfaces" configuration is similar to "ethernet_interfaces" configuration. Only difference being the "interface_num" within "trunk_interfaces" configuration specifies the trunk-group number on which the VLAN and VE needs to be configured.

Full list of options can be found here: [Config Options Module](https://github.com/a10networks/a10-octavia/blob/master/a10_octavia/common/config_options.py)

*Note: trailing "," are invalid in device config type*

##### How is the VE IP Allocated?

**Case 1: DHCP **

In this case, when a member is created, the VRID floating IP is allocated from the available ip range in the subnet it was created in. Please note, should a member be added to the pool from a different subnet, a VRID floating IP will be allocated from that subnet even if one has already been allocated from another subnet.

**Case 2: Static IP **

In this case, when a member is created, the VRID floating IP is allocated using the provided static IP. If a partial IP be provided, an attempt will be made to join the partial IP with the member's subnet. Should the provided static IP be out of range of the member's subnet, then an error will be thrown.

##### Sample a10-octavia.conf for VLAN and VE settings

```shell
<pre>
[a10_controller_worker]
network_type = "vlan"

[hardware_thunder]
devices = [
              {
               "project_id":"<project_id>",
               "ip_address":<device IP / aVCS cluster floating IP>,
               "username":"<username>",
               "password":"<password>",
               "device_name":"<device_name>"
               "interface_vlan_map": {
                   "device_1": {
                       "vcs_device_id": 1,
                       "mgmt_ip_address": "10.0.0.74",
                       "ethernet_interfaces": [{
                           "interface_num": 1,
                           "vlan_map": [
                               {"vlan_id": 11, "use_dhcp": "True"}
                           ]
                       }],
                       "trunk_interfaces": [{
                           "interface_num": 1,
                           "vlan_map": [
                               {"vlan_id": 11, "ve_ip": ".10"},
                               {"vlan_id": 12, "ve_ip": ".10"}
                           ]
                       }],
                   }
               }
              }
          ]
</pre>
```



## SLB Configuration Options

These settings are added to the `a10-octavia.conf` file. They allow the operator to configure options not exposed by the Openstack CLI.

*WARNING: Any option specified here will apply globally meaning all projects and devices*

#### Global section config example
```shell
[a10_global]
enable_hierarchical_multitenancy = False
use_parent_partition = False
```
#### Loadbalancer/virtual server config example
```shell
[slb]
arp_disable = False
default_virtual_server_vrid = "10"
```

#### Listener/virtual port config example
```shell
[listener]
ipinip = False
no_dest_nat = False
ha_conn_mirror = False
template_virtual_port = "vport_template"
template_tcp = "tcp_template"
template_policy = "policy_temp1"
autosnat = True
conn_limit = 5000
template_http = "http_template"
use_rcv_hop_for_resp = False
```

#### Pool/service group config example
```shell
[service_group]
template_server = "server_template"
template_port = "port_template"
template_policy = "policy_template"`
```

#### Member config example
```shell
[server]
conn_limit = 5000
conn_resume = 1
template_server = "server_template"
```

Full list of options can be found here: [Config Options Module](https://github.com/a10networks/a10-octavia/blob/master/a10_octavia/common/config_options.py)

## Troubleshooting
You may check logs of the services using `journalctl` commands. For example:

```shell
$ journalctl -af --unit a10-controller-worker.service
$ journalctl -af --unit a10-health-manager.service
$ journalctl -af --unit a10-house-keeper.service
```

## Issues and Inquiries
For all issues, please send an email to support@a10networks.com 

For general inquiries, please send an email to opensource@a10netw
