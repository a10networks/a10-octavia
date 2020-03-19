#    Copyright 2019, A10 Networks
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

import cotyledon
from cotyledon import oslo_config_glue
import logging
import sys

from oslo_config import cfg
from oslo_reports import guru_meditation_report as gmr

from octavia import version

from a10_octavia.cmd import service as octavia_service
from a10_octavia.controller.queue import consumer


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


def main():
    octavia_service.prepare_service(sys.argv)
    gmr.TextGuruMeditation.setup_autorun(version)
    sm = cotyledon.ServiceManager()
    sm.add(consumer.ConsumerService, workers=CONF.a10_controller_worker.workers,
           args=(CONF,))
    oslo_config_glue.setup(sm, CONF, reload_method="mutate")
    sm.run()
