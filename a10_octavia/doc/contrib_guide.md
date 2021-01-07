# A10 Networks OpenStack Octavia Driver

## Table of Contents
1. [Overview](#Overview)

2. [System Requirements](#System-Requirements)

3. [Troubleshooting](#Troubleshooting)

4. [Contributing](#Contributing)

5. [Issues and Inquiries](#Issues-and-Inquiries)

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
