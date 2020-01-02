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

from concurrent import futures
import binascii
import hashlib
import socket
import time
import hmac
import zlib
import datetime
from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import secretutils
from stevedore import driver as stevedore_driver

from octavia.common import exceptions
from octavia.db import api as db_api
from a10_octavia.db import repositories as a10repo

UDP_MAX_SIZE = 64 * 1024
CONF = cfg.CONF
LOG = logging.getLogger(__name__)

hash_len = 32
hex_hash_len = 64


class UDPStatusGetter(object):
    """This class defines methods that will gather heatbeats

    The heartbeats are transmitted via UDP and this class will bind to a port
    and absorb them
    """
    def __init__(self):
        self.key = cfg.CONF.health_manager.heartbeat_key
        self.ip = cfg.CONF.health_manager.bind_ip
        self.port = cfg.CONF.health_manager.bind_port
        self.sockaddr = None
        LOG.info('attempting to listen on %(ip)s port %(port)s',
                 {'ip': self.ip, 'port': self.port})
        self.sock = None
        self.update(self.key, self.ip, self.port)

        self.health_executor = futures.ProcessPoolExecutor(
            max_workers=CONF.health_manager.health_update_threads)
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
            if cfg.CONF.health_manager.sock_rlimit > 0:
                rlimit = cfg.CONF.health_manager.sock_rlimit
                LOG.info("setting sock rlimit to %s", rlimit)
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF,
                                     rlimit)
            break  # just used the first addr getaddrinfo finds
        if self.sock is None:
            raise exceptions.NetworkConfig("unable to find suitable socket")

    def dorecv(self, *args, **kw):
        """Waits for a UDP heart beat to be sent.

        :return: Returns the unwrapped payload and addr that sent the
                 heartbeat. The format of the obj from the UDP sender
                 can be seen below. Note that listener_1 has no pools
                 and listener_4 has no members.

        """
        (data, srcaddr) = self.sock.recvfrom(UDP_MAX_SIZE)
        ip, port = srcaddr
        LOG.warning('Received packet from %s', ip) 
        # get record id of first vthunder from srcaddr
        record_id = self.vthunder_repo.get_vthunder_from_src_addr(db_api.get_session(), ip)
       
        if record_id:
            last_udp_update = datetime.datetime.utcnow()
            self.vthunder_repo.update(db_api.get_session(), record_id, last_udp_update=last_udp_update) 
        
        return srcaddr[0]

    def check(self):
        try:
            srcaddr = self.dorecv()
        except socket.timeout:
            # Pass here as this is an expected cycling of the listen socket
            pass
        except exceptions.InvalidHMACException:
            # Pass here as the packet was dropped and logged already
            pass
        except Exception as e:
            LOG.warning('Health Manager experienced an exception processing a'
                        'heartbeat packet. Ignoring this packet. '
                        'Exception: %s', e)
