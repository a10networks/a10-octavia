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
$ openstack flavor create --vcpu 8 --ram 8196 --disk 30 vThunder_flavor
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
[VTHUNDER]
DEFAULT_VTHUNDER_USERNAME = "admin"
DEFAULT_VTHUNDER_PASSWORD = "a10"
DEFAULT_AXAPI_VERSION = "30"

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

[RACK_VTHUNDER]
devices = """[
                    {
                     "project_id":"<project_id>",
                     "ip_address":"10.0.0.4",
                     "undercloud":"True",
                     "username":"<username>",
                     "password":"<password>",
                     "device_name":"<device_name>",
                     "axapi_version":"30"
                     },
                     {
                     "project_id":"<another_project_id>",
                     "ip_address":"10.0.0.5",
                     "undercloud":"True",
                     "username":"<username>",
                     "password":"<password>",
                     "device_name":"<device_name>",
                     "axapi_version":"30",
                     }
             ]
       """
```

Full list of options can be found here: [Config Options Module](https://github.com/a10networks/a10-octavia/blob/master/a10_octavia/common/config_options.py)

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

This will install systemd services with names - `a10-controller-worker.service`, `a10-health-manager.service` and `a10-housekeeper-manager.service`.

#### 5a. Make sure the services are up and running.

```shell
$ systemctl status a10-controller-worker.service a10-health-manager.service a10-housekeeper-manager.service
```

You can start/stop the services using systemctl/service commands.


## Setting Object Defaults

These settings are added to the `a10-octavia.conf` file. They allow the operator to configure options not exposed by the Openstack CLI.

*WARNING: Any option specified here will apply globally meaning all projects and devices*

#### Loadbalancer/virtual server config example
```shell
[SLB]
arp_disable = False
default_virtual_server_vrid = "10"
logging_template = "Logging_temp1"
policy_template = "policy_temp1"
template_virtual_server = "virtual_server_template1"
default_virtual_server_vrid = 0
```

#### Listener/virtual port config example
```shell
[LISTENER]
ipinip = False
no_dest_nat = False
ha_conn_mirror = False
template_virtual_port = "vport_template"
template_tcp = "tcp_template"
template_policy = "policy_temp1"
autosnat = True
conn_limit = 5000
template_http = "http_template"
```

#### Pool/service group config example
```shell
[SERVICE - GROUP]
templates = "server1"
```

#### Member config example
```shell
[SERVER]
conn_limit = 5000
conn_resume = 1
templates = "server1"
```

Full list of options can be found here: [Config Options Module](https://github.com/a10networks/a10-octavia/blob/master/a10_octavia/common/config_options.py)

## Troubleshooting
You may check logs of the services using `journalctl` commands. For example:

```shell
$ journalctl -af --unit a10-controller-worker.service
$ journalctl -af --unit a10-health-manager.service
$ journalctl -af --unit a10-housekeeper-manager.service
```

## Contributing

### 1. Fork the a10-octavia repository

[How To Fork](https://help.github.com/en/github/getting-started-with-github/fork-a-repo)

### 2. Clone the repo from your fork

```shell
$ git clone https://git@github.com:<username>/a10-octavia.git
```

### 3. Checkout to a new branch

```shell
$ git checkout -b feature/<branch_name>
```

### 4. Run octavia install script 
**WARNING: THIS INSTALLS DEVSTACK. RUN IN A VM** 

Run the following as the super user

```shell
$ sudo ./path/to/a10-octavia/a10_octavia/contrib/devstack/new-octavia-devstack.sh
```

### 5. Become the stack user and move the a10-octavia repo

```shell
$ sudo su - stack
$ mv /path/to/a10-octavia .
$ sudo chown -R stack:stack a10-octavia
```

### 6. Install in edit mode

```shell
$ pip install -e a10-octavia
```

### 7. Restart the Octavia API service
`sudo systemctl restart devstack@o-api.service`

### 8. Update security groups 

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

### 9. Register and start the a10-octavia services 

```shell
$ install-a10-octavia
```

#### Testing install script changes
When testing changes to the `install-a10-octavia` script, run `python setup.py install` from within the `a10-octavia` dir to re-install the script.

## Issues and Inquiries
For all issues, please send an email to support@a10networks.com 

For general inquiries, please send an email to opensource@a10networks.com
