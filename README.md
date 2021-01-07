# A10 Networks OpenStack Octavia Driver

## Table of Contents
1. [Overview](#Overview)

2. [System Requirements](#System-Requirements)

3. [Setup and Configuration](#Setup-And-Configuration)

    1. [For use with vThunders](#3a-for-use-with-vthunders)

    2. [For use with hardware devices](#3b-for-use-with-hardware-devices)

4. [Setting Object Defaults](#Setting-Object-Defaults)

5. [Troubleshooting](#Troubleshooting)

6. [Contributing](#Contributing)

7. [Issues and Inquiries](#Issues-and-Inquiries)

## Overview

**This solution is currently in beta stage with limited support**

The A10 Networks Octavia Driver allows for configuration of Thunder, vThunder, and AX Series Appliances deployed in
an Openstack enviroment. While the default Octavia provider leverages an "Amphora per VIP" architecture,
this provider driver uses a "Thunder per Tenant" architecture. Therefore, each tenant may only be serviced by a single
**active** Thunder device.

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
* Openstack (Nova, Neutron, Etc): Stein Release

ACOS Device Requirements
* ACOS version: ACOS 4.1.4 GR1 P2
* AXAPI version: 3.0

## Installation

This guide assumes that Openstack has already been deployed and Octavia has already been configured.

*Note: The following configurations should be done as an Openstack admin user*

### Install from PyPi

```shell
$ pip install a10-octavia
```

## Setup And Configuration

### 1. Enable A10 provider driver in Octavia config file
Add the following to `/etc/octavia/octavia.conf` under the `api-settings` section

```shell
enabled_provider_drivers = a10: 'The A10 Octavia driver.'

default_provider_driver = a10
```

### 2. Restart Openstack Octavia services
Use `systemctl` or similar a command to restart the Octavia API service. 

### 3a. For use with vThunders

#### 3aa. Upload vThunder image and create a nova flavor for amphorae devices

Upload a vThunder image (QCOW2) and create a nova flavor with the required resources.

Recommended vThunder flavor settings:
* 8 vCPUs
* 8GB RAM
* 30GB disk

```shell
$ openstack image create --disk-format qcow2 --container-format bare --public --file vThunder414.qcow2 vThunder.qcow2
$ openstack flavor create --vcpu 8 --ram 8192 --disk 30 vThunder_flavor
```

Note down the `image ID` and `flavor ID` of created resources.

*Please contact support@a10networks.com for questions on acquiring and licensing vThunder images*

#### 3ab. Create the a10-octavia.conf file
```shell
$ mkdir /etc/a10
$ touch /etc/a10/a10-octavia.conf
```

*Note: Make sure the user running the Octavia service has access to these files* 

#### 3ac. Sample a10-octavia.conf for vThunders
```shell
[vthunder]
default_vthunder_username = "admin"
default_vthunder_password = "a10"
default_axapi_version = "30"

[a10_controller_worker]
amp_image_owner_id = <admin_project_id>
amp_secgroup_list = <security_group_to_apply>
amp_flavor_id = <vthunder_flavor_id>
amp_boot_network_list = <netword_id_to_boot_vthunder_in_admin_project>
amp_ssh_key_name = <ssh_key_for_amphorae>
network_driver = a10_octavia_neutron_driver
workers = 2
amp_active_retries = 100
amp_active_wait_sec = 2
amp_image_id = <vthunder_image_id>
loadbalancer_topology = <SINGLE or ACTIVE_STANDBY>

[a10_health_manager]
udp_server_ip_address = <server_ip_address_for_health_monitor>
bind_port = 5550
bind_ip = <controller_ip_configured_to_listen_for_udp_health_packets>
heartbeat_interval = 5
heartbeat_key = insecure
heartbeat_timeout = 90
health_check_interval = 3
failover_timeout = 600
health_check_timeout = 3
health_check_max_retries = 5

[a10_house_keeping]
load_balancer_expiry_age = 3600
amphorae_expiry_age = 3600
```

Full list of options can be found here: [Config Options Module](https://github.com/a10networks/a10-octavia/blob/master/a10_octavia/common/config_options.py)

#### 3ad. Update security group to access vThunder AXAPIs

These settings are for ports allocated on the managment network. It's up to the operator to define the data network security rules.

When delopying with the STANDALONE loadbalancer topology

| Protocol   | Port  | Ingress    | Egress  | Purpose                                   |
|:----------:|:-----:|:----------:|:-------:|:-----------------------------------------:|
| TCP        | 80    | ✓          | ✓       | Communication with AXAPI                  |
| TCP        | 443   | ✓          | ✓       | Communication with AXAPI                  |
| UDP        | 5550  |            | ✓       | Communication with Health Manager Service |

When deploying with the ACTIVE-STANDBY loadbalancer topology

| Protocol   | Port   | Ingress    | Egress  | Purpose                                           |
|:----------:|:------:|:----------:|:-------:|:-------------------------------------------------:|
| TCP        | 80     | ✓          | ✓       | Communication with AXAPI                          |
| TCP        | 443    | ✓          | ✓       | Communication with AXAPI                          |
| UDP        | ALL    | ✓          | ✓       | For specifics contact support@a10networks.com     |


### 3b. For use with hardware devices

#### 3ba. Create the a10-octavia.conf file
```shell
$ mkdir /etc/a10
$ touch a10-octavia.conf
```

#### 3bb. Sample a10-octavia.conf for hardware devices

```shell
[a10_controller_worker]
amp_secgroup_list = <security_group_to_apply> 
amp_boot_network_list = <netword_id_to_boot_amphorae_in_admin_project>
amp_ssh_key_name = <ssh_key_for_amphorae>
network_driver = a10_octavia_neutron_driver
workers = 2
amp_active_retries = 100
amp_active_wait_sec = 2
loadbalancer_topology = SINGLE

[hardware_thunder]
devices = [
                    {
                     "project_id":"<project_id>",
                     "ip_address":"10.0.0.4",
                     "username":"<username>",
                     "password":"<password>",
                     "device_name":"<device_name>"
                     },
                     {
                     "project_id":"<another_project_id>",
                     "ip_address":"10.0.0.5",
                     "username":"<username>",
                     "password":"<password>",
                     "device_name":"<device_name>",
                     "partition_name" : "<partition_name>"
                     }
             ]
```

### 3c. Configuring High Availability for VThunders

<pre>
[a10_controller_worker]
amp_secgroup_list = &lt;security_group_to_apply&gt;
amp_boot_network_list = &lt;netword_id_to_boot_amphorae_in_admin_project&gt;
amp_ssh_key_name = &lt;ssh_key_for_amphorae&gt;
network_driver = a10_octavia_neutron_driver
workers = 2
amp_active_retries = 100
amp_active_wait_sec = 2
<b>loadbalancer_topology = ACTIVE_STANDBY</b>
</pre>

To enable HA deployment, when using vThunders, the `loadbalancer_topology` setting must be set to `ACTIVE_STANDBY`. In this deployment mode, two vThunders are created per tenant. The configurations will be synced between the vThunders.

### 3d. Configuring High Availability for hardware devices

It is expected for an operator to configure two hardware devices in a VRRPA set and an aVCS cluster. The IP address provided in the `[hardware_thunder]` configuration group must be the floating IP of the aVCS cluster. As the operator will configure VRRPA and aVCS out of band, it is not possible for openstack to verify that the provided IP address is for an aVCS cluster or a single device. For this reason, the `loadbalancer_topology` configuration setting is ignored by hardware devices.

<pre>
[a10_controller_worker]
network_driver = a10_octavia_neutron_driver
loadbalancer_topology = ACTIVE_STANDBY

[hardware_thunder]
devices = [
                    {
                     "project_id":"&lt;project_id&gt;",
                     "ip_address":"10.0.0.4",
                     "username":"&lt;username&gt;",
                     "password":"&lt;password&gt;",
                     "device_name":"&lt;device_name&gt;"
                     },
                     {
                     "project_id":"&lt;another_project_id&gt;",
                     "ip_address":"10.0.0.5",
                     "username":"&lt;username&gt;",
                     "password":"&lt;password&gt;",
                     "device_name":"&lt;device_name&gt;",
                     "partition_name" : "&lt;partition_name&gt;"
                     }
             ]
</pre>


To support VRRPA floating IP config for hardware devices, `vrid_floating_ip` setting can be included along with above config at global or local level.
The valid values for `vrid_floating_ip` can be set as `dhcp`, partial IP octets such as '45', '.45', '0.0.45' or a full IPv4 address.

##### How the VRID floating IP is allocated ?

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
 
=======
#### 3bc. Configuring VLAN and Virtual Ethernet for hardware devices

In the VLAN Network setup, for configuring the VLAN and Virtual Ethernet(VE) interfaces in the hardware thunder device, `network_type` setting in `[a10_global]` configuration section should be set to "vlan" string. VLAN and VE configuration for the ethernet interfaces or trunk interfaces should be specified in `interface_vlan_map` setting in the `[hardware_thunder]` device configuration section. The `interface_vlan_map` setting is a json map. For a single device it can have key "device_1" with data or two keys "device_1" and "device_2" for aVCS cluster device. While configuring aVCS cluster, VCS floating IP must be provided in `ip_address` field and respective management IP for both devices in `mgmt_ip_address` fields. The `vcs_device_id` value must be provided as either 1 or 2 based on current aVCS cluster status.

##### 3bca. Sample a10-octavia.conf for VLAN and VE settings

<pre>

[a10_global]
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

##### 3bcb. Configuring VLAN and VE for Ethernet Interfaces

With each device the ethernet interfaces settings can be specified as an array within the key "ethernet_interfaces". Each interface information contains a key "interface_num" indicating the ethernet interface number on which the "vlan_map" config will be applied. The key "vlan_map" contains an array with VLANs informations corresponding to the interface_num. The VLAN information contains "vlan_id" and the VE information. The VE information consists of either partial or complete "ve_ip" or a flag "use_dhcp" set to "True".

##### 3bcc. Configuring VLAN and VE for Trunk Interfaces

In order to configure VLAN and VE on trunk interfaces, the hardware thunder should have the trunk-group configurations set on the corresponding ethernet interfaces. Also system promiscuous-mode should be enabled on the hardware thunder, before applying the VLAN and VE on trunk interfaces. The "trunk_interfaces" configuration is similar to "ethernet_interfaces" configuration. Only difference being the "interface_num" within "trunk_interfaces" configuration specifies the trunk-group number on which the VLAN and VE needs to be configured.

Full list of options can be found here: [Config Options Module](https://github.com/a10networks/a10-octavia/blob/master/a10_octavia/common/config_options.py)

*Note: trailing "," are invalid in device config type*


### 4. Run database migrations

From the `/path/to/a10-octavia/a10_octavia/db/migration` folder run 

```shell
$ alembic upgrade head
```

If versioning error occurs, delete all entries in the `alembic_version` table from `octavia` database and re-run the above command.

```shell
mysql> use octavia;
mysql> DELETE FROM alembic_version;
```

*Note: Octavia verisons less than 4.1.1 have the `alembic_migrations` table instead*


### 5. Register and start a10-octavia services

With `a10-octavia` installed, run the following command to register the services

```shell
$ install-a10-octavia
```

This will install systemd services with names - `a10-controller-worker.service`, `a10-health-manager.service` and `a10-house-keeper.service`.

#### 5a. Make sure the services are up and running.

```shell
$ systemctl status a10-controller-worker.service a10-health-manager.service a10-house-keeper.service
```

You can start/stop the services using systemctl/service commands.


## Setting Object Defaults

These settings are added to the `a10-octavia.conf` file. They allow the operator to configure options not exposed by the Openstack CLI.

*WARNING: Any option specified here will apply globally meaning all projects and devices*

#### Global section config example
```shell
[a10_global]
network_type = vlan
use_parent_partition = True

[NOTE: Use this flag for allowing templates to be used from shared partition for attaching them to components in l3v partition]
use_shared_for_template_lookup = True
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

## Contributing

### 1. Fork the a10-octavia repository

[How To Fork](https://help.github.com/en/github/getting-started-with-github/fork-a-repo)

### 2. Clone the repo from your fork

```shell
$ git clone git@github.com:<username>/a10-octavia.git
```

### 3. Run octavia install script 
**WARNING: THIS INSTALLS DEVSTACK. RUN IN A VM**

Run the following as the super user

```shell
$ sudo ./path/to/a10-octavia/a10_octavia/contrib/devstack/new-octavia-devstack.sh
```

### 4. Become the stack user and move the a10-octavia repo

```shell
$ sudo su - stack
$ mv /path/to/a10-octavia .
$ sudo chown -R stack:stack a10-octavia
```

### 5. Checkout to a new branch

```shell
$ git checkout -b feature/<branch_name>
```

### 6. Install in edit mode

```shell
$ pip install -e a10-octavia
```
### 7. Enable A10 provider driver in Octavia config file
Add the following to `/etc/octavia/octavia.conf` under the `api-settings` section

```shell
enabled_provider_drivers = a10: 'The A10 Octavia driver.'

default_provider_driver = a10
```

### 8. Restart the Octavia API service
```shell
$ sudo systemctl restart devstack@o-api.service
```

### 9. Create a10-octavia.conf and update with desired configuration
```shell
$ sudo mkdir /etc/a10
$ sudo chown -R stack:stack /etc/a10
$ touch /etc/a10/a10-octavia.conf
$ <vi/vim/nano/emacs> a10-octavia.conf
```

### 10. Run database migrations

From the `/path/to/a10-octavia/a10_octavia/db/migration` folder run

```shell
$ alembic upgrade head
```

If versioning error occurs, delete all entries in the `alembic_version` table from `octavia` database and re-run the above command.

```shell
mysql> use octavia;
mysql> DELETE FROM alembic_version;
```

*Note: Octavia verisons less than 4.1.1 have the `alembic_migrations` table instead*


### 11. Register and start a10-octavia services

With `a10-octavia` installed, run the following command to register the services

```shell
$ /path/to/a10-octavia/a10_octavia/install/install-a10-octavia-dev
```

This will install systemd services with names - `a10-controller-worker.service`, `a10-health-manager.service` and `a10-house-keeper.service`.

### 12. Make sure the services are up and running.

```shell
$ systemctl status a10-controller-worker.service a10-health-manager.service a10-house-keeper.service
```

You can start/stop the services using systemctl/service commands.


### 13 (Optional). If working with vThunder amphora, update security groups

Modify the `lb-mgmt-sec-grp` to include

| Protocol   | Port   | Ingress    | Egress  | Purpose                                           |
|:----------:|:------:|:----------:|:-------:|:-------------------------------------------------:|
| TCP        | 80     | ✓          | ✓       | Communication with AXAPI                          |
| TCP        | 443    | ✓          | ✓       | Communication with AXAPI                          |
| UDP        | ALL    | ✓          | ✓       | For specifics contact support@a10networks.com     | 

Modify the `lb-health-mgr-sec-grp` to include

| Protocol   | Port  | Ingress    | Egress  | Purpose                                   |
|:----------:|:-----:|:----------:|:-------:|:-----------------------------------------:|
| UDP        | 5550  |            | ✓       | Communication with Health Manager Service |


### 14. You may check logs of the services using `journalctl` commands. For example:

```shell
$ journalctl -af --unit a10-controller-worker.service
$ journalctl -af --unit a10-health-manager.service
$ journalctl -af --unit a10-house-keeper.service
```

#### Testing install script changes
When testing changes to the `install-a10-octavia` script, run `python setup.py install` from within the `a10-octavia` dir to re-install the script.

## Issues and Inquiries
For all issues, please send an email to support@a10networks.com 

For general inquiries, please send an email to opensource@a10networks.com
