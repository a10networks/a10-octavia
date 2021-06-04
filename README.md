# A10 Networks OpenStack Octavia Driver

## Table of Contents
1. [Overview](#Overview)

2. [Project Resources](#Project-Resources)

3. [Issues and Inquiries](#Issues-and-Inquiries)

## Overview

**This solution is currently in beta stage with limited support**

The A10 Networks Octavia Driver allows for configuration of Thunder, vThunder, and AX Series Appliances deployed in
an Openstack enviroment. While the default Octavia provider leverages an "Amphora per VIP" architecture,
this provider driver uses a "Thunder per Tenant" architecture. Therefore, each tenant may only be serviced by a single
**active** Thunder device.

## Supported Versions

```
| a10-octavia    | acos-client   | ACOS Version        |
| v1.1           | v2.6.1        | 5.2.1, 4.1.4-GR1-P5 |
| v1.2           | v2.7.0        | 5.2.1-p1            |
```

## Project Resources

Installation and usage information is available at https://documentation.a10networks.com/Install/Software/A10_ACOS_Install/pdf/Thunder_openstack_octavia_install_guide.pdf

Release notes are available at https://documentation.a10networks.com/Install/Software/A10_ACOS_Install/pdf/Thunder_openstack_octavia_RN.pdf

## Issues and Inquiries
For all issues, please send an email to support@a10networks.com 
