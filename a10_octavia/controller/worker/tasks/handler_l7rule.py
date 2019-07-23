from taskflow import task

from octavia.controller.worker import task_utils as task_utilities
from octavia.common import constants
import acos_client
from octavia.amphorae.driver_exceptions import exceptions as driver_except
import time
from oslo_log import log as logging
from oslo_config import cfg
from a10_octavia.common import openstack_mappings
from a10_octavia.controller.worker.tasks.policy import PolicyUtil
from a10_octavia.controller.worker.tasks import persist
from a10_octavia.controller.worker.tasks.common import BaseVThunderTask

CONF = cfg.CONF
LOG = logging.getLogger(__name__)

class CreateL7Rule(BaseVThunderTask):
    """ Task to create a healthmonitor and associate it with provided pool. """

    def execute(self, l7rule, listeners, vthunder):
        """ Execute create health monitor for amphora """
        axapi_version = acos_client.AXAPI_21 if vthunder.axapi_version == 21 else acos_client.AXAPI_30
        try:
            l7policy = l7rule.l7policy
            filename = l7policy.id
            action = "import"
            p = PolicyUtil()
            script = p.createPolicy(l7policy)
            size = len(script.encode('utf-8'))
            c = acos_client.Client(vthunder.ip_address, axapi_version, vthunder.username,
                                       vthunder.password)
            out = c.slb.aflex_policy.create(file=filename, script=script, size=size, action=action)
            LOG.info("aFlex policy created successfully.")
        except Exception as e:
            print(str(e))
            LOG.info("Error occurred")
        try:
            # get SLB vPort
            listener = listeners[0]

            new_listener = listeners[0]
            c = acos_client.Client(vthunder.ip_address, axapi_version, vthunder.username,
                                       vthunder.password)
            get_listener = c.slb.virtual_server.vport.get(listener.load_balancer_id, listener.name,
                                                listener.protocol, listener.protocol_port)

            aflex_scripts = []
            if 'aflex-scripts' in get_listener['port']:
                aflex_scripts = get_listener['port']['aflex-scripts']
                aflex_scripts.append({"aflex": filename})
            else:
                aflex_scripts = [{"aflex": filename}]

            persistence = persist.PersistHandler(
            c, listener.default_pool)

            s_pers = persistence.s_persistence()
            c_pers = persistence.c_persistence()

            kargs = {}
            kargs["aflex-scripts"] = aflex_scripts

            update_listener = c.slb.virtual_server.vport.update(listener.load_balancer_id, listener.name,
                                                                listener.protocol, listener.protocol_port, listener.default_pool_id,
                                                                s_pers, c_pers, 1, **kargs)
            LOG.info("Listener updated successfully.")
        except Exception as e:
            print(str(e))
            LOG.info("Error occurred")

class DeleteL7Rule (BaseVThunderTask):
    """ Task to delete a l7rule and associate it with provided pool. """

    def execute(self, l7rule, listeners, vthunder):
        """ Execute create health monitor for amphora """
        axapi_version = acos_client.AXAPI_21 if vthunder.axapi_version == 21 else acos_client.AXAPI_30
        policy = l7rule.l7policy
        rules = policy.l7rules

        for index, rule in enumerate(rules):
                if rule.id == l7rule.id:
                    del rules[index]
                    break
        policy.rules = rules
        l7rule.l7policy = policy
        try:
            l7pol = l7rule.l7policy
            filename = l7pol.id
            action = "import"
            p = PolicyUtil()
            script = p.createPolicy(l7pol)
            size = len(script.encode('utf-8'))
            c = acos_client.Client(vthunder.ip_address, axapi_version, vthunder.username,
                                       vthunder.password)
            out = c.slb.aflex_policy.create(file=filename, script=script, size=size, action=action)
            LOG.info("aFlex policy created successfully.")
        except Exception as e:
            print(str(e))
            LOG.info("Error occurred")
        try:
            # get SLB vPort
            listener = listeners[0]

            new_listener = listeners[0]
            c = acos_client.Client(vthunder.ip_address, axapi_version, vthunder.username,
                                       vthunder.password)
            get_listener = c.slb.virtual_server.vport.get(listener.load_balancer_id, listener.name,
                                                listener.protocol, listener.protocol_port)

            aflex_scripts = []
            if 'aflex-scripts' in get_listener['port']:
                aflex_scripts = get_listener['port']['aflex-scripts']
                aflex_scripts.append({"aflex": filename})
            else:
                aflex_scripts = [{"aflex": filename}]

            persistence = persist.PersistHandler(
            c, listener.default_pool)

            s_pers = persistence.s_persistence()
            c_pers = persistence.c_persistence()

            kargs = {}
            kargs["aflex-scripts"] = aflex_scripts

            update_listener = c.slb.virtual_server.vport.update(listener.load_balancer_id, listener.name,
                                                                listener.protocol, listener.protocol_port, listener.default_pool_id,
                                                                s_pers, c_pers, 1, **kargs)
            LOG.info("Listener updated successfully.")
        except Exception as e:
            print(str(e))
            LOG.info("Error occurred")





