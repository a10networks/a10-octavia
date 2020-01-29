# A10 Networks Openstack Octavia Driver
===========================================

**This is currently in beta stage with limited support. Our next dev release is tentative for early 2020**

A10 Networks Octavia Driver for Thunder, vThunder and AX Series Appliances 
Supported releases:

* OpenStack: Rocky Releases
* Octavie versions: v2
* ACOS versions: ACOS 2/AxAPI 2.1 (ACOS 2.7.2+), ACOS 4/AxAPI 3.0 (ACOS 4.0.1-GA +)

## STEP1: Installation

Clone the repository and run the following command to install

### Register the A10 driver and plugin
`sudo python ./setup.py install`

Clone the acos client and install it from https://github.com/a10networks/acos-client

### Register acos clint by running following command in acos-client folder

`sudo python ./setup.py install`

## STEP2: Upload vThunder image and create vThunder flavor

Upload provided vThunder image in QCOW2 and create OpenStack flavor with minimum 8 vcpus, 8GB RAM and 30GB disk as admin user of OpenStack environment.

Use below commands for reference:

```shell
openstack image create --disk-format qcow2 --container-format bare   --public --file vThunder410.qcow2 vThunder.qcow2

openstack flavor create --vcpu 8 --ram 8196 --disk 30 vThunder_flavor
```

Note down the `image ID` and `flavor ID` of created resources.

## STEP3: Update the Octavia config file

Update the /etc/octavia/octavia.conf file with the following parameters:

```shell
enabled_provider_drivers = a10:     'The A10 Octavia driver.',
                           noop_driver: 'The no-op driver.',
                           amphora: 'The Octavia Amphora driver.',
                           octavia: 'Deprecated alias of the Octavia Amphora driver.'

default_provider_driver = a10
```

## STEP4: Add an Octavia config file 
Create an `a10-octavia.conf` file at /etc/a10/ location with following paramaters:

```shell

[VTHUNDER]
DEFAULT_VTHUNDER_USERNAME = "admin"
DEFAULT_VTHUNDER_PASSWORD = "a10"
DEFAULT_AXAPI_VERSION = "30"
```

```shell
[a10_controller_worker]
amp_image_owner_id = <admin_project_id>
amp_secgroup_list = lb-mgmt-sec-grp <or_you_can_create_custom>
amp_flavor_id = <flavor_id_for_amphora>
amp_boot_network_list = <netword_id_for_amphora_in_admin_project>
amp_ssh_key_name = <ssh_key_for_amphora>
network_driver = allowed_address_pairs_driver
compute_driver = compute_nova_driver
amphora_driver = amphora_haproxy_rest_driver
workers = 2
amp_active_retries = 100
amp_active_wait_sec = 2
amp_image_id = <vthunder_amphora_image_id>
amp_image_tag = amphora
user_data_config_drive = False
```

## STEP5: Run database migrations

from `a10-octavia/a10_octavia/db/migration` folder run 

```shell
alembic upgrade head
```

if older migrations not found, trucate `alembic_migrations` table from ocatvia database and re-run the above command.

## STEP6: Allow security group to access vThunder AXAPIs port

As `admin` OpenStack user, update security group `lb-mgmt-sec-grp` (security group of which ID is provided in octavia.conf) and allow `PORT 80` and `PORT 443` ingress traffic to allow AXAPI communication with vThunder instances.

## STEP7: Restart Related Octavia Services
### devstack development environment
`sudo systemctl restart devstack@o-api.service devstack@o-cw.service devstack@o-hk.service devstack@o-hm.service devstack@q-svc.service`

## other environments
Use `systemctl` or similar function to restart Octavia controller and health services. 

## STEP 8: [FOR ROCKY AND STEIN RELEASE] Create octavia service worker
From a10-octavia/a10_octavia/install folder run `install_service.sh` file.
```shell
chmod +X install_service.sh
./install_service.sh
```
This will install systemd service with name - 'a10-controller-worker'. Make sure service is up and running.
You can start/stop service using systemctl/service commands.
You can check logs of service using following command:
```shell
journalctl -af --unit a10-controller-worker.service
```
