#!/bin/sh

echo "Installing a10-controller-worker..."
SYSTEMD_SCRIPT_DIR = $(cd $(dirname "${BASH_SOURCE:=$0}") && pwd)
cp -f "$SYSTEMD_SCRIPT_DIR/a10-controller-worker.service" /etc/systemd/system/
cp -f "$SYSTEMD_SCRIPT_DIR/a10-house-keeper.service" /etc/systemd/system/
chown root:root /etc/systemd/system/a10-controller-worker.service
chown root:root /etc/systemd/system/a10-house-keeper.service

systemctl daemon-reload
systemctl enable a10-controller-worker.service
systemctl enable a10-house-keeper.service
systemctl start a10-controller-worker.service
systemctl start a10-house-keeper.service
echo "Completed installtion a10-controller-worker and a10-house-keeper service"
