# A10 Networks OpenStack Octavia Driver
=====================================================

**This is currently in beta stage with limited support. Our next dev release is tentative for early 2020.**

A10 Networks Octavia Driver for Thunder, vThunder and AX Series Appliances 
supported releases:

* OpenStack: Stein Release
* Octavia version: 4.1.0
* ACOS versions: AxAPI 2.1 (ACOS 2.7.2+), ACOS 4/AxAPI 3.0 (ACOS 4.0.1-GA +)

**Note: Following Configurations should be done as an OpenStack admin user**

## STEP 1: Installation

Clone the repository and run the following command to install the plugin

#### Register the A10 provider driver and controller worker plugin
`sudo pip install -e .`

Clone the `acos-client` from https://github.com/a10networks/acos-client and checkout `feature/octavia-support` branch

#### Register `acos-client` by running following command in acos-client folder

`sudo pip install -e .`

## STEP 2: Upload vThunder image and create a nova flavor for amphorae devices

Upload a vThunder image (QCOW2) and create nova flavor with required resources.
Minimum recommendation for vThunder instance is 8 vCPUs, 8GB RAM and 30GB disk.

Use below commands for reference:

```shell
openstack image create --disk-format qcow2 --container-format bare --public --file vThunder410.qcow2 vThunder.qcow2

openstack flavor create --vcpu 8 --ram 8196 --disk 30 vThunder_flavor
```

Note down the `image ID` and `flavor ID` of created resources.

## STEP 3: Enable A10 provider driver in Octavia config file

Add `a10` driver to the `enabled_provider_drivers` list in the `api-settings` section of `/etc/octavia/octavia.conf`.
Change `default_provider_driver` to `a10`

```shell
enabled_provider_drivers = a10: 'The A10 Octavia driver.',

default_provider_driver = a10
```

## STEP 4: Add A10-Octavia config file
Create a `a10-octavia.conf` file at /etc/a10/ location with proper permissions including following configuration sections.

### vThunder sample config
```shell
[VTHUNDER]
DEFAULT_VTHUNDER_USERNAME = "admin"
DEFAULT_VTHUNDER_PASSWORD = "a10"
DEFAULT_AXAPI_VERSION = "30"
```

### Controller worker sample config
```shell
[a10_controller_worker]
amp_image_owner_id = <admin_project_id>
amp_secgroup_list = lb-mgmt-sec-grp <or_you_can_create_custom>
amp_flavor_id = <flavor_id_for_amphorae>
amp_boot_network_list = <netword_id_to_boot_amphorae_in_admin_project>
amp_ssh_key_name = <ssh_key_for_amphorae>
network_driver = a10_octavia_neutron_driver
workers = 2
amp_active_retries = 100
amp_active_wait_sec = 2
amp_image_id = <vthunder_amphorae_image_id>
loadbalancer_topology = SINGLE
```
Load balancer topology options are `SINGLE` and `ACTIVE_STANDBY`. In `ACTIVE_STANDBY` topology, the plugin boots 2 vThunders and uses aVCS to provide high availability.

### Health manager sample config
```shell
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
```

### Housekeeper sample config
```shell
[a10_house_keeping]
load_balancer_expiry_age = 3600
amphorae_expiry_age = 3600
```


## STEP 5: Run database migrations

from `a10-octavia/a10_octavia/db/migration` folder run 

```shell
alembic upgrade head
```

if older migrations not found, truncate `alembic_migrations` table from octavia database and re-run the above command.

## STEP 6: Update security group to access vThunder AXAPIs

Update security group `lb-mgmt-sec-grp` (or custom security group configured in a10-octavia.conf file) and allow `TCP PORT 80` and `TCP PORT 443` ingress traffic to allow AXAPI communication with vThunder instances. Also update security group `lb-health-mgr-sec-grp` to allow `UDP PORT 5550` ingress traffic to allow UDP packets from vThunder instances.

## STEP 7: Restart Related Octavia Services
#### For devstack development environment
`sudo systemctl restart devstack@o-api.service devstack@o-cw.service devstack@o-hk.service devstack@o-hm.service`

#### For other OpenStack environments
Use `systemctl` or similar function to restart Octavia controller and health services. 

## STEP 8: [FOR ROCKY AND STEIN RELEASE] Create a10-octavia services
From a10-octavia/a10_octavia/install folder run `install_service.sh` script.

```shell
chmod +X install_service.sh
./install_service.sh
```
This will install systemd services with names - `a10-controller-worker`, `a10-health-manager.service` and `a10-housekeeper-manager.service`. Make sure the services are up and running.
You can start/stop the services using systemctl/service commands.
You may check logs of the services using `journalctl` commands. For example:
```shell
journalctl -af --unit a10-controller-worker.service
journalctl -af --unit a10-health-manager.service
journalctl -af --unit a10-housekeeper-manager.service
```
