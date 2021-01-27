# Copyright 2019 A10 Networks.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
#

from concurrent import futures
import datetime

from oslo_config import cfg
from oslo_log import log as logging

from octavia.controller.healthmanager import health_manager
from octavia.db import api as db_apis

from a10_octavia.controller.worker import controller_worker as cw
from a10_octavia.db import repositories as a10repo

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class A10HealthManager(health_manager.HealthManager):
    def __init__(self, exit_event):
        super(A10HealthManager, self).__init__(exit_event)
        self.cw = cw.A10ControllerWorker()
        self.threads = CONF.a10_health_manager.failover_threads
        self.executor = futures.ThreadPoolExecutor(max_workers=self.threads)
        self.vthunder_repo = a10repo.VThunderRepository()
        self.dead = exit_event

    def health_check(self):
        futs = []
        db_session = db_apis.get_session()
        list_full = False
        while not self.dead.is_set():
            vthunders = None
            try:
                db_session = db_apis.get_session()
                failover_wait_time = datetime.datetime.utcnow() - datetime.timedelta(
                    seconds=CONF.a10_health_manager.heartbeat_timeout)
                initial_setup_wait_time = datetime.datetime.utcnow() - datetime.timedelta(
                    seconds=CONF.a10_health_manager.failover_timeout)
                vthunders = self.vthunder_repo.get_stale_vthunders(
                    db_session, initial_setup_wait_time, failover_wait_time)

            except Exception as e:
                LOG.warning("Error getting stale thunders: %s", str(e))

            if vthunders is None:
                break

            for vthunder in vthunders:
                if self.dead.is_set():
                    break

                LOG.info("Stale vThunder's id is: %s", vthunder.vthunder_id)
                fut = self.executor.submit(self.cw.failover_amphora, vthunder.vthunder_id)
                futs.append(fut)
                if len(futs) == self.threads:
                    list_full = True
                    break

            if list_full is True:
                break

        if futs:
            LOG.info("Waiting for %s failovers to finish",
                     len(futs))
            health_manager.wait_done_or_dead(futs, self.dead)
            LOG.info("Successfully completed failover for VThunders.")
