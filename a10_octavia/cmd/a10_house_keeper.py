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


from datetime import datetime
import signal
import sys
import threading
import time

from oslo_config import cfg
from oslo_log import log as logging
from oslo_reports import guru_meditation_report as gmr

from a10_octavia.cmd import service
from a10_octavia.controller.housekeeping import house_keeping
from octavia import version

LOG = logging.getLogger(__name__)
CONF = cfg.CONF

spare_amp_thread_event = threading.Event()
db_cleanup_thread_event = threading.Event()
write_memory_thread_event = threading.Event()


def spare_amphora_check():
    """Initiates spare amp check with respect to configured interval."""

    # Read the interval from CONF
    interval = CONF.a10_house_keeping.spare_check_interval
    LOG.info("Spare check interval is set to %d sec", interval)
    spare_amp = house_keeping.SpareAmphora()
    while not spare_amp_thread_event.is_set():
        LOG.debug("Initiating spare amphora check...")
        try:
            spare_amp.spare_check()
        except Exception as e:
            LOG.debug('spare_amphora caught the following exception and '
                      'is restarting: {}'.format(e))
        spare_amp_thread_event.wait(interval)


def db_cleanup():
    """Perform db cleanup for old resources."""
    # Read the interval from CONF
    interval = CONF.a10_house_keeping.cleanup_interval
    LOG.info("DB cleanup interval is set to %d sec", interval)
    LOG.info('Amphora expiry age is %s seconds',
             CONF.a10_house_keeping.amphora_expiry_age)
    LOG.info('Load balancer expiry age is %s seconds',
             CONF.a10_house_keeping.load_balancer_expiry_age)

    db_cleanup = house_keeping.DatabaseCleanup()
    while not db_cleanup_thread_event.is_set():
        LOG.info("Initiating the cleanup of old resources...")
        try:
            db_cleanup.delete_old_amphorae()
            db_cleanup.cleanup_load_balancers()
        except Exception as e:
            LOG.info('db_cleanup caught the following exception and '
                     'is restarting: {}'.format(e))
        db_cleanup_thread_event.wait(interval)


def write_memory():
    """Performs write memory for all thunders"""
    if CONF.a10_house_keeping.use_periodic_write_memory == 'enable':
        interval = CONF.a10_house_keeping.write_mem_interval
        write_memory_perform = house_keeping.WriteMemory()
        LOG.info("Write Memory interval set to %s seconds", interval)
        while not write_memory_thread_event.is_set():
            LOG.info("Initiating the write memory operation for all thunders...")
            timestamp = datetime.utcnow()
            LOG.debug("Starting write memory thread ar %s", str(timestamp))
            try:
                write_memory_perform.perform_memory_writes()
            except Exception as e:
                LOG.exception('write memory caught the following exception and '
                              ' is restarting: {}'.format(e))
            write_memory_thread_event.wait(interval)
    else:
        LOG.warning("Write memory flag is disabled...")


def _mutate_config(*args, **kwargs):
    LOG.info("Housekeeping recieved HUP signal, mutating config.")
    CONF.mutate_config_files()


def main():
    service.prepare_service(sys.argv)

    gmr.TextGuruMeditation.setup_autorun(version)

    timestamp = datetime.utcnow()
    LOG.info("Starting house keeping at %s", str(timestamp))

    # Thread to perform spare amphora check
    spare_amp_thread = threading.Thread(target=spare_amphora_check)
    spare_amp_thread.daemon = True
    spare_amp_thread.start()

    # Thread to perform db cleanup
    db_cleanup_thread = threading.Thread(target=db_cleanup)
    db_cleanup_thread.daemon = True
    db_cleanup_thread.start()

    # Thread to perform write memory
    write_memory_thread = threading.Thread(target=write_memory)
    write_memory_thread.daemon = True
    write_memory_thread.start()

    signal.signal(signal.SIGHUP, _mutate_config)

    # Try-Exception block should be at the end to gracefully exit threads
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        LOG.info("Attempting to gracefully terminate House-Keeping")
        spare_amp_thread_event.set()
        db_cleanup_thread_event.set()
        write_memory_thread_event.set()
        spare_amp_thread.join()
        db_cleanup_thread.join()
        write_memory_thread.join()
        LOG.info("House-Keeping process terminated")
