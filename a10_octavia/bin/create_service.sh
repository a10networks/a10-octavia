#!/bin/sh

echo "trying something"
SYSTEMD_SCRIPT_DIR=$( cd  $(dirname "${BASH_SOURCE:=$0}") && pwd)
cp -f "$SYSTEMD_SCRIPT_DIR/a10-controller-worker.service" /etc/systemd/system/
chown root:root /etc/systemd/system/a10-controller-worker.service

systemctl daemon-reload
systemctl enable a10-controller-worker.service
systemctl start a10-controller-worker.service
