#!/bin/bash
#
# Credit for this goes to the upstream Openstack community. You may find the
# original file here:
#
#   https://github.com/openstack/octavia/blob/master/devstack/contrib/new-octavia-devstack.sh
#
# These instructions assume an Ubuntu-based host or VM for running devstack.
# Please note that if you are running this in a VM, it is vitally important
# that the underlying hardware have nested virtualization enabled or you will
# experience very poor amphora performance.

# Set up the packages we need. Ubuntu package manager is assumed.
apt-get update
apt-get install git vim -y

# Clone the devstack repo
git clone https://github.com/openstack-dev/devstack.git $HOME/devstack
cd $HOME/devstack

git checkout stable/stein

git clone https://github.com/openstack/python-octaviaclient.git $HOME/python-octaviaclient
cd $HOME/python-octaviaclient

git checkout stable/stein
pip install -e .

cat <<EOF > $HOME/devstack/localrc
enable_plugin barbican https://opendev.org/openstack/barbican stable/stein
enable_plugin neutron https://opendev.org/openstack/neutron stable/stein
enable_plugin octavia https://opendev.org/openstack/octavia stable/stein

KEYSTONE_TOKEN_FORMAT=fernet

DATABASE_PASSWORD=password
RABBIT_PASSWORD=password
ADMIN_PASSWORD=password
SERVICE_PASSWORD=password
SERVICE_TOKEN=111222333444
# Enable Logging
LOGFILE=/opt/stack/logs/stack.sh.log
VERBOSE=True
LOG_COLOR=True
# Pre-requisite
ENABLED_SERVICES=key,rabbit,mysql,horizon
# Nova
ENABLED_SERVICES+=,n-api,n-crt,n-cpu,n-cond,n-sch,n-api-meta,n-sproxy
ENABLED_SERVICES+=,placement-api,placement-client
# Glance
ENABLED_SERVICES+=,g-api,g-reg
# Neutron
ENABLED_SERVICES+=,q-svc,q-agt,q-dhcp,q-l3,q-meta,neutron
ENABLED_SERVICES+=,octavia,o-cw,o-hk,o-hm,o-api
# Cinder
ENABLED_SERVICES+=,c-api,c-vol,c-sch
# Tempest (optional)
#ENABLED_SERVICES+=,tempest
EOF

# Create the stack user
$HOME/devstack/tools/create-stack-user.sh

# Move everything into place
mv $HOME/devstack /opt/stack/
chown -R stack:stack /opt/stack/devstack/

# Fix permissions on current tty so screens can attach
chmod go+rw `tty`

# Stack that stack!
su - stack -c /opt/stack/devstack/stack.sh

# Add environment variables for auth/endpoints
echo 'source /opt/stack/devstack/openrc admin admin' >> /opt/stack/.bashrc

# Drop into a shell
exec su - stack
