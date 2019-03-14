# A10 Networks Openstack Octavia Driver
===========================================

A10 Networks Octavia Driver for Thunder, vThunder and AX Series Appliances 
Supported releases:

* OpenStack: Rocky Releases
* Octavie versions: v2
* ACOS versions: ACOS 2/AxAPI 2.1 (ACOS 2.7.2+), ACOS 4/AxAPI 3.0 (ACOS 4.0.1-GA +)

## Installation

### Register the A10 driver and plugin
`sudo python ./setup.py develop`

### Update the Octavia config file
Update the /etc/octavia/octavia.conf file with the following parameters:

```shell
octavia_plugins = a10_hot_plug_plugin

enabled_provider_drivers = a10:     'The A10 Octavia driver.',
                           noop_driver: 'The no-op driver.',
                           amphora: 'The Octavia Amphora driver.',
                           octavia: 'Deprecated alias of the Octavia Amphora driver.'

default_provider_driver = a10
```

### Restart Related Octavia Services

`sudo systemctl restart devstack@o-api.service devstack@o-cw.service devstack@o-hk.service devstack@o-hm.service devstack@q-svc.service`

