# A10 Networks OpenStack Octavia Driver - Flavor Support
***
## Table of Contents
1. [Overview](#Overview)
2. [Requirements](#Requirements)
3. [Flavors](#Flavors) 
    * 3-1 [Flavor Support](#3-1-Flavor-Support)
    * 3-2 [virtual-server](#3-2-virtual-server)
    * 3-3 [virtual-port](#3-3-virtual-port)
    * 3-4 [service-group](#3-4-service-group)
    * 3-5 [server](#3-5-server)
    * 3-6 [health-monitor](#3-6-health-monitor)
    * 3-7 [nat-pool](#3-7-nat-pool)
    * 3-8 [nat-pool-list](#3-8-nat-pool-list)
4. [Limitations](#Limitations)


***

## Overview

#### 1-1 Feature Overview
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

#### 1-2 Behavior
##### Flavor example 
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

 - aXAPI attributes can be used as options to configure loadbalancers.
 - Global options are specified under "virtual-server". (in this example is **"arp-disable": 1**)
 - Allow use regex expression to match specific object name and apply specific options to this object. 
    - User can specify matching list in **"name-expressions"**, and use **"regex"** to specify object name regex you want match.
      And then use **"json"** to specify options for matched objects.
	- Any object name that contains the string in **"regex"** will be matched.
    - In this example, loadbalancer **vip1** will configure **user-tag** as **vip1**.
      loadbalancer **vip2** will configure **user-tag** as **vip2**.

***

## Requirements


#### 2-1 software version

* a10-octavia v1.1 or later
* acos-client v2.6 or later
* ACOS 4.1.4-GR1-P5 or later

#### 2-2 database schema update
After upgrade to a10-octavia v1.1 (or later), you need to upgrade database schema for flavor support feature.


```shell
$ pip show a10-octavia
Name: a10-octavia
Version: 1.1
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


***

## Flavors


### 3-1 Flavor Support

#### supported flavors
* **virtual-server**: Specify aXAPI attributes to loadbalancer
* **virtual-port**: Specify aXAPI attributes to loadbalancer listeners
* **service-group**: Specify aXAPI attributes to loadbalancer pool
* **server**: Specify aXAPI attributes to loadbalancer member
* **health-monitor**: Specify aXAPI attributes to loadbalancer healthmonitor
* **nat-pool**: Create the SNAT pool on ACOS device and use this pool as default SNAT pool for listeners
* **nat-pool-list**: Create the SNAT pools on ACOS device

#### ACOS aXAPI
The aXAPI version 3.0 offers an HTTP interface that can be used to configure and monitor your ACOS device.
And for flaovr support feature, **a10-octavia allow user to specify aXAPI attributes in flavor options** to configure ACOS device objects.

For more information for aXAPI and **aXAPI attributes for slb objects**, please find aXAPI v3.0 document for more information:
 - aXAPI v30 document for ACOS 4.1.4-GR1-P5: https://documentation.a10networks.com/ACOS/414x/ACOS_4_1_4-GR1-P5/html/axapiv3/index.html
 - aXAPI v30 document for ACOS 5.2.1: http://acos.docs.a10networks.com/axapi/521/index.html

Please reference below example for how aXAPI attributes apply to flavor options.

#### simple flavor example

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

#### multiple matching
  For a slb object flavors we have global options and options in name-expression.
So, when name-expression is matched both global options and regex options will apply to this slb object. In this case:
- All aXAPI attributes will merge togethor.
- regex options has higher priority. So, for same attribute name in global option and regex option, regex option will apply.

And since a slb object may match to multiple name-expressions. In this case:
- All flavors (global option and all matched name-expressions regex options) will apply to the object
- regex options has higher priority. So, for same attribute name in global option and regex option, regex option will apply.
- latest matched name-expression has higher priority. So, in previous example. regex "vip2" has higher priority than regex "vip1".

***

### 3-2 virtual-server

- For supported aXAPI attributes for virtual-server flavor, please reference: https://documentation.a10networks.com/ACOS/411x/411-P1/ACOS_4_1_1-P1/html/axapiv3/slb_virtual_server.html#virtual-server-attributes
- Example Flavor
```python
{ 
    "virtual-server": 
    { 
        "vport-disable-action":"drop-packet" 
		"name-expressions": [
			{
				"regex": "vip2", 
                "json": {"user-tag": "vip2"} 
			}
		]
    } 
} 
```
- Commands
```shell
$ openstack loadbalancer flavorprofile create --name fp1 --provider a10 --flavor-data '{"virtual-server": {"vport-disable-action":"drop-packet", "name-expressions":[{"regex": "vip2", "json": {"user-tag": "vip2"}}]}}' 
$ openstack loadbalancer flavor create --name f1 --flavorprofile fp1 --description "vtest" --enable 
$ openstack loadbalancer create --flavor f1 --vip-subnet-id f25ce642-f953-4058-8c46-98fdd72fb129 --vip-address 192.168.91.56 --name vip1 
$ openstack loadbalancer create --flavor f1 --vip-subnet-id f25ce642-f953-4058-8c46-98fdd72fb129 --vip-address 192.168.91.57 --name vip2
```
- Expected Result
```shell
slb virtual-server 7347cf03-a3df-4333-9f36-2f058d071ab5 192.168.91.56
  vport-disable-action drop-packet
!
slb virtual-server c7250a77-8ecc-47e9-913a-809c6e187293 192.168.91.57
  vport-disable-action drop-packet
  user-tag vip2
!
```

***

### 3-3 virtual-port

- For supported aXAPI attributes for virtual-port flavor, please reference: https://documentation.a10networks.com/ACOS/411x/411-P1/ACOS_4_1_1-P1/html/axapiv3/slb_virtual_server_port.html#port-attributes
- Example Flavor
```python
{ 
    "virtual-port": { 
        "user-tag": "1", 
        "name-expressions": [ 
            { 
                "regex": "vport1", 
                "json": {"support-http2": 1} 
            }
        ] 
    }
}
```
- Commands
```shell
$ openstack loadbalancer flavorprofile create --name fp1 --provider a10 --flavor-data '{"virtual-port": {"user-tag": "1", "name-expressions": [{"regex": "vport1", "json": {"support-http2": 1}}]}}' 
$ openstack loadbalancer flavor create --name f1 --flavorprofile fp1 --description "flaovr test" --enable 
$ openstack loadbalancer create --flavor f1 --vip-subnet-id f25ce642-f953-4058-8c46-98fdd72fb129 --vip-address 192.168.91.56 --name vip1 
$ openstack loadbalancer listener create --protocol HTTP --protocol-port 80 --name vport1 vip1 
```
- Expected Result
```shell
slb virtual-server 7336f918-509a-47a1-8b84-9633ef2e632b 192.168.91.56
  port 80 http
    support-http2
    name 8714844f-14a3-4f1c-8826-d359cbe319ef
    extended-stats
    source-nat auto
    user-tag 1
!
```

***

###	3-4 service-group

- For supported aXAPI attributes for service-group flavor, please reference: https://documentation.a10networks.com/ACOS/411x/411-P1/ACOS_4_1_1-P1/html/axapiv3/slb_service_group.html#service-group-attributes
- Example Flavor
```python
{ 
    "service-group": { 
        "lb-method": "fastest-response", 
        "name-expressions": [ 
            { 
                "regex": "sg1",  
                "json": {"health-check-disable":1} 
            } 
        ] 
    }
}
```
- Commands
```shell
$ openstack loadbalancer flavorprofile create --name fp1 --provider a10 --flavor-data '{"service-group": {"lb-method": "fastest-response", "name-expressions": [{"regex": "sg1", "json": {"health-check-disable":1}}]}}' 
$ openstack loadbalancer flavor create --name f1 --flavorprofile fp1 --description "flaovr test" --enable 
$ openstack loadbalancer create --flavor f1 --vip-subnet-id f25ce642-f953-4058-8c46-98fdd72fb129 --vip-address 192.168.91.56 --name vip1 
$ openstack loadbalancer listener create --protocol HTTP --protocol-port 80 --name vport1 vip1 
$ openstack loadbalancer pool create --protocol HTTP --lb-algorithm ROUND_ROBIN --listener vport1 --name sg1 
```
- Expected Result
```shell
slb service-group a394ef89-b587-4749-8da8-662c9ef35181 tcp
  method fastest-response
  health-check-disable
!
slb virtual-server a10410be-97bf-4d35-ad30-0ed3e681883c 192.168.91.56
  port 80 http
    name aaed87f6-0d18-4d19-a635-ede8bc63d891
    extended-stats
    source-nat auto
    service-group a394ef89-b587-4749-8da8-662c9ef35181
!
```

***

### 3-5 server

- For supported aXAPI attributes for server flavor, please reference: https://documentation.a10networks.com/ACOS/411x/411-P1/ACOS_4_1_1-P1/html/axapiv3/slb_server.html#server-attributes
- Example Flavor
```python
{ 
    "server": { 
        "conn-limit": 65535, 
        "name-expressions": [ 
            { 
                "regex": "srv1", 
                "json": {"conn-resume": 5000} 
            }
        ] 
    }
}
```
- Commands
```shell
$ openstack loadbalancer flavorprofile create --name fp1 --provider a10 --flavor-data '{"server": {"conn-limit": 65535, "name-expressions": [{"regex": "srv1", "json": {"conn-resume": 5000}}]}}' 
$ openstack loadbalancer flavor create --name f1 --flavorprofile fp1 --description "flaovr test" --enable 
$ openstack loadbalancer create --flavor f1 --vip-subnet-id f25ce642-f953-4058-8c46-98fdd72fb129 --vip-address 192.168.91.56 --name vip1 
$ openstack loadbalancer listener create --protocol HTTP --protocol-port 80 --name vport1 vip1 
$ openstack loadbalancer pool create --protocol HTTP --lb-algorithm ROUND_ROBIN --listener vport1 --name sg1 
$ openstack loadbalancer member create --address 192.168.90.132 --subnet-id tp90 --protocol-port 80 --name srv1 sg1 
```
- Expected Result
```shell
slb server 3d21c_192_168_90_132 192.168.90.132
  conn-limit 65535
  conn-resume 5000
  port 80 tcp
!
slb service-group ed9eb517-584d-41d0-bebf-92ee0cc3e95c tcp
  member 3d21c_192_168_90_132 80
!
slb virtual-server abe4cf35-0532-4f62-8404-5e81a49c3238 192.168.91.56
  port 80 http
    name cf3edb1d-399d-4f54-9c10-e522b274a11a
    extended-stats
    source-nat auto
    service-group ed9eb517-584d-41d0-bebf-92ee0cc3e95c
!
```

***

### 3-6 health-monitor

- For supported aXAPI attributes for health-monitor flavor, please reference: https://documentation.a10networks.com/ACOS/411x/411-P1/ACOS_4_1_1-P1/html/axapiv3/health_monitor.html#monitor-attributes
- Example Flavor
```python
{
  "health-monitor":{ 
    "retry":5, 
    "method":{ 
      "http":{ 
        "http-response-code":"201" 
      } 
    }, 
    "name-expressions":[ 
    { 
      "regex":"hm1", 
      "json":{ 
        "timeout":8, 
        "method":{ 
          "http":{ 
            "http-host":"my.test.com" 
          } 
        } 
      } 
    } 
    ] 
  } 
}
```
- Commands
```shell
$ openstack loadbalancer flavorprofile create --name fp_hm1 --provider a10 --flavor-data '{"health-monitor": {"retry":5, "method": { "http": {"http-response-code":"201"}}, "name-expressions": [{"regex": "hm1", "json": {"timeout":8, "method": { "http": {"http-host":"my.test.com"}}}}]}}' 
$ openstack loadbalancer flavor create --name f_hm1 --flavorprofile fp_hm1 --description "hm test1" --enable 
$ openstack loadbalancer create --flavor f_hm1 --vip-subnet-id f25ce642-f953-4058-8c46-98fdd72fb129 --vip-address 192.168.91.56 --name vip1 
$ openstack loadbalancer listener create --protocol HTTP --protocol-port 80 --name vport1 vip1 
$ openstack loadbalancer pool create --protocol HTTP --lb-algorithm ROUND_ROBIN --listener vport1 --name sg1 
$ openstack loadbalancer healthmonitor create --delay 30 --timeout 3 --max-retries 3 --type HTTP sg1 --name hm1 

$ openstack loadbalancer listener create --protocol HTTP --protocol-port 8080 --name vport2 vip1 
$ openstack loadbalancer pool create --protocol HTTP --lb-algorithm ROUND_ROBIN --listener vport2 --name sg2 
$ openstack loadbalancer healthmonitor create --delay 30 --timeout 3 --max-retries 3 --type HTTP sg2 --name hm2 
```
- Expected Result

```shell
health monitor 05ba1984-c23a-4783-9215-4f8e7bedcc0a 
  retry 5 
  override-port 80 
  interval 30 timeout 8 
  method http port 80 expect response-code 200 host my.test.com url GET / 
! 
health monitor 4b3da84c-f1f4-480b-94e5-fd38793111a1 
  retry 5 
  override-port 8080 
  interval 30 timeout 3 
  method http port 8080 expect response-code 201 url GET / 
! 
ervice-group 237ebbfe-f2dd-4e12-9206-f1575e52ec39 tcp 
  health-check 05ba1984-c23a-4783-9215-4f8e7bedcc0a 
! 
slb service-group b904e527-19b5-450a-8f5f-ba47a32b774b tcp 
  health-check 4b3da84c-f1f4-480b-94e5-fd38793111a1 
! 
slb virtual-server 763eec3a-446e-4ca3-82e5-da7eb1ee202b 192.168.91.56 
  port 80 http 
    name 9c04c0cc-5392-4b89-9687-86ce41481c02 
    conn-limit 555000 
    extended-stats 
    source-nat auto 
    service-group 237ebbfe-f2dd-4e12-9206-f1575e52ec39 
  port 8080 http 
    name f97a4344-8000-405e-9e09-c24fdb4e44a9 
    conn-limit 555000 
    extended-stats 
    source-nat auto 
    service-group b904e527-19b5-450a-8f5f-ba47a32b774b 
!
```


***

### 3-7 nat-pool

- For supported aXAPI attributes for nat-pool flavor, please reference: https://documentation.a10networks.com/ACOS/411x/411-P1/ACOS_4_1_1-P1/html/axapiv3/ip_nat_pool.html#pool-attributes
- Example Flavor
```python
{  
    "nat-pool":{  
        "pool-name":"pool1",  
        "start-address":"192.168.90.201",  
        "end-address":"192.168.90.210",  
        "netmask":"/24",  
        "gateway":"192.168.90.1"  
    } 
}
```
- Commands
```shell
$ openstack loadbalancer flavorprofile create --name fp_snat --provider a10 --flavor-data '{"nat-pool":{"pool-name":"pool1", "start-address":"192.168.90.201", "end-address":"192.168.90.210", "netmask":"/24", "gateway":"192.168.90.1" }}' 
$ openstack loadbalancer flavor create --name f_snat --flavorprofile fp_snat --description "SNAT Flavor1" --enable 
$ openstack loadbalancer create --flavor f_snat --vip-subnet-id f25ce642-f953-4058-8c46-98fdd72fb129 --vip-address 192.168.91.56 --name vip1 
$ openstack loadbalancer listener create --protocol HTTP --protocol-port 80 --name vport1 vip1 
$ openstack loadbalancer pool create --protocol HTTP --lb-algorithm ROUND_ROBIN --listener vport1 --name sg1 
$ openstack loadbalancer member create --address 192.168.90.132 --subnet-id tp90 --protocol-port 80 --name srv1 sg1  
```
- Expected Result
```shell
ip nat pool pool1 192.168.90.201 192.168.90.210 netmask /24 gateway 192.168.90.1 
! 
slb server 3d21c_192_168_90_132 192.168.90.132 
  port 80 tcp 
! 
slb service-group 46997ede-9a87-4dfb-91d2-b208dcc6ea48 tcp 
  member 3d21c_192_168_90_132 80 
! 
slb virtual-server 0d406fc5-0f05-4c13-a831-4fda5cd079c6 192.168.91.56 
  port 80 http 
    name a9510efa-6d19-4c77-9925-a570cf196962 
    extended-stats 
    source-nat pool pool1 
    source-nat auto 
    service-group 46997ede-9a87-4dfb-91d2-b208dcc6ea48 
!
```


***

### 3-8 nat-pool-list

- For supported aXAPI attributes for nat-pool-list flavor, please reference: https://documentation.a10networks.com/ACOS/411x/411-P1/ACOS_4_1_1-P1/html/axapiv3/ip_nat_pool.html#pool-attributes
- Example Flavor
In this example, we use **"nat-pool"** flavor to configure a default NAT pool (i.e. **pool1**) for listeners. 
And then create another 2 NAT pool **pool2** and **pool3** on ACOS device via **"nat-pool-list"** flavor.
Then later, we can specify NAT pool we want in **"virtual-port"** flavor.


```python
{  
    "nat-pool":{  
        "pool-name":"pool1",  
        "start-address":"192.168.90.201",  
        "end-address":"192.168.90.210",  
        "netmask":"/24",  
        "gateway":"192.168.90.1"  
    },  
    "nat-pool-list":[  
        {  
            "pool-name":"pool2",  
            "start-address":"192.168.90.211",  
            "end-address":"192.168.90.220",  
            "netmask":"/24",  
            "gateway":"192.168.90.1"  
        },  
        {  
            "pool-name":"pool3",  
            "start-address":"192.168.90.221",  
            "end-address":"192.168.90.230",  
            "netmask":"/24",  
            "gateway":"192.168.90.1"  
        }  
    ], 
    "virtual-port": { 
        "name-expressions": [ 
            { 
                "regex": "vport2", 
                "json": {"pool": "pool2"} 
            }, 
        ] 
    } 
}
```
- Commands
```shell
$ openstack loadbalancer flavorprofile create --name fp_snat_list --provider a10 --flavor-data '{"nat-pool":{"pool-name":"pool1", "start-address":"192.168.90.201", "end-address":"192.168.90.210", "netmask":"/24", "gateway":"192.168.90.1"}, "nat-pool-list":[{"pool-name":"pool2", "start-address":"192.168.90.211", "end-address":"192.168.90.220", "netmask":"/24", "gateway":"192.168.90.1"}, {"pool-name":"pool3", "start-address":"192.168.90.221", "end-address":"192.168.90.230", "netmask":"/24", "gateway":"192.168.90.1"}], "virtual-port": {"name-expressions": [{"regex": "vport2", "json": {"pool": "pool2"}}]}}' 
$ openstack loadbalancer flavor create --name f_snat_list --flavorprofile fp_snat_list --description "flaovr all test1" --enable 

$ openstack loadbalancer create --flavor f_snat_list --vip-subnet-id f25ce642-f953-4058-8c46-98fdd72fb129 --vip-address 192.168.91.56 --name vip1 
$ openstack loadbalancer listener create --protocol HTTP --protocol-port 80 --name vport1 vip1 
$ openstack loadbalancer pool create --protocol HTTP --lb-algorithm ROUND_ROBIN --listener vport1 --name sg1 
$ openstack loadbalancer member create --address 192.168.90.132 --subnet-id tp90 --protocol-port 80 --name srv1 sg1 

$ openstack loadbalancer listener create --protocol HTTP --protocol-port 8080 --name vport2 vip1 
$ openstack loadbalancer pool create --protocol HTTP --lb-algorithm ROUND_ROBIN --listener vport2 --name sg2 
$ openstack loadbalancer member create --address 192.168.90.136 --subnet-id tp90 --protocol-port 80 --name srv2 sg2 
```
- Expected Result
```shell
ip nat pool pool1 192.168.90.201 192.168.90.210 netmask /24 gateway 192.168.90.1 
! 
ip nat pool pool2 192.168.90.211 192.168.90.220 netmask /24 gateway 192.168.90.1 
! 
ip nat pool pool3 192.168.90.221 192.168.90.230 netmask /24 gateway 192.168.90.1 
! 
slb server 3d21c_192_168_90_132 192.168.90.132 
  port 80 tcp 
! 
slb server 3d21c_192_168_90_136 192.168.90.136 
  port 80 tcp 
! 
slb service-group 789534a3-5d06-4a64-b6ae-d5e31417b145 tcp 
  member 3d21c_192_168_90_132 80 
! 
slb service-group d1d5cb40-29b3-42d4-b3ae-64f6bc22e671 tcp 
  member 3d21c_192_168_90_136 80 
! 
slb virtual-server 6e4badd1-aa4a-4eaf-963c-105e97fc162f 192.168.91.56 
  port 80 http 
    name 33e91ffd-93d4-4440-828c-fd054b3563db 
    extended-stats 
    source-nat pool pool1 
    source-nat auto 
    service-group 789534a3-5d06-4a64-b6ae-d5e31417b145 
  port 8080 http 
    name 11905d9a-31f2-438e-a303-42bf7739613f 
    extended-stats 
    source-nat pool pool2 
    source-nat auto 
    service-group d1d5cb40-29b3-42d4-b3ae-64f6bc22e671 
!
```

***

## Limitations

### 1.  The flavor-data can't be modified when flavorprofile is in used. User need to remove related loadbalancer objects before modify it.

### 2.	Don’t allow the "name" aXAPI attribute in flavor option for all slb objects (i.e. virtual-server, virtual-port, service-group, server and health-monitor). 
Since all object will use the same name and will cause problem.

### 3.	Some aXAPI attributes will conflict with openstack command options, a10-octavia will:
  * Reject some of these aXAPI attributes in flavor. (For example: "port-number" and "protocol" aXAPI attributes keys are not allowed for virtual-port flavor.
  * Some of them will be accepted, but the show result in openstack and ACOS device will be different. (For example: When service-group flavor specify "lb-method" and it is different from the openstack pool create/set command --lb-algorithm option. In thunder it will use the method specified in lb-method, but in openstack show command it still show method specified in –lb-algorithm.)
  
### 4.  Some aXAPI attributes will conflict with some default aXAPI attributes.
For example:
```python
{
	"health-monitor": {
		"method": { 
			"http": { 
				"response-code-regex":"20[0-5]"
			}
		}
	}
}
```
For health monitor, a10-octavia will have aXAPI attribute `"http-response-code": 200` for http method. But it will conflict with `"response-code-regex":"20[0-5]"` flavor.
So, the openstack command will failed. To prevent this problem, we need to use following flavor instead:
```python
{
	"health-monitor": {
		"method": {
			"http": {
				"http-response-code": null,
				"response-code-regex":"20[0-5]"
			}
		}
	}
}
```

