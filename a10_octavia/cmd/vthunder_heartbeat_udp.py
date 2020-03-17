# Copyright 2019 A10 Networks
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import datetime
import socket

from oslo_config import cfg
from oslo_log import log as logging

from octavia.common import exceptions
from octavia.db import api as db_api

from a10_octavia.db import repositories as a10repo

UDP_MAX_SIZE = 64 * 1024
CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class VThunderUDPStatusGetter(object):
    """This class defines methods that will gather heatbeats.
    """

    def __init__(self):
        self.key = CONF.a10_health_manager.heartbeat_key
        self.ip = CONF.a10_health_manager.bind_ip
        self.port = CONF.a10_health_manager.bind_port
        self.sockaddr = None
        LOG.info('attempting to listen on %(ip)s port %(port)s',
                 {'ip': self.ip, 'port': self.port})
        self.sock = None
        self.update(self.key, self.ip, self.port)
        self.vthunder_repo = a10repo.VThunderRepository()

    def update(self, key, ip, port):
        """Update the running config for the udp socket server

        :param key: The hmac key used to verify the UDP packets. String
        :param ip: The ip address the UDP server will read from
        :param port: The port the UDP server will read from
        :return: None
        """
        self.key = key
        for addrinfo in socket.getaddrinfo(ip, port, 0, socket.SOCK_DGRAM):
            ai_family = addrinfo[0]
            self.sockaddr = addrinfo[4]
            if self.sock is not None:
                self.sock.close()
            self.sock = socket.socket(ai_family, socket.SOCK_DGRAM)
            self.sock.settimeout(1)
            self.sock.bind(self.sockaddr)
            if CONF.a10_health_manager.sock_rlimit > 0:
                rlimit = CONF.a10_health_manager.sock_rlimit
                LOG.info("setting sock rlimit to %s", rlimit)
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF,
                                     rlimit)
            break  # just used the first addr getaddrinfo finds
        if self.sock is None:
            raise exceptions.NetworkConfig("Unable to find suitable socket")

    def check(self):
        """Wait and obtain the source address of UDP packet and updates its time in
           vThunder repositories.
        """
        try:
            data, srcaddr = self.sock.recvfrom(UDP_MAX_SIZE)
            ip, port = srcaddr
            LOG.warning('Received packet from %s', ip)
            # get record id of first vThunder from srcaddr
            record_id = self.vthunder_repo.get_vthunder_from_src_addr(db_api.get_session(), ip)

            if record_id:
                last_udp_update = datetime.datetime.utcnow()
                self.vthunder_repo.update(db_api.get_session(), record_id,
                                          last_udp_update=last_udp_update)
        except socket.timeout:
            # Pass here as this is an expected cycling of the listen socket
            pass
        except exceptions.InvalidHMACException:
            # Pass here as the packet was dropped and logged already
            pass
        except Exception as ex:
            LOG.warning('Health Manager experienced an exception processing a'
                        'heartbeat packet. Ignoring this packet. '
                        'Exception: %s', ex)
