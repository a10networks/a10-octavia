# Installation and Deployment Guide for Use with Thunders

## Table of Contents
1. [Overview](#Overview)

2. [System Requirements](#System-Requirements)

3. [Installation](#Installation)

4. [Initial Configuration](#Initial-Configuration)

5. [Basic Usage](#Basic-Usage)
    * [Flat Networks](#Flat-Networks)
    * [L3v Partitions](#Using-L3V-Partitioning)

6. [High Availability](#High-Availability)
    * [VRRP-A VRID](#VRRP-A-VRIDs-and-Floating-IPs)
    
7. [VLAN Networks](#VLAN-Networks)
   * [Trunk Interfaces](#Trunk-Interfaces)

8. [Advanced Features](#Advanced-Features)
    * [L7 Rules, Policies, and AFLEX](#L7-Rules,-Policies,-and-AFLEX)
    * [Terminated HTTPS/SSL Offloading](#Terminated-HTTPS)
    * [Hierarchical Multitenancy](#Hierarchical-Multitenancy)
    * [Octavia Flavor Support](#Octavia-Flavor-Support)
    * [SLB Configuration Options](#SLB-Configuration-Options)

9. [Troubleshooting](#Troubleshooting)
    * [Pending States](#Pending-States)

10. [Issues and Inquiries](#Issues-and-Inquiries)

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
* OS: Ubuntu 18.04+ or Centos 7/8
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

#### Step 1. Enable A10 provider driver in Octavia config file
Add the following to `/etc/octavia/octavia.conf` under the `api-settings` section

```shell
enabled_provider_drivers = a10: 'The A10 Octavia driver.'

default_provider_driver = a10
```

#### Step 2. Restart Openstack Octavia services
Use `systemctl` or similar a command to restart the Octavia API service.

If using devstack the command is: `sudo systemctl restart devstack@o-api.service`

#### Step 3. Create the a10-octavia.conf file
```shell
mkdir /etc/a10
touch a10-octavia.conf
```

##### Sample a10-octavia.conf for hardware devices

```shell
[a10_controller_worker]
network_driver = a10_octavia_neutron_driver

[hardware_thunder]
devices = [
                    {
                     "project_id": "3330d7ff659841a2a685b18af0f7a099",
                     "ip_address": "10.0.0.4",
                     "username": "myuser",
                     "password": "mypass",
                     "device_name": "device1"
                     },
                     {
                     "project_id": "0c7b84309e6f419db149d2e613b1b72a",
                     "ip_address": "10.0.0.5",
                     "username": "myuser2",
                     "password": "mypass2",
                     "device_name": "device2"
                     }
             ]
```

*Note: It's important to not have trailing commas after final value entires, closing brackets, and closing braces*

#### Step 4. Run the database migration


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

From the `/usr/local/lib/python2.7/dist-packages/a10_octavia/db/migration` folder execute the following

```shell
alembic upgrade head
```

If versioning error occurs, delete all entries in the `alembic_version` table from `octavia` database and re-run the above command.

```shell
mysql> use octavia;
mysql> DELETE FROM alembic_version;
```

*Note: Octavia verisons less than 4.1.1 have the `alembic_migrations` table instead*


#### Step 5. Register and start a10-octavia services

With `a10-octavia` installed, run the following command to register the services

```shell
install-a10-octavia
```

This will install systemd services with names - `a10-controller-worker.service`, `a10-health-manager.service` and `a10-house-keeper.service`.

##### Make sure the services are up and running.

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

### Flat Networks

In Openstack, flat networks are simply networks without VLAN tagging or any other forms of network segmentation where all instances reside on the same network. In this deployment, the host has two ethernet interfaces, `eth0` which acts the data interface and `eth1` which acts as the host management interface. The data interface `eth0` is connected to the `18.64.10.0/24` subnet and `eth1` is connected to the `18.64.4.0/24` subnet. 

Each Thunder device should have 2 interfaces. The managment interface should be on `18.64.4.0/24`, but the other must be left unset as the driver will configure it at runtime.

#### Step 1: Create the provider bridge

```
sudo ovs-vsctl add-br br-ex
```

#### Step 2: Assign the NIC `eth0` to the bridge

```
sudo ip addr flush dev eth0
sudo ovs-vsctl add-port br-ex eth0
sudo ip addr add 18.64.4.5/24 dev br-ex
sudo ip link set br-ex up
```

#### Step 3: Add the following to the `ml2` config found under `/etc/neutron/plugins/ml2/ml2.conf`

##### Step 3a: Add the bridge mapping

```
[ovs]
bridge_mappings = public:br-ex
```

The name of the provider physical network in this case will simply be `public`.

##### Step 3b: Set the following options under the ml2 section
```
[ml2]
tenant_network_types =
extension_drivers = port_security
mechanism_drivers = openvswitch
type_drivers = flat
```

There may be pre-existing type drivers. Feel free to keep those if they are in use.

#### Step 4: Restart the neutron server
```
service neutron-server restart
```

#### Step 5: Create an external provider network

```
openstack network create --share --external --provider-physical-network public --provider-network-type flat public_net
openstack subnet create --subnet-range 18.64.10.0/24 --gateway 18.64.10.1 --network public_net public_subnet
```

#### Step 6: Configure Security Group

```
openstack security group create apache
openstack security group rule create --ingress --protocol tcp --dst-port 80 apache
```

#### Step 7: Launch Apache Servers

*Note: Before preforming this step, ensure that your enviromental variables have `OS_PROJECT_NAME=demo` as for some reason the server command doesn't have a project option*

```
openstack server create --image apache_server --flavor apache_flavor --security-group apache --network public_net server1
openstack server create --image apache_server --flavor apache_flavor --security-group apache --network public_net server2
```

In this example server1 dhcp's to `18.64.10.227` and server2 dhcp's to `18.64.10.54`

#### Step 8: Fetch Project ID
Before continuing, we need to decide which project will own the loadbalancer.

```
$ openstack project list
+----------------------------------+--------------------+
| ID                               | Name               |
+----------------------------------+--------------------+
| 0c7b84309e6f419db149d2e613b1b72a | alt_demo           |
| 268a09b7ace8489f8d5487edce54fba6 | project_a          |
| 3330d7ff659841a2a685b18af0f7a099 | demo               |
| 62030f8ac3094b43a2cff8fc81f8c99f | invisible_to_admin |
| 7840a9998e4245419b462896191cb61f | admin              |
| 9295be60ac674a3d951f4bed4e8d02df | service            |
| a0fccfcd5b2347a8b1ecbd78012d9cfa | project_b          |
+----------------------------------+--------------------+
```

I'll be creating the loadbalancer on the `demo` project, so in the next section I'll be setting `project_id` to `3330d7ff659841a2a685b18af0f7a099`

#### Step 9: Update a10-octavia.conf

We'll start with just a single Thunder device. The `ip_address` is the management IP of the device. The `autosnat` setting is being used here as the Thunder is not being used as the gateway nor are we leveraging DSR thus we need to set this option to ensure that the member servers reply back to the Thunder.

```shell
[a10_controller_worker]
network_driver = a10_octavia_neutron_driver

[listener]
autosnat = True

[hardware_thunder]
devices = [
                    {
                     "project_id": "3330d7ff659841a2a685b18af0f7a099",
                     "device_name": "device1",
                     "ip_address": "18.64.4.6",
                     "username": "myuser",
                     "password": "mypass"
                     }
             ]
```

After modifying the `a10-octavia.conf` file be sure to execute `sudo systemctl restart a10-controller-worker.service` so that changes can take effect.

#### Step 10: Create the load balancer

```shell
openstack loadbalancer create --vip-subnet-id public_subnet --name lb1 --project demo
```

```shell
+---------------------+--------------------------------------+
| Field               | Value                                |
+---------------------+--------------------------------------+
| admin_state_up      | True                                 |
| created_at          | 2020-07-30T07:58:28                  |
| description         |                                      |
| flavor_id           | None                                 |
| id                  | 6a830cc0-7798-436b-92da-219f4feba54  |
| listeners           |                                      |
| name                | lb1                                  |
| operating_status    | OFFLINE                              |
| pools               |                                      |
| project_id          | 3330d7ff659841a2a685b18af0f7a099     |
| provider            | a10                                  |
| provisioning_status | PENDING_CREATE                       |
| updated_at          | None                                 |
| vip_address         | 18.64.10.191                         |
| vip_network_id      | ae50079f-4694-4da7-942c-168542da5def |
| vip_port_id         | 4d923736-3683-476d-8cf1-66592bd39d83 |
| vip_qos_policy_id   | None                                 |
| vip_subnet_id       | d9edc710-b995-4554-9412-218d989d952d |
+---------------------+--------------------------------------+
```

#### Check the Thunder device

```shell
!
interface management 
  ip address dhcp 
!
interface ethernet 1 
!
!
slb virtual-server 6a830cc0-7798-436b-92da-219f4feba544 18.64.10.191
!
!
cloud-services meta-data 
  enable 
  provider openstack 
!
end
```

Note that the name of the `virtual-server` is the `id` of the `loadbalancer` object on the Openstack side. This will be true of the names for all SLB objects created via Openstack.

##### Common Issue #1
If you encounter an error state at this step, make sure to check the journalctl logs.

```
$ openstack loadbalancer list
+--------------------------------------+------+----------------------------------+--------------+---------------------+----------+
| id                                   | name | project_id                       | vip_address  | provisioning_status | provider |
+--------------------------------------+------+----------------------------------+--------------+---------------------+----------+
| 6a830cc0-7798-436b-92da-219f4feba544 | lb1  | 3330d7ff659841a2a685b18af0f7a099 | 18.64.10.191 | ERROR               | a10      |
+--------------------------------------+------+----------------------------------+--------------+---------------------+----------+
```

```
$ journalctl -af --unit a10-controller-worker.service
...
Jul 30 07:24:44 docu a10-octavia-worker[20712]: ERROR oslo_messaging.rpc.server ComputeBuildException: Failed to build compute instance due to: No Glance images are tagged with  tag.
Jul 30 07:24:44 docu a10-octavia-worker[20712]: ERROR oslo_messaging.rpc.server
```

**Issue:** An incorrect `project_id` was added to the device list or the loadbalancer create command was not given the right `--project` option value

**Cause:** By default, the A10 Octavia driver tries to spawn a vThunder instance to serve as the loadbalancer. As we are working with hardware Thunders instead of vThunders we have not provided vThunder image information in the configuration file.

**Fix:** Ensure the `project_id` is correct in the `a10-octavia.conf` and that you have restarted the `a10-controller-worker.service`. Ensure that the proper `--project` value option being provided matches the `project_id` or name of the project assocciated with the given `project_id`

#### Step 11: Create the listener

```shell
openstack loadbalancer listener create --protocol HTTP --protocol-port 8080 --name l1 lb1 
```

```shell
+-----------------------------+--------------------------------------+
| Field                       | Value                                |
+-----------------------------+--------------------------------------+
| admin_state_up              | True                                 |
| connection_limit            | -1                                   |
| created_at                  | 2020-07-31T00:33:50                  |
| default_pool_id             | None                                 |
| default_tls_container_ref   | None                                 |
| description                 |                                      |
| id                          | 5096c0f6-3ca2-4111-8b11-fe88ad936602 |
| insert_headers              | None                                 |
| l7policies                  |                                      |
| loadbalancers               | 6a830cc0-7798-436b-92da-219f4feba544 |
| name                        | l1                                   |
| operating_status            | OFFLINE                              |
| project_id                  | 3330d7ff659841a2a685b18af0f7a099     |
| protocol                    | HTTP                                 |
| protocol_port               | 8080                                 |
| provisioning_status         | PENDING_CREATE                       |
| sni_container_refs          | []                                   |
| timeout_client_data         | 50000                                |
| timeout_member_connect      | 5000                                 |
| timeout_member_data         | 50000                                |
| timeout_tcp_inspect         | 0                                    |
| updated_at                  | None                                 |
| client_ca_tls_container_ref | None                                 |
| client_authentication       | NONE                                 |
| client_crl_container_ref    | None                                 |
+-----------------------------+--------------------------------------+
```

##### Check the Thunder device

```shell
!
slb virtual-server 6a830cc0-7798-436b-92da-219f4feba544 18.64.10.191 
  port 8080 http 
    name 5096c0f6-3ca2-4111-8b11-fe88ad936602 
    extended-stats 
    source-nat auto 
!
```

*Note: A listener in openstack is a virtual port (called just "port") on the Thunder side*

#### Step 12: Create the pool

```shell
openstack loadbalancer pool create --protocol HTTP --lb-algorithm ROUND_ROBIN --listener l1 --name pool1
```

```shell
+----------------------+--------------------------------------+
| Field                | Value                                |
+----------------------+--------------------------------------+
| admin_state_up       | True                                 |
| created_at           | 2020-07-31T00:42:09                  |
| description          |                                      |
| healthmonitor_id     |                                      |
| id                   | d140e112-f37b-4f6a-8dd1-12f5c8f137e3 |
| lb_algorithm         | ROUND_ROBIN                          |
| listeners            | 5096c0f6-3ca2-4111-8b11-fe88ad936602 |
| loadbalancers        | 6a830cc0-7798-436b-92da-219f4feba544 |
| members              |                                      |
| name                 | pool1                                |
| operating_status     | OFFLINE                              |
| project_id           | 3330d7ff659841a2a685b18af0f7a099     |
| protocol             | HTTP                                 |
| provisioning_status  | PENDING_CREATE                       |
| session_persistence  | None                                 |
| updated_at           | None                                 |
| tls_container_ref    | None                                 |
| ca_tls_container_ref | None                                 |
| crl_container_ref    | None                                 |
| tls_enabled          | False                                |
+----------------------+--------------------------------------+
```

##### Check the Thunder device

```
!
slb service-group d140e112-f37b-4f6a-8dd1-12f5c8f137e3 tcp 
!
slb virtual-server 6a830cc0-7798-436b-92da-219f4feba544 18.64.10.191 
  port 8080 http 
    name 5096c0f6-3ca2-4111-8b11-fe88ad936602 
    extended-stats 
    source-nat auto 
    service-group d140e112-f37b-4f6a-8dd1-12f5c8f137e3 
!
```

*Note: A pool in openstack is a service group on the Thunder side*

#### Step 13: Create the health monitor

```
openstack loadbalancer healthmonitor create --delay 10 --max-retries 4 --timeout 5 --type HTTP --url-path /healthcheck pool1
```

```
+---------------------+--------------------------------------+
| Field               | Value                                |
+---------------------+--------------------------------------+
| project_id          | 0e567ea4ea824228b06fce04805c8c16     |
| name                |                                      |
| admin_state_up      | True                                 |
| pools               | d140e112-f37b-4f6a-8dd1-12f5c8f137e3 |
| created_at          | 2020-08-24T04:47:22                  |
| provisioning_status | PENDING_CREATE                       |
| updated_at          | None                                 |
| delay               | 10                                   |
| expected_codes      | 200                                  |
| max_retries         | 4                                    |
| http_method         | GET                                  |
| timeout             | 5                                    |
| max_retries_down    | 3                                    |
| url_path            | /healthcheck                         |
| type                | HTTP                                 |
| id                  | e2fdd166-4c37-4499-ba5d-6f285a582942 |
| operating_status    | OFFLINE                              |
| http_version        | None                                 |
| domain_name         | None                                 |
+---------------------+--------------------------------------+
```

##### Check the Thunder
```
health monitor e2fdd166-4c37-4499-ba5d-6f285a582942 
  retry 4 
  override-port 8080
  interval 10 
  method http port 8080 expect response-code 200 url GET /healthcheck 
!         
slb service-group d140e112-f37b-4f6a-8dd1-12f5c8f137e3 tcp 
  health-check e2fdd166-4c37-4499-ba5d-6f285a582942 
!       
slb virtual-server 6a830cc0-7798-436b-92da-219f4feba54 18.64.10.191
  port 8080 http 
    name 5096c0f6-3ca2-4111-8b11-fe88ad936602
    extended-stats 
    source-nat auto 
    service-group d140e112-f37b-4f6a-8dd1-12f5c8f137e3 
```

#### Step 14: Create and associate members with the real servers

```shell
openstack loadbalancer member create --address 18.64.10.227 --subnet-id provider-flat-subnet --protocol-port 80 --name mem1 pool1
openstack loadbalancer member create --address 18.64.10.54 --subnet-id provider-flat-subnet --protocol-port 80 --name mem2 pool1
```

```shell
+---------------------+--------------------------------------+
| Field               | Value                                |
+---------------------+--------------------------------------+
| address             | 18.64.10.227                         |
| admin_state_up      | True                                 |
| created_at          | 2020-07-31T06:41:22                  |
| id                  | 0b187895-9bd9-4a62-9a9a-8bed1a96eb6d |
| name                | mem1                                 |
| operating_status    | NO_MONITOR                           |
| project_id          | 3330d7ff659841a2a685b18af0f7a099     |
| protocol_port       | 80                                   |
| provisioning_status | PENDING_CREATE                       |
| subnet_id           | None                                 |
| updated_at          | None                                 |
| weight              | 1                                    |
| monitor_port        | None                                 |
| monitor_address     | None                                 |
| backup              | False                                |
+---------------------+--------------------------------------+

+---------------------+--------------------------------------+
| Field               | Value                                |
+---------------------+--------------------------------------+
| address             | 18.64.10.54                          |
| admin_state_up      | True                                 |
| created_at          | 2020-07-31T06:41:52                  |
| id                  | f805282f-301c-4134-bd0d-7ad2086b83cd |
| name                | mem2                                 |
| operating_status    | NO_MONITOR                           |
| project_id          | 3330d7ff659841a2a685b18af0f7a099     |
| protocol_port       | 80                                   |
| provisioning_status | PENDING_CREATE                       |
| subnet_id           | None                                 |
| updated_at          | None                                 |
| weight              | 1                                    |
| monitor_port        | None                                 |
| monitor_address     | None                                 |
| backup              | False                                |
+---------------------+--------------------------------------+
```

##### Check the Thunder device

```
!
health monitor e2fdd166-4c37-4499-ba5d-6f285a582942 
  retry 4 
  override-port 8080
  interval 10 
  method http port 8080 expect response-code 200 url GET /healthcheck 
!  
slb server 0b187895-9bd9-4a62-9a9a-8bed1a96eb6d 18.64.10.227 
  conn-resume 1 
  port 80 tcp 
!
  slb server f805282f-301c-4134-bd0d-7ad2086b83cd 18.64.10.54 
  conn-resume 1 
  port 80 tcp 
! 
slb service-group d140e112-f37b-4f6a-8dd1-12f5c8f137e3 tcp
  health-check e2fdd166-4c37-4499-ba5d-6f285a582942 
  member 0b187895-9bd9-4a62-9a9a-8bed1a96eb6d 80
  member f805282f-301c-4134-bd0d-7ad2086b83cd 80
!       
slb virtual-server 6a830cc0-7798-436b-92da-219f4feba544 18.64.10.191
  port 8080 http 
    name 5096c0f6-3ca2-4111-8b11-fe88ad936602
    extended-stats 
    source-nat auto 
    service-group d140e112-f37b-4f6a-8dd1-12f5c8f137e3 
!    
```

*Note: A member in openstack comprised of a server and member on the Thunder side (Openstack member == Thunder member+server).*

### L7 load balancing

When load balancing at the application layer, it's expected that the backend pools are serving up a wide array of content. One pool of servers may be responsible for delivering images while another exclusively servers static HTML and CSS pages. As such, the loadbalancer requires further information to direct the requests such as the URI, HTTP headers, etc.

Octavia provides L7 load balancing through L7 rules and policies. L7 rules are singular tests which return either a true or false whenever their conditions are checked against. L7 rules can be bundled together under an L7 policy. When all the L7 rules under an L7 policy evaluate to true, the L7 policy preforms an action such as rejecting a request.

For more information on L7 load balancing with Opentack see https://docs.openstack.org/octavia/queens/user/guides/l7.html

#### Step 15: Add an L7 Policy
```
openstack loadbalancer l7policy create --action REJECT --name policy1 l1
```

```
+---------------------+--------------------------------------+
| Field               | Value                                |
+---------------------+--------------------------------------+
| listener_id         | efc80bff-b6cb-478f-83e8-1d9e812bd2ed |
| description         |                                      |
| admin_state_up      | True                                 |
| rules               |                                      |
| project_id          | 0e567ea4ea824228b06fce04805c8c16     |
| created_at          | 2020-08-21T20:00:39                  |
| provisioning_status | PENDING_CREATE                       |
| updated_at          | None                                 |
| redirect_pool_id    | None                                 |
| redirect_url        | None                                 |
| redirect_prefix     | None                                 |
| action              | REJECT                               |
| position            | 1                                    |
| id                  | 997dab6f-f74b-48a6-90de-6489131eba91 |
| operating_status    | OFFLINE                              |
| name                | policy1                              |
| redirect_http_code  | None                                 |
+---------------------+--------------------------------------+
```

#### Step 16: Add an L7 Rule
```
openstack loadbalancer l7rule create --compare-type REGEX --type HEADER --key "reject" --value "request" policy1
```

```
+---------------------+--------------------------------------+
| Field               | Value                                |
+---------------------+--------------------------------------+
| created_at          | 2020-08-21T20:05:36                  |
| compare_type        | REGEX                                |
| provisioning_status | PENDING_CREATE                       |
| invert              | False                                |
| admin_state_up      | True                                 |
| updated_at          | None                                 |
| value               | request                              |
| key                 | reject                               |
| project_id          | 0e567ea4ea824228b06fce04805c8c16     |
| type                | HEADER                               |
| id                  | a01732c8-47f0-4990-8477-7078fc7162fa |
| operating_status    | OFFLINE                              |
+---------------------+--------------------------------------+
```

##### Check the Thunder

```
slb server 0b187895-9bd9-4a62-9a9a-8bed1a96eb6d 18.64.10.227 
  conn-resume 1 
  port 80 tcp 
!       
slb server f805282f-301c-4134-bd0d-7ad2086b83cd 18.64.10.54 
  conn-resume 1 
  port 80 tcp 
!       
slb service-group d140e112-f37b-4f6a-8dd1-12f5c8f137e3 tcp 
  member 0b187895-9bd9-4a62-9a9a-8bed1a96eb6d 80 
  member f805282f-301c-4134-bd0d-7ad2086b83cd 80 
!       
slb virtual-server 6a830cc0-7798-436b-92da-219f4feba544 18.64.10.191
  port 8080 http 
    name 5096c0f6-3ca2-4111-8b11-fe88ad936602
    extended-stats 
    source-nat auto 
    aflex 997dab6f-f74b-48a6-90de-6489131eba91   <------ Addition of the aflex script
    service-group d140e112-f37b-4f6a-8dd1-12f5c8f137e3 
!   
```

The L7 Rules and Policies are translated into AFLEX scripts on the Thunder side. For further information on AFLEX scripts see https://documentation.a10networks.com/ACOS/414x/ACOS_4_1_4-GR1-P2/html/aFleX_Ref_Guide-Responsive%20HTML5/aFleX_Ref_Guide/Getting_Started_with_aFleX/Getting_Started_with_aFleX.htm?rhtocid=toc1.0_1#TOC_Advantages_of_Using

##### Make requests

**First let's make a regular curl request against the vip by logging into one of the members/servers**

```
root@client:~# curl https://18.64.10.191:9001 --insecure
----------------------
Page from server1    

----------------------
```

**Now let's make a request with "reject:request" in the header**
```
root@client:~# curl http://18.64.10.191:8080 --HEADER reject:request
curl: (52) Empty reply from server
```

#### L7 load balancing with HTTPS

For L7 load balancing to be possible, we need to the ability to inspect the contents of a given request. When HTTPS is in use, Openstack treats the requests as raw TCP traffic since it's encrypted and undecipherable. However, when using SSL offloading, also known as Terminated HTTPS, the Thunder device is tasked with decrypting the HTTPS traffic instead of the backend webserver. Not only does this allow for L7 loadbalancing to occur, it also lessens the load on the web server as decrypting HTTPS traffic is CPU intensive.

Please see the [Terminated-HTTPS](#Terminated-HTTPS) section for information on how to configure SSL Offloading.

### Using L3V Partitioning

Partitions that provide Layer 3-7 support are referred to as L3V partitions. Each L3V partition can contain either SLB or CGN application resources, networking resources, and system resources. In essence, each L3V partition can operate as an independent ACOS device. An L3V partition can be created, configured and deleted by a root admin and configured by a partition admin. The partition admin has access to configure all applications, network, and system resources within the partition.

```shell
[a10_controller_worker]
network_driver = a10_octavia_neutron_driver

[hardware_thunder]
devices = [
                    {
                     "project_id": "CorpA_Eng",
                     "device_name": "device1"
                     "ip_address": "18.64.4.6",
                     "username": "myuser",
                     "password": "mypass",
                     "partition_name": "Engineering"
                     }
             ]
```

Two changes have occured in the configuration. The first is the addition of the `partition_name` key. The partition name doesn't have to any correlation with the `project_id`. However, I have changed the `project_id` in this example away from the original `demo` project. It's best practice for each L3V partition to only be assigned to single project given that "each L3V partition can operate as an independent ACOS device" as stated above. This is enforced when more than one device exists in the `devices` list.

## High Availability

It is expected for an operator to configure two hardware devices in a VRRPA set and an aVCS cluster. For a guide on this please refrence https://documentation.a10networks.com/ACOS/414x/ACOS_4_1_4-GR1-P2/html/vcs-Responsive%20HTML5/vcs/vcs-deploy/Initial_VCS_Deployment.htm

The IP address provided in the `[hardware_thunder]` configuration group must be the floating IP of the aVCS cluster.

```shell
[a10_controller_worker]
network_driver = a10_octavia_neutron_driver

[listener]
autosnat = True

[hardware_thunder]
devices = [
                    {
                     "project_id": "CorpB_Finance",
                     "device_name": "device1"
                     "ip_address": "18.64.4.112",     <------ aVCS/VRRPA Cluster Floating IP Address
                     "username": "myuser",
                     "password": "mypass"
                     }
             ]
```

No other configuration settings need to be specified when using a flat network topology.

### VRRP-A VRIDs and Floating IPs

<Insert Graphic Here>

A10's VRRP-A protocol allows for high availability deployments of ACOS devices. While it derives from VRRP (Virtual Router Redundancy Protocol), it is a seperate solution and cannot inter-operate with VRRP. For further information, please visit the following link 
https://documentation.a10networks.com/ACOS/414x/ACOS_4_1_4-GR1-P2/html/vrrp-a-Responsive%20HTML5/vrrp-a-new/vrrp-a-overview/vrrp-a-overview.htm

#### Step 1: Initial configuration

This section requires 2 Thunder devices which have gone through the basic aVCS/VRRPA configuration steps. Please visit the following link to find configuration details https://documentation.a10networks.com/ACOS/414x/ACOS_4_1_4-GR1-P2/html/vcs-Responsive%20HTML5/vcs/vcs-deploy/Initial_VCS_Deployment.htm 

In this section, there are 2 projects being used `dev_team_1` and `dev_team_2` which have the project id's of `6e8ab3d60e6248d09a97b76dda362397` and `8c589595eb924356bcfb1416f7b35551` respectively.

The `dev_team_1` project has members on subnet `10.10.12.0/24` where as `dev_team_2` has members on subnet `10.0.13.0/24`.

#### Step 2: Set the VRID in the a10-octavia.conf

In order to differentiate virtual routers, the last byte of the MAC address is configurable.

```
[a10_global]
vrid = 0
```

#### Step 3: Configure the VRID Floating IP

The VRID Floating IP provides a gateway IP which "floats" between the devices configured together as a VRRPA pair allowing the real servers to maintain their connectivity should one of the Thunders go down. 

##### How is the VRID Floating IP Allocated?

**Case 1: DHCP **

When a member is created, the VRID floating IP is allocated from the available ip range in the subnet it was created in. Please note, should a member be added to the pool from a different subnet, a VRID floating IP will be allocated from that subnet even if one has already been allocated from another subnet.

**Case 2: Static IP **

When a member is created, the VRID floating IP is allocated using the provided static IP. If a partial IP be provided, an attempt will be made to join the partial IP with the member's subnet. Should the provided static IP be out of range of the member's subnet, then an error will be thrown.

##### VRRP-A VRID and L3V partitions

By default, L3V partitions and the shared partition have their own VRIDs independent of one another. For example, the shared, CorpA, and CorpB partitions could all be assigned VRID 0, but no conflict will occur as at a lower level these are reconfigured to avoid collision.

#### Step 3a: For setting VRRPA floating IP in a10-octavia.conf at global level

```
[a10_global]
vrid_floating_ip = "dhcp"

[a10_controller_worker]
network_driver = a10_octavia_neutron_driver

[listener]
autosnat = True

[hardware_thunder]
devices = [
                    {
                     "project_id": "6e8ab3d60e6248d09a97b76dda362397",
                     "device_name": "device1",
                     "ip_address": "18.64.4.6",
                     "username": "myuser",
                     "password": "mypass",
                     "partition_name": "dev1"
                     },
                    {
                     "project_id": "8c589595eb924356bcfb1416f7b35551",
                     "device_name": "device1",
                     "ip_address": "18.64.4.6",
                     "username": "myuser",
                     "password": "mypass",
                     "partition_name": "dev2"
                     }
             ]
```

Be sure to restart the `a10-controller-worker` service to load the config file with `sudo systemctl restart a10-controller-worker.service`

#### Step 3b: For setting VRRPA floating IP in a10-octavia.conf at the project level

Setting a configuration at the "Project Level" is akin to setting it in the partition itself. For this reason, the A10 Octavia driver only supports assigning one subnet per partition when using VRRPA.

```
[a10_controller_worker]
network_driver = a10_octavia_neutron_driver

[listener]
autosnat = True

[hardware_thunder]
devices = [
                    {
                     "project_id": "6e8ab3d60e6248d09a97b76dda362397",
                     "device_name": "device1",
                     "ip_address": "18.64.4.6",
                     "username": "myuser",
                     "password": "mypass",
                     "partition_name": "dev1",
                     "vrid_floating_ip": "10.10.12.46"          <----- VRID Floating IP set here
                     },
                    {
                     "project_id": "8c589595eb924356bcfb1416f7b35551",
                     "device_name": "device1",
                     "ip_address": "18.64.4.6",
                     "username": "myuser",
                     "password": "mypass",
                     "partition_name": "dev2",
                     "vrid_floating_ip": "10.10.13.45"         <----- VRID Floating IP set here
                     }
             ]
```

*Note: If the option is set at the local and global level, then the local configuration option shall be used.*

Once again be sure to restart the `a10-controller-worker` service to load the config file.

#### Step 4: Create the loadbalancers, listeners, and pools

##### Step 4a: Create the slb tree for dev_team_1
```
openstack loadbalancer create --vip-subnet-id provider-vlan-11-subnet --name dev_1_vip --project dev_team_1
openstack loadbalancer listener create --protocol HTTP --protocol-port 9001 dev_1_vip --name http_l1
openstack loadbalancer pool create --protocol HTTP --lb-algorithm ROUND_ROBIN --listener http_l1 --name pool1
```

##### Step 4b: Create the slb tree for dev_team_2
```
openstack loadbalancer create --vip-subnet-id provider-vlan-12-subnet --name dev_2_vip --project dev_team_2
openstack loadbalancer listener create --protocol HTTP --protocol-port 9001 dev_2_vip --name http_l2
openstack loadbalancer pool create --protocol HTTP --lb-algorithm ROUND_ROBIN --listener http_l2 --name pool2
```

#### Step 5: Add the members

#### Step 5a: Add a member for dev_team_1
```
openstack loadbalancer member create --address 10.10.12.18 --subnet-id dev-team-1-subnet --protocol-port 9001 --name mem1 pool1
```

#### Step 5b: Add a member for dev_team_2
```
openstack loadbalancer member create --address 10.10.13.102 --subnet-id dev-team-2-subnet --protocol-port 9001 --name mem1 pool2
```

##### Check the Thunder

Show run of partition `dev1`

```
vrrp-a vrid 0 
  floating-ip 10.10.12.46
!       
slb server b8213d65-f86e-6152-e8fd-af3d712f9cb8 10.10.12.18
  conn-resume 1 
  port 9001 tcp 
!       
slb service-group 77d5b73a-da72-4176-abf8-645ce675f317 tcp 
  member b8213d65-f86e-6152-e8fd-af3d712f9cb8 9001 
!       
slb virtual-server 67de121c-781c-3f72-45c7-5871cd421e98 10.0.11.165 
  port 9001 http 
    name 5db50bef-a723-c78d-97e8-2c9e812a462d 
    extended-stats 
    source-nat auto 
    service-group 77d5b73a-da72-4176-abf8-645ce675f317 
!  
```

Show run of partition `dev2`

```
vrrp-a vrid 0 
  floating-ip 10.10.13.45
!       
slb server a8223e65-f86e-4154-98bd-ef3d711f7006 10.10.13.102
  conn-resume 1 
  port 9001 tcp 
!       
slb service-group 79dcb73b-da76-4176-cdf5-145ce432f317 tcp 
  member a8223e65-f86e-4154-98bd-ef3d711f7006 9001 
!       
slb virtual-server a76b101b-351b-4e7c-a519-5975eb430e88 10.0.11.107
  port 9001 http 
    name efc80bff-b6cb-478f-83e8-1d9e812bd2ed 
    extended-stats 
    source-nat auto 
    service-group 79dcb73b-da76-4176-cdf5-145ce432f317
!  
```

#### Step 7: Set the Floating IP as the default gateway

This step will vary from system to system.

For Ubuntu:
```
ip route del default via 192.168.1.254
ip route add default via 10.10.12.46
```

For CentOS:
```
route del default gw 192.168.1.1
route add default gw 10.10.12.46
```

## VLAN Networks

### Environment Overview

As with the basic usage section, the host has two ethernet interfaces, `eth0` which acts the data interface and `eth1` which acts as the host management interface.

<Insert Graphic Here>

### Step 1: Create the vlan provider bridge

```
sudo ovs-vsctl add-br br-vlanp
```

### Step 2: Assign the NIC `eth0` to the bridge

```
sudo ip addr flush dev eth0
sudo ovs-vsctl add-port br-vlanp eth0
```

### Step 3: Add the following to the `ml2` config found under `/etc/neutron/plugins/ml2/ml2.conf`

#### Step 3a: Add the bridge mapping

```
[ovs]
bridge_mappings = provider:br-vlanp
```

The name of the provider physical network in this case will simply be `provider`.

#### Step 3b: Set the vlan range

```
[ml2_type_vlan]
network_vlan_ranges = provider:11:14
```

For this example, we'll only be using VLANs 11, 12, 13, and 14. Note that the name of the provider physical network is required an in this case is just `provider`.

#### Step 3c: Set the following options under the ml2 section
```
[ml2]
tenant_network_types =
extension_drivers = port_security
mechanism_drivers = openvswitch
type_drivers = vlan
```

There may be pre-existing type drivers. Feel free to keep those if they are in use.

### Step 4: Restart the neutron server
```
service neutron-server restart
```

### Step 5: Create the VLAN networks
```
openstack network create --external --provider-segment 11 --provider-network-type vlan --provider-physical-network provider --share provider-vlan-11
openstack network create --external --provider-segment 12 --provider-network-type vlan --provider-physical-network provider --share provider-vlan-12
openstack network create --external --provider-segment 13 --provider-network-type vlan --provider-physical-network provider --share provider-vlan-13
openstack network create --external --provider-segment 14 --provider-network-type vlan --provider-physical-network provider --share provider-vlan-14
```

### Step 6: Create the subnets
```
openstack subnet create --ip-version 4 --network provider-vlan-11 --subnet-range 10.0.11.0/24 provider-vlan-11-subnet
openstack subnet create --ip-version 4 --network provider-vlan-12 --subnet-range 10.0.12.0/24 provider-vlan-12-subnet
openstack subnet create --ip-version 4 --network provider-vlan-13 --subnet-range 10.0.13.0/24 provider-vlan-13-subnet
openstack subnet create --ip-version 4 --network provider-vlan-14 --subnet-range 10.0.14.0/24 provider-vlan-14-subnet
```

### Step 7: Configure the a10-octavia.conf to use 2 ethernet interfaces

```
[a10_global]
network_type = vlan

[a10_controller_worker]
network_driver = a10_octavia_neutron_driver

[listener]
autosnat = True

[hardware_thunder]
devices = [
                    {
                     "project_id": "6e8ab3d60e6248d09a97b76dda362397",
                     "device_name": "device1",
                     "ip_address": "18.64.4.6",
                     "username": "myuser",
                     "password": "mypass",
                     "interface_vlan_map": {
                         "device_1": {
                             "mgmt_ip_address": "18.64.4.6",
                             "ethernet_interfaces": [{
                                 "interface_num": 1,
                                 "vlan_map": [
                                     {"vlan_id": 11, "ve_ip": ".6"}
                                 ]}, 
                                 {   
                                 "interface_num": 2,
                                 "vlan_map": [
                                     {"vlan_id": 12, "ve_ip": ".5"}
                                 ]   
                             }]
                          }   
                        }
                     }
             ]
```

In this first config setup, we are going to have 1 project whose VIP will be on VLAN 11 and whose members will be on VLAN 12. As such, the first ethernet interface `interface_num: 1` of the device is will be tagged with VLAN 11. When using the ACOS devices in routed/gateway mode, as is standard for high availability deployments, we configure IPs on the VLAN networks which that interface can use to route traffic.

To enable this functionality, we first create an object known as a virtual ethernet (VE) interface. We then assign the interface to a VLAN and provide it an IP address. In this scenario, the ethernet interface itself keeps it's IP address meta address of `0.0.0.0`. This configuration two VE interfaces will be created to support each VLAN.

The first, VE 11 (VE ids are equivalent of the VLAN id), will have it's last IP octet set to `.6`. The rest of the IP address wil be inferred based upon the subnet IP of network whose network segment (VLAN id) is set to 11. In this case, the name of that is `provider-vlan-11`. The second, VE 12, will have it's last IP octet defined as `.5`.

#### How is the VE IPs Allocated?

**Case 1: DHCP **


1. When a loadbalancer is created, the VE IP is allocated from the available ip range in the subnet it was created in.

2. When a member is created, the VE IP is allocated from the available ip range in the subnet it was created in. Please note, should a member be added to the pool from a different subnet, a VE IP will be allocated from that subnet even if one has already been allocated from another subnet.

**Case 2: Static IP **

When a member or loadbalancer is created, the VE IP is allocated using the provided static IP. If a partial IP be provided, an attempt will be made to join the partial IP with the objects's subnet. Should the provided static IP be out of range of the objects's subnet, then an error will be thrown.

*Note: Whenever an object is updated


### Trunk Interfaces

#### Step 8: Configure the a10-octavia.conf to use 1 ethernet interface and 1 trunk group

##### Step 8a: Creating the trunk group

In order to configure VLAN and VE on trunk interfaces, the hardware thunder should have the trunk-group configurations set on the corresponding ethernet interfaces. The `system promiscuous-mode` setting should be enabled on the hardware thunder, before applying the VLAN and VE on trunk interfaces. For further information on configuring a trunk interface see https://documentation.a10networks.com/ACOS/414x/ACOS_4_1_4-GR1-P2/html/network-Responsive%20HTML5/network/Layer_2/network_trunk/network_trunk.htm#XREF_65732_Use_the_CLI_to

The "trunk_interfaces" configuration is similar to "ethernet_interfaces" configuration. Only difference being the "interface_num" within "trunk_interfaces" configuration specifies the trunk-group number on which the VLAN and VE needs to be configured.

#### Step 8b: Edit the a10-octavia.conf file
Let's set ethernet interfaces 2 and 3 into trunk group 1. Then we'll to allow it to send packets bound for VLANs 12 and 13 with the last octet of both VE IPs set to `.10`. We'll keep the VIP on VLAN 11.

```shell
[a10_global]
network_type = vlan

[a10_controller_worker]
network_driver = a10_octavia_neutron_driver

[hardware_thunder]
devices = [
                    {
                     "project_id": "6e8ab3d60e6248d09a97b76dda362397",
                     "device_name": "device1",
                     "ip_address": "18.64.4.6",
                     "username": "myuser",
                     "password": "mypass",
                     "interface_vlan_map": {
                         "device_1": {
                             "mgmt_ip_address": "18.64.4.6",
                             "ethernet_interfaces": [{
                                 "interface_num": 1,
                                 "vlan_map": [
                                     {"vlan_id": 11, "ve_ip": ".6"}
                                 ]}, 
                             }],
                             "trunk_interfaces": [{
                                 "interface_num": 1,
                                  "vlan_map": [
                                      {"vlan_id": 12, "ve_ip": ".10"},
                                      {"vlan_id": 13, "ve_ip": ".10"}
                                  ]
                             }],
                         }
                      }
                 }
          ]
```

#### Step 9: Restart the controller worker

```
sudo systemctl restart a10-controller-worker.service
```

#### Step 10: Create the loadbalancer

```
openstack loadbalancer create --vip-subnet-id provider-vlan-11-subnet --name dev_1_vip --project dev_team_1
```

##### Check the Thunder

Show run output
```
active-partition 6e8ab3d60e624
!
!
vlan 11 
  tagged ethernet 1
  router-interface ve 11 
!
interface ve 11 
  ip address 10.0.11.6
!
! 
slb virtual-server c99bc159-af0a-4391-a458-32f459ce3069 10.0.11.103 
!       
end
``` 

Show interface brief output
```
Port    Link  Dupl  Speed  Trunk Vlan MAC             IP Address          IPs  Name
------------------------------------------------------------------------------------
mgmt    Up    auto  auto   N/A   N/A  5254.003d.d641  10.0.0.78/24          1
1       Up    Full  10000  none  Tag  5254.00d9.a2d7  0.0.0.0/0             0
2       Disb  Full  10000  none  Tag  5254.0007.4a7b  0.0.0.0/0             0
3       Disb  None  None   none  1    5254.00d1.514c  0.0.0.0/0             0
4       Disb  None  None   none  1    5254.00fa.c887  0.0.0.0/0             0
ve11    Up    N/A   N/A    N/A   11   5254.00d9.a2d7  10.0.11.6/24          1
```

A few points, first we can see that ethernet interface 1 is up though it's IP is still set to `0.0.0.0/0`. Next, observe that `ve11` has the ip address of `10.0.11.6` having taken the host address `.6` from our configuration file and `10.0.11` network address from the `provider-vlan-11-subnet` cidr. Finally, the virtual server has been provided the ip address of `10.0.11.103`.


#### Step 11: Create a listener and pool

Before we can add members, we obviously need a listener and pool. Let's create those quickly.

```
openstack loadbalancer listener create --protocol HTTP --protocol-port 9001 dev_1_vip --name http_l1
openstack loadbalancer pool create --protocol HTTP --lb-algorithm ROUND_ROBIN --listener http_l1 --name pool1
```

#### Step 12: Create the members

##### Step 12a: a member for real server1 on VLAN 12

```
openstack loadbalancer member create --address 10.0.12.172 --subnet-id provider-vlan-12-subnet --protocol-port 9001 --name mem1 pool1
```

##### Step 12b: Create a member for real server2 on VLAN 13

```
openstack loadbalancer member create --address 10.0.13.123 --subnet-id provider-vlan-13-subnet --protocol-port 9001 --name mem2 pool1
```

##### Check the Thunder

Show run output

```
!
system promiscuous-mode 
!
vlan 11 
  tagged ethernet 1
  router-interface ve 11 
!
vlan 12 
  tagged trunk 1
  router-interface ve 12 
!
vlan 13 
  tagged trunk 1
  router-interface ve 13 
!
interface management 
  ip address dhcp 
!       
interface ethernet 1 
  enable 
!       
interface ethernet 2 
  enable 
  trunk-group 1 
!       
interface ethernet 3
  enable
  trunk-group 1 
!       
interface ethernet 4
!       
interface ve 11 
  ip address 10.0.11.6 255.255.255.0
!       
interface ve 12 
  ip address 10.0.12.10 255.255.255.0 
!       
interface ve 13 
  ip address 10.0.13.10 255.255.255.0 
!       
!       
slb server 54d70433-b753-45e3-a14d-23e937e61d1e 10.0.12.172 
  conn-resume 1 
  port 9001 tcp 
!       
slb server 7b3266e7-55f1-4cde-bf09-533b34dcb119 10.0.13.123 
  conn-resume 1 
  port 9001 tcp 
!       
slb service-group b30806b8-8fc4-4272-aae7-580176b4abde tcp 
  member 54d70433-b753-45e3-a14d-23e937e61d1e 9001 
  member 7b3266e7-55f1-4cde-bf09-533b34dcb119 9001 
!       
slb virtual-server a76b101b-351b-4e7c-a519-5975eb430e88 10.0.11.165 
  port 9001 http 
    name efc80bff-b6cb-478f-83e8-1d9e812bd2ed 
    extended-stats 
    source-nat auto 
    service-group b30806b8-8fc4-4272-aae7-580176b4abde 
```

Show interface brief output

```
Port    Link  Dupl  Speed  Trunk Vlan MAC             IP Address          IPs  Name
------------------------------------------------------------------------------------
mgmt    Up    auto  auto   N/A   N/A  5254.003d.d641  10.0.0.78/24          1
1       Up    Full  10000  none  Tag  5254.00d9.a2d7  0.0.0.0/0             0
2       Up    Full  10000  1     Tag  5254.0007.4a7b  0.0.0.0/0             0
3       Up    Full  10000  1     Tag  5254.00d1.514c  0.0.0.0/0             0
4       Disb  None  None   none  1    5254.00fa.c887  0.0.0.0/0             0
ve11    Up    N/A   N/A    N/A   11   5254.00fa.c887  10.0.11.6/24          1
ve12    Up    N/A   N/A    N/A   12   5254.00d9.a2d7  10.0.12.10/24         1
ve13    Up    N/A   N/A    N/A   13   5254.0007.4a7b  10.0.13.10/24         1
```


##### A note on VLAN sharing


##### Configuring for High Availability

Now to throw high availability into the mix. If you haven't yet, please read over section #High-Availability section to review the basics of configuring a high availability deployment.

```shell
[a10_global]
network_type = vlan

[a10_controller_worker]
network_driver = a10_octavia_neutron_driver

[hardware_thunder]
devices = [
                    {
                     "project_id": "6e8ab3d60e6248d09a97b76dda362397",
                     "device_name": "device1",
                     "ip_address": "18.64.4.6",
                     "username": "myuser",
                     "password": "mypass",
                     "vrid_floating_ip": ".8", <----- A VRRPA floating IP must be used
                     "interface_vlan_map": {
                         "device_1": {
                             "vcs_device_id": 1,   <------ VCS ID needed to differentiate devices
                             "mgmt_ip_address": "18.64.4.6",
                             "ethernet_interfaces": [{
                                 "interface_num": 1,
                                 "vlan_map": [
                                     {"vlan_id": 11, "ve_ip": ".6"}
                                 ]}, 
                             }],
                             "trunk_interfaces": [{
                                 "interface_num": 1,
                                  "vlan_map": [
                                      {"vlan_id": 12, "ve_ip": ".10"},
                                      {"vlan_id": 13, "ve_ip": ".10"}
                                  ]
                             }],
                         },
                         "device_2": {
                             "vcs_device_id": 2,
                             "mgmt_ip_address": "18.64.4.7",
                             "ethernet_interfaces": [{
                                 "interface_num": 1,
                                 "vlan_map": [
                                     {"vlan_id": 11, "ve_ip": ".5"}
                                 ]}, 
                             }],
                             "trunk_interfaces": [{
                                 "interface_num": 1,
                                  "vlan_map": [
                                      {"vlan_id": 12, "ve_ip": ".9"},
                                      {"vlan_id": 13, "ve_ip": ".9"}           <----- VE IPs must be different between devices
                                  ]
                             }],
                         }
                      }
                 }
          ]
```

The first thing to notice is the addition of the `vcs_device_id`. This can be found by executing the command `show vcs summary`. The next is the inclusion of a VRID floating IP which will be used by backend servers to ensure their connectivity remains in the case of failover. Finally, the VE IPs have distinct values between two devices.

## Advanced Usage

### Terminated HTTPS

Terminated HTTPS (also refferred to as SSL Offloading) sees the loadbalancer taking on the CPU intensive task of decrypting the HTTPS traffic. This feature requires Barbican (Openstack's key management service) to be installed and running.

*Note: Further information regarding Barbican can be found here https://docs.openstack.org/barbican/latest/*

#### Step 1: Create the certificate and key

```
openssl req -new -newkey rsa:4096 -x509 -sha256 -days 365 -nodes -out MyCertificate.crt -keyout MyKey.key -subj "/C=US/ST=CA/L=San Jose/O=Openstack/OU=OSTeam/CN=a10networks.com"
```

#### Step 2: Upload the cert to the Barbican keystore

```
openstack secret store --secret-type certificate --file MyCertificate.crt --name mycert
```

```
+---------------+--------------------------------------------------------------------------------+
| Field         | Value                                                                          |
+---------------+--------------------------------------------------------------------------------+
| Secret href   | http://18.64.4.110/key-manager/v1/secrets/41aaa1fc-1fb8-43c9-9fee-241e5bda2282 |
| Name          | mycert                                                                         |
| Created       | None                                                                           |
| Status        | None                                                                           |
| Content types | None                                                                           |
| Algorithm     | aes                                                                            |
| Bit length    | 256                                                                            |
| Secret type   | certificate                                                                    |
| Mode          | cbc                                                                            |
| Expiration    | None                                                                           |
+---------------+--------------------------------------------------------------------------------+
```

*Note: Sufficient user privileges are required to preform this action.*

#### Step 3: Upload the key to the Barbican keystore

```
openstack secret store --secret-type private --file MyKey.key --name mykey
```

```
+---------------+--------------------------------------------------------------------------------+
| Field         | Value                                                                          |
+---------------+--------------------------------------------------------------------------------+
| Secret href   | http://18.64.4.110/key-manager/v1/secrets/903abe35-da04-4ecb-99c0-5bb1f44322d9 |
| Name          | mykey                                                                          |
| Created       | None                                                                           |
| Status        | None                                                                           |
| Content types | None                                                                           |
| Algorithm     | aes                                                                            |
| Bit length    | 256                                                                            |
| Secret type   | private                                                                        |
| Mode          | cbc                                                                            |
| Expiration    | None                                                                           |
+---------------+--------------------------------------------------------------------------------+
```

#### Step 4: Create a secrets container
```
openstack secret container create --name mytls1 --secret "certificate=http://18.64.4.110/key-manager/v1/secrets/41aaa1fc-1fb8-43c9-9fee-241e5bda2282" --secret "private_key=http://18.64.4.110/key-manager/v1/secrets/903abe35-da04-4ecb-99c0-5bb1f44322d9" --type certificate
```

```
+----------------+-----------------------------------------------------------------------------------+
| Field          | Value                                                                             |
+----------------+-----------------------------------------------------------------------------------+
| Container href | http://18.64.4.110/key-manager/v1/containers/00764d1e-d305-4dac-8d4e-1ee0582f80be |
| Name           | mytls1                                                                            |
| Created        | None                                                                              |
| Status         | ACTIVE                                                                            |
| Type           | certificate                                                                       |
| Certificate    | http://18.64.4.110/key-manager/v1/secrets/41aaa1fc-1fb8-43c9-9fee-241e5bda2282    |
| Intermediates  | None                                                                              |
| Private Key    | http://18.64.4.110/key-manager/v1/secrets/903abe35-da04-4ecb-99c0-5bb1f44322d9    |
| PK Passphrase  | None                                                                              |
| Consumers      | None                                                                              |
+----------------+-----------------------------------------------------------------------------------+
```

#### Step 5: Create a loadbalancer

```
openstack loadbalancer create --vip-subnet-id public_subnet --name lb_term --project demo
```

```
+---------------------+--------------------------------------+
| Field               | Value                                |
+---------------------+--------------------------------------+
| admin_state_up      | True                                 |
| created_at          | 2020-08-17T22:39:15                  |
| description         |                                      |
| flavor_id           | None                                 |
| id                  | f56ad4f2-5827-4f5a-83dd-1c4092e0d3c3 |
| listeners           |                                      |
| name                | dev_1_vip                            |
| operating_status    | OFFLINE                              |
| pools               |                                      |
| project_id          | 0e567ea4ea824228b06fce04805c8c16     |
| provider            | a10                                  |
| provisioning_status | PENDING_CREATE                       |
| updated_at          | None                                 |
| vip_address         | 18.64.10.103                         |
| vip_network_id      | e6b2e88c-e254-447e-b8cf-419bbd6b8509 |
| vip_port_id         | ef6bba10-97ae-4c10-81f6-26cf69d94abf |
| vip_qos_policy_id   | None                                 |
| vip_subnet_id       | 8f7ca7c3-4d3e-416d-b1c5-0d002e3ab7b8 |
+---------------------+--------------------------------------+
```

#### Step 6: Create a Terminated HTTPS listener

```
openstack loadbalancer listener create --protocol TERMINATED_HTTPS --default-tls-container-ref http://18.64.4.110/key-manager/v1/containers/00764d1e-d305-4dac-8d4e-1ee0582f80be --protocol-port 9001 lb_term --name list_term
```

```
+-----------------------------+-----------------------------------------------------------------------------------+
| Field                       | Value                                                                             |
+-----------------------------+-----------------------------------------------------------------------------------+
| admin_state_up              | True                                                                              |
| connection_limit            | -1                                                                                |
| created_at                  | 2020-08-17T23:14:32                                                               |
| default_pool_id             | None                                                                              |
| default_tls_container_ref   | http://18.64.4.110/key-manager/v1/containers/00764d1e-d305-4dac-8d4e-1ee0582f80be |
| description                 |                                                                                   |
| id                          | faa7edcf-0630-4a06-8488-66b0ac9cdef3                                              |
| insert_headers              | None                                                                              |
| l7policies                  |                                                                                   |
| loadbalancers               | c99bc159-af0a-4391-a458-32f459ce3069                                              |
| name                        | https_l1                                                                          |
| operating_status            | OFFLINE                                                                           |
| project_id                  | 0e567ea4ea824228b06fce04805c8c16                                                  |
| protocol                    | TERMINATED_HTTPS                                                                  |
| protocol_port               | 9001                                                                              |
| provisioning_status         | PENDING_CREATE                                                                    |
| sni_container_refs          | []                                                                                |
| timeout_client_data         | 50000                                                                             |
| timeout_member_connect      | 5000                                                                              |
| timeout_member_data         | 50000                                                                             |
| timeout_tcp_inspect         | 0                                                                                 |
| updated_at                  | None                                                                              |
| client_ca_tls_container_ref | None                                                                              |
| client_authentication       | NONE                                                                              |
| client_crl_container_ref    | None                                                                              |
+-----------------------------+-----------------------------------------------------------------------------------+
```

#### Check the Thunder
```
!       
slb template client-ssl faa7edcf-0630-4a06-8488-66b0ac9cdef3 
  cert mycert 
  key mykey 
!       
slb virtual-server c99bc159-af0a-4391-a458-32f459ce3069 18.64.10.103 
  port 9001 https 
    name faa7edcf-0630-4a06-8488-66b0ac9cdef3 
    extended-stats 
    source-nat auto 
    service-group 5e5264da-a7e7-4c54-ac85-a3b53129bcac 
    template client-ssl faa7edcf-0630-4a06-8488-66b0ac9cdef3 
!
```

The cert and key have both been uploaded under the `client-ssl` template which shares the same name (5547bbf4-7fa0-4481-ba38-bad4f6ef5032) that of the listener. This makes it easier to track down which ssl template is destined for which virtual port when inspecting the configuration on the Thunder.

#### Step 6: Create a pool

```
openstack loadbalancer pool create --protocol HTTP --lb-algorithm ROUND_ROBIN --listener list_term --name pool1
```

```
+----------------------+--------------------------------------+
| Field                | Value                                |
+----------------------+--------------------------------------+
| admin_state_up       | True                                 |
| created_at           | 2020-08-17T23:14:42                  |
| description          |                                      |
| healthmonitor_id     |                                      |
| id                   | 5e5264da-a7e7-4c54-ac85-a3b53129bcac |
| lb_algorithm         | ROUND_ROBIN                          |
| listeners            | faa7edcf-0630-4a06-8488-66b0ac9cdef3 |
| loadbalancers        | c99bc159-af0a-4391-a458-32f459ce3069 |
| members              |                                      |
| name                 | pool1                                |
| operating_status     | OFFLINE                              |
| project_id           | 0e567ea4ea824228b06fce04805c8c16     |
| protocol             | HTTP                                 |
| provisioning_status  | PENDING_CREATE                       |
| session_persistence  | None                                 |
| updated_at           | None                                 |
| tls_container_ref    | None                                 |
| ca_tls_container_ref | None                                 |
| crl_container_ref    | None                                 |
| tls_enabled          | False                                |
+----------------------+--------------------------------------+
```

Only certain pool and listener protocols are compatible together. For the full matrix see https://docs.openstack.org/api-ref/load-balancer/v2/#protocol-combinations-listener-pool

#### Step 7: Create a member

```
openstack loadbalancer member create --address 18.64.10.54 --subnet-id provider-flat-subnet --protocol-port 80 --name mem3 pool1
```

```
+---------------------+--------------------------------------+
| Field               | Value                                |
+---------------------+--------------------------------------+
| address             | 18.64.10.54                          |
| admin_state_up      | True                                 |
| created_at          | 2020-08-17T23:14:50                  |
| id                  | 68daeb94-383a-4488-aa60-9f8954ef4529 |
| name                | mem1                                 |
| operating_status    | NO_MONITOR                           |
| project_id          | 0e567ea4ea824228b06fce04805c8c16     |
| protocol_port       | 80                                   |
| provisioning_status | PENDING_CREATE                       |
| subnet_id           | 8f7ca7c3-4d3e-416d-b1c5-0d002e3ab7b8 |
| updated_at          | None                                 |
| weight              | 1                                    |
| monitor_port        | None                                 |
| monitor_address     | None                                 |
| backup              | False                                |
+---------------------+--------------------------------------+
```

#### Check the Thunder

```
slb server 28028354-5d1f-4158-98f0-dfe0d924b192 18.64.10.54 
  conn-resume 1 
  port 80 tcp 
!       
slb service-group 5e5264da-a7e7-4c54-ac85-a3b53129bcac tcp 
  member 28028354-5d1f-4158-98f0-dfe0d924b192 80 
!       
slb template client-ssl faa7edcf-0630-4a06-8488-66b0ac9cdef3 
  cert mycert 
  key mykey 
!       
slb virtual-server c99bc159-af0a-4391-a458-32f459ce3069 18.64.10.103 
  port 9001 https 
    name faa7edcf-0630-4a06-8488-66b0ac9cdef3 
    extended-stats 
    source-nat auto 
    service-group 5e5264da-a7e7-4c54-ac85-a3b53129bcac 
    template client-ssl faa7edcf-0630-4a06-8488-66b0ac9cdef3 
!   
```

#### Send traffic to ensure HTTPS connectivity

```
root@client:~# curl https://18.64.10.103:9001 --insecure
----------------------
Page from server1    

----------------------
```

*Note: Since we are using a self-signed certificate, the `insecure` option is required*

#### Health Monitoring with Terminated HTTPS

Pools can contain members with distinct ports, yet only one health monitor can be attributed to a given pool. As pools can also only have one listener, the listener’s port is used to determine the health monitor port instead of an arbitrary member.  This results in issues when using Terminated HTTPS as it's standard to listen for HTTPS requests on 443 and HTTP requests on 80.

If health monitoring is required, then the operator will need to match the listener's port with the member's and ensure that the real server is hosting the application on the same port.

### Hierarchical Multitenancy

Hierarchical Multitenancy (HMT) was added to Openstack as a QOL improvement for private clouds allowing operators to structure their projects in a way that emulates their own organizations design. Further information on HMT may be found here: https://specs.openstack.org/openstack/keystone-specs/specs/keystone/juno/hierarchical_multitenancy.html

#### Example
Corporation A has the Engineering department divided into Dev Team 1, Dev Team 2, and QA. Each team has it's own resource needs which are defined in openstack via qoutas. (Further information on nested qoutas may be found here: https://docs.openstack.org/ocata/config-reference/block-storage/nested-quota.html)

The requirements are as follows:

```
Dev Team 1: 3 load balancers
Dev Team 2: 3 load balancers
QA:         2 load balancers

Total Eng:  8 load balancers
```

#### Step 1: Create Corp A domain

```
openstack domain create --description "Corporation A Domain" corpA
```

Let's also create an admin user for the domain

```
openstack user create --domain corpA --password-prompt corp_admin
openstack role add --domain corpA --user corp_admin admin
```

#### Step 2: Create the Engineering Project

```
openstack project create --domain corpA --description "Engineering" engineering
```

```
openstack loadbalancer quota set --loadbalancer 8 engineering
```

#### Step 3: Create the Dev Group Project

```
openstack project create --domain corpA --description "Dev Management" --parent engineering dev_mgmt
```

```
openstack loadbalancer quota set --loadbalancer 6 dev_mgmt
```

#### Step 4: Create the Dev Team 1 Project

```
openstack project create --domain corpA --description "Dev Team 1" --parent dev_mgmt dev_team_1
```

```
openstack loadbalancer quota set --loadbalancer 3 dev_team_1
```

#### Step 5: Create the Dev Team 2 Project

```
openstack project create --domain corpA --description "Dev Team 2" --parent dev_mgmt dev_team_2
```

```
openstack loadbalancer quota set --loadbalancer 3 dev_team_2
```

#### Step 6: Create the QA Project

```
openstack project create --domain corpA --description "QA" --parent engineering qa
```

```
openstack loadbalancer quota set --loadbalancer 2 qa
```

#### Step 7: Update the a10-octavia.conf file

First we need to grab all of the project ids

```
$ openstack project list
+----------------------------------+--------------------+
| ID                               | Name               |
+----------------------------------+--------------------+
| cecabe921e02490d97840b96866caa29 | engineering        |
| f9efe94e11a04432a28a4b01997731e5 | dev_mgmt           |
| 6e8ab3d60e6248d09a97b76dda362397 | dev_team_1         |
| 9adffd6e4c554830a4bb48e259caf56f | dev_team_2         |
| 8c589595eb924356bcfb1416f7b35551 | qa                 |
+----------------------------------+--------------------+
```

Now modify the `a10-octavia.conf` file
```
[a10_controller_worker]
network_driver = a10_octavia_neutron_driver

[listener]
autosnat = True

[hardware_thunder]
devices = [
                    {
                     "project_id": "6e8ab3d60e6248d09a97b76dda362397",
                     "device_name": "device1",
                     "ip_address": "18.64.4.6",
                     "username": "myuser",
                     "password": "mypass",
                     "hierarchical_multitenancy": "enable"
                     },
                    {
                     "project_id": "9adffd6e4c554830a4bb48e259caf56f",
                     "device_name": "device1",
                     "ip_address": "18.64.4.6",
                     "username": "myuser",
                     "password": "mypass",
                     "hierarchical_multitenancy": "enable"
                     },
                    {
                     "project_id": "8c589595eb924356bcfb1416f7b35551",
                     "device_name": "device1",
                     "ip_address": "18.64.4.6",
                     "username": "myuser",
                     "password": "mypass",
                     "hierarchical_multitenancy": "enable"
                     }
             ]
```

When using hierarchical multitenancy (HMT), partitions will be created on the Thunder device with names matching the first 14 characters of the `project_id`. It's important to note that any `partition_name` defined for projects without pre-existing loadbalancers will be ignored.

Now issue the following commands to create each loadbalancer
```
openstack loadbalancer create --vip-subnet-id public_subnet --name dev_1_vip --project dev_team_1
openstack loadbalancer create --vip-subnet-id public_subnet --name dev_2_vip --project dev_team_2
openstack loadbalancer create --vip-subnet-id public_subnet --name qa_vip --project qa
```

#### Check the Thunder

List the partitions
```
Total Number of active partitions: 3
Partition Name   Id     L3V/SP     Parent L3V           App Type   Admin Count
------------------------------------------------------------------------------
6e8ab3d60e6248   1       L3V       -                    -            0    
9adffd6e4c5548   2       L3V       -                    -            0    
8c589595eb9243   3       L3V       -                    -            0    
```

The running configurations of each partition
```
!
active-partition 6e8ab3d60e6248
!
!
!
slb virtual-server 0a0d7627-df95-433e-a3b5-d0e1f94caf6b 18.64.10.101
```

```
!
active-partition 9adffd6e4c5548
!
!
!
slb virtual-server 3d0cb11e-039c-4a19-aa01-2f123d73a0bd 18.64.10.34
```

```
!
active-partition 8c589595eb9243
!
!
!
slb virtual-server ecbda83d-1598-4c51-9fed-9c01f755eaf3 18.64.10.27
```

#### Using Parent Partitions

<Insert Graphic Here>

Ocassionally, operators may want to create the slb objects of one project in the L3V partition of its parent project. Generally speaking, this is due to resource limitations though it can be used to share non-slb configurations between two projects.

Continuing from the above example, let's recreate both loadbalancers from the `dev_team` projects inside of the `dev_mgmt` project's L3V partition.

#### Step 1: Delete pre-existing 
```
openstack loadbalancer delete dev_1_vip
openstack loadbalancer delete dev_2_vip
```

#### Step 2: Edit `a10-octavia.conf`

```
[a10_global]
use_parent_partition=True

[a10_controller_worker]
network_driver = a10_octavia_neutron_driver

[listener]
autosnat = True

[hardware_thunder]
devices = [
                    {
                     "project_id": "6e8ab3d60e6248d09a97b76dda362397",
                     "device_name": "device1",
                     "ip_address": "18.64.4.6",
                     "username": "myuser",
                     "password": "mypass",
                     "hierarchical_multitenancy": "enable"
                     },
                     {
                     "project_id": "9adffd6e4c554830a4bb48e259caf56f",
                     "device_name": "device1",
                     "ip_address": "18.64.4.6",
                     "username": "myuser",
                     "password": "mypass",
                     "hierarchical_multitenancy": "enable"
                     }
             ]
```

#### Step 3: Recreate the loadbalancers
*Note: Loadbalancers created under `use_parent_partition` reside in the child projects; however, their virtual server counterparts reside in the parent partitions on the Thunder device.*

```
openstack loadbalancer create --vip-subnet-id public_subnet --name dev_1_vip --project dev_team_1
```

```
+---------------------+--------------------------------------+
| Field               | Value                                |
+---------------------+--------------------------------------+
| admin_state_up      | True                                 |
| created_at          | 2020-08-30T08:34:18                  |
| description         |                                      |
| flavor_id           | None                                 |
| id                  | 0c1d7623-1590-6b21-78ec-5e456d73ea2d |
| listeners           |                                      |
| name                | lb1                                  |
| operating_status    | OFFLINE                              |
| pools               |                                      |
| project_id          | 3330d7ff659841a2a685b18af0f7a099     |
| provider            | a10                                  |
| provisioning_status | PENDING_CREATE                       |
| updated_at          | None                                 |
| vip_address         | 18.64.10.13                          |
| vip_network_id      | ae50079f-4694-4da7-942c-168542da5def |
| vip_port_id         | 4d923736-3683-476d-8cf1-66592bd39d83 |
| vip_qos_policy_id   | None                                 |
| vip_subnet_id       | d9edc710-b995-4554-9412-218d989d952d |
+---------------------+--------------------------------------+
```

```
openstack loadbalancer create --vip-subnet-id public_subnet --name dev_2_vip --project dev_team_2
```

```
+---------------------+--------------------------------------+
| Field               | Value                                |
+---------------------+--------------------------------------+
| admin_state_up      | True                                 |
| created_at          | 2020-08-30T08:34:22                  |
| description         |                                      |
| flavor_id           | None                                 |
| id                  | fcbda83d-1098-4cb1-8acd-9c21ef633eed |
| listeners           |                                      |
| name                | lb1                                  |
| operating_status    | OFFLINE                              |
| pools               |                                      |
| project_id          | 3330d7ff659841a2a685b18af0f7a099     |
| provider            | a10                                  |
| provisioning_status | PENDING_CREATE                       |
| updated_at          | None                                 |
| vip_address         | 18.64.10.109                         |
| vip_network_id      | ae50079f-4694-4da7-942c-168542da5def |
| vip_port_id         | 4d923736-3683-476d-8cf1-66592bd39d83 |
| vip_qos_policy_id   | None                                 |
| vip_subnet_id       | d9edc710-b995-4554-9412-218d989d952d |
+---------------------+--------------------------------------+
```

#### Check the Thunder device
```
!
active-partition f9efe94e11a044
!
!
!
slb virtual-server 0c1d7623-1590-6b21-78ec-5e456d73a2d 18.64.10.13
!
slb virtual-server fcbda83d-1098-4cb1-8acd-9c21f633ead 18.64.10.109
!
```

Note that the partition name is the first 14 characters of the parent project's id.

***

### Octavia Flavor Support
***In this section we just brief this feature. Please reference Octavia Flavor Support document for more information: https://github.com/a10networks/a10-octavia/blob/master/a10_octavia/doc/octavia_flavor_support.md***

#### Feature Overview

* Use octavia flavor/flavorprofile to specify options for slb objects.
* Flavors can be shared between loadblancers.
* Uses regex expressions to match object names, if match occurs then the provided setting is applied.
* SNAT pool flavors are supported to allocate NAT pool on ACOS device.
* ACOS aXAPI attributes can be spcified as options for slb objects and nat pools.
* Doesn't require restart service for change loadbalancer options.
* example commands:
```shell
$ openstack loadbalancer flavorprofile create --name fp1 --provider a10 --flavor-data '{"virtual-server": {"vport-disable-action":"drop-packet"}}'
$ openstack loadbalancer flavor create --name f1 --flavorprofile fp1 --description "vtest" --enable
$ openstack loadbalancer create --flavor f1 --vip-subnet-id f25ce642-f953-4058-8c46-98fdd72fb129 --vip-address 192.168.91.56 --name vip1
```

#### ACOS aXAPI
The aXAPI version 3.0 offers an HTTP interface that can be used to configure and monitor your ACOS device.
And for flaovr support feature, **a10-octavia allow user to specify aXAPI attributes in flavor options** to configure ACOS device objects.

For more information for aXAPI and **aXAPI attributes for slb objects**, please find aXAPI v3.0 document for more information:
 - aXAPI v30 document for ACOS 4.1.4-GR1-P5: https://documentation.a10networks.com/ACOS/414x/ACOS_4_1_4-GR1-P5/html/axapiv3/index.html
 - aXAPI v30 document for ACOS 5.2.1: http://acos.docs.a10networks.com/axapi/521/index.html

Please reference below example for how aXAPI attributes apply to flavor options.

#### Flavor example

Use virtual-server flavor as example:
```
{
	"virtual-server": {
		"arp-disable":1,
		"name-expressions": [
			{
				"regex": "vip1", "json": {"user-tag": "vip1"}
			},
			{
				"regex": "vip2", "json": {"user-tag": "vip2"}
			}
		]
	}
}
```
 - aXAPI attributes can be used as options to configure loadbalancers. (where **"arp-disable"** and **"user-tag"** are **aXAPI attributes** for ACOS)
 - Global options are specified under "virtual-server". (in this example is **"arp-disable": 1**)
 - Allow use regex expression to match specific object name and apply specific options to this object. 
    - User can specify matching list in **"name-expressions"**, and use **"regex"** to specify object name regex you want match.
      And then use **"json"** to specify options for matched objects.
	- Any **slb object name** that **contains** the string in **"regex"** will match this name expression.
	  And options in this name expression will apply to this slb object.
    - In this example, loadbalancer **vip1** will configure **user-tag** as **vip1**.
      loadbalancer **vip2** will configure **user-tag** as **vip2**.

***

### SLB Configuration Options

These settings are added to the `a10-octavia.conf` file. They allow the operator to configure options not exposed by the Openstack CLI.

*WARNING: Any option specified here will apply globally meaning all projects and devices*

#### Global section config example
```shell
[a10_global]
vrid = 0
use_parent_partition = False
```

Options set in the global section will apply to every project under the `hardware_thunder` configuration section

#### housekeeper config example
```shell
[a10_house_keeping]
use_periodic_write_memory = 'enable'
write_mem_interval = 3600
```
Enable periodic write memory with interval 3600 seconds. (So, write memroy will not perform for every openstack commands. And will be maintained by housekeeper

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

#### Health Monitor config example
```shell
[health_monitor]
post_data = "abc=1"
```
- post_data: Specify HTTP/HTTPS POST payload that Thunder health monitor will send to server.

Full list of options can be found here: [Config Options Module](https://github.com/a10networks/a10-octavia/blob/master/a10_octavia/common/config_options.py)

## Troubleshooting
You may check logs of the services using `journalctl` commands. For example:

```shell
$ journalctl -af --unit a10-controller-worker.service
$ journalctl -af --unit a10-health-manager.service
$ journalctl -af --unit a10-house-keeper.service
```

### Pending States

#### Pending Create
```
+--------------------------------------+-----------+----------------------------------+-------------+---------------------+----------+
| id                                   | name      | project_id                       | vip_address | provisioning_status | provider |
+--------------------------------------+-----------+----------------------------------+-------------+---------------------+----------+
| a76b101b-351b-4e7c-a519-5975eb430e88 | dev_1_vip | 0e567ea4ea824228b06fce04805c8c16 | 10.0.11.165 | PENDING_CREATE      | a10      |
+--------------------------------------+-----------+----------------------------------+-------------+---------------------+----------+
```


When a resource is created, it will first enter a `PENDING_CREATE` provisioning status. This is expected behavior though it should quickly enter the `ACTIVE` state.

If it becomes stuck in pending create, then be sure to check the journal logs with the following command `journalctl -af --unit a10-controller-worker.service`. It is likely that the `a10-octavia.conf` file has been misconfigured. Once the issue has been resolved, restart the `a10-controller-worker` service and wait for the object to be created.

#### Pending Update and Pending Delete

```
+--------------------------------------+-----------+----------------------------------+-------------+---------------------+----------+
| id                                   | name      | project_id                       | vip_address | provisioning_status | provider |
+--------------------------------------+-----------+----------------------------------+-------------+---------------------+----------+
| a76b101b-351b-4e7c-a519-5975eb430e88 | dev_1_vip | 0e567ea4ea824228b06fce04805c8c16 | 10.0.11.165 | PENDING_UPDATE      | a10      |
+--------------------------------------+-----------+----------------------------------+-------------+---------------------+----------+
```

Resources can become stuck duing update and delete calls for a number of reasons (http connection timeouts, misconfigurations, etc). Once stuck, the only road to recovery is to delete the offending resources and set the connected resources back to `ACTIVE` state via the database.

##### Scenario 1: Resource exists on the device

If the resources exists on the device already, then access the database and set `provisioning_status` back to `ACTIVE` with the following commands.

```
$ mysql
> use octavia;
> UPDATE load_balancer SET provisioning_status = "ACTIVE" WHERE id = "a76b101b-351b-4e7c-a519-5975eb430e88";
```

This effectively cancels the update or delete operation.

*Note: If the resources is a member, then all the parent resources (pool, listener, loadbalancer) will also need to be set back to `ACTIVE`*

##### Scenario 2: Resource does not exists on the device, but does in Openstack

If the resources has been removed from the device, but has not been removed from the Octavia database execute the following commands.

```
$ mysql
> use octavia;
> DELETE FROM vip WHERE load_balancer_id = "a76b101b-351b-4e7c-a519-5975eb430e88";
> DELETE FROM load_balancer WHERE id = "a76b101b-351b-4e7c-a519-5975eb430e88";
```

## Issues and Inquiries
For all issues, please send an email to support@a10networks.com 

For general inquiries, please send an email to opensource@a10networks.com
