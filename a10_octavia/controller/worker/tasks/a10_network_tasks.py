# Copyright 2019, A10 Networks
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
import acos_client.errors as acos_errors
import copy
#from neutronclient.common import exceptions as neutron_exceptions
import openstack.exceptions as os_exceptions
from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import uuidutils
from requests import exceptions as req_exceptions
import six
from taskflow import task
from taskflow.types import failure

from octavia.common import constants
from octavia.common import data_models as o_data_models
from octavia.controller.worker import task_utils
from octavia.db import api as db_apis
from octavia.network import base
from octavia.network import data_models as n_data_models

from a10_octavia.common import a10constants
from a10_octavia.common import data_models
from a10_octavia.common import exceptions
from a10_octavia.common import utils as a10_utils
from a10_octavia.controller.worker.tasks.decorators import axapi_client_decorator
from a10_octavia.controller.worker.tasks import utils as a10_task_utils
from a10_octavia.db import repositories as a10_repo
from octavia.db import repositories as repo

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class BaseNetworkTask(task.Task):
    """Base task to load drivers common to the tasks."""

    def __init__(self, **kwargs):
        super(BaseNetworkTask, self).__init__(**kwargs)
        self._network_driver = None
        self.task_utils = task_utils.TaskUtils()
        self.vthunder_repo = a10_repo.VThunderRepository()
        self.amphora_repo = repo.AmphoraRepository()
        self.loadbalancer_repo = repo.LoadBalancerRepository()

    @property
    def network_driver(self):
        if self._network_driver is None:
            self._network_driver = a10_utils.get_network_driver()
        return self._network_driver


class CalculateAmphoraDelta(BaseNetworkTask):

    default_provides = constants.DELTA

    def execute(self, loadbalancer, loadbalancers_list, amphora, member_list):
        LOG.debug("Calculating network delta for amphora id: %s", amphora.get(constants.ID))
        # Figure out what networks we want
        # seed with lb network(s)

        #desired_network_ids = set(CONF.a10_controller_worker.amp_boot_network_list[:])
        management_nets = set(CONF.a10_controller_worker.amp_boot_network_list[:])
        session = db_apis.get_session()
        with session.begin():
                db_lb = self.loadbalancer_repo.get(
                    session, id=loadbalancer[constants.LOADBALANCER_ID])
        desired_subnet_to_net_map = {
            loadbalancer[constants.VIP_SUBNET_ID]:
            loadbalancer[constants.VIP_NETWORK_ID]
        }
        for loadbalancer in loadbalancers_list:
            for pool in db_lb.pools:
                for member in pool.members:
                    if member.subnet_id and member in member_list:
                        member_network = self.network_driver.get_subnet(
                            member.subnet_id).network_id
                        desired_subnet_to_net_map[member.subnet_id] = (
                            member_network)
                    else:
                        LOG.warning("Subnet id argument was not specified during "
                                    "issuance of create command/API call for member %s. "
                                    "Skipping interface attachment", member.id)

                    #desired_network_ids.update(member_networks)
        desired_network_ids = set(desired_subnet_to_net_map.values())
        desired_subnet_ids = set(desired_subnet_to_net_map)

        # loadbalancer_networks = [
        #     self.network_driver.get_subnet(loadbalancer['vip_subnet_id']).network_id
        #     for loadbalancer in loadbalancers_list
        #     if loadbalancer['vip_subnet_id']
        # ]
        # desired_network_ids.update(loadbalancer_networks)
        LOG.debug("[NetIF] desired_network_ids.update{0}".format(desired_network_ids))

        #nics = self.network_driver.get_plugged_networks(amphora.compute_id)
        nics = self.network_driver.get_plugged_networks(
            amphora[constants.COMPUTE_ID])
        # assume we don't have two nics in the same network
        # actual_network_nics = dict((nic.network_id, nic) for nic in nics)
        # LOG.debug("[NetIF] actual_network_nics {0}".format(actual_network_nics))

        # del_ids = set(actual_network_nics) - desired_network_ids
        # delete_nics = list(
        #     actual_network_nics[net_id] for net_id in del_ids)

        # add_ids = desired_network_ids - set(actual_network_nics)
        # add_nics = list(n_data_models.Interface(
        #     network_id=net_id) for net_id in add_ids)
        # delta = n_data_models.Delta(
        #     amphora_id=amphora.id, compute_id=amphora.compute_id,
        #     add_nics=add_nics, delete_nics=delete_nics)
        # return delta
        network_to_nic_map = {
            nic.network_id: nic
            for nic in nics
            if nic.network_id not in management_nets}

        plugged_network_ids = set(network_to_nic_map)

        del_ids = plugged_network_ids - desired_network_ids
        delete_nics = [n_data_models.Interface(
            network_id=net_id,
            port_id=network_to_nic_map[net_id].port_id)
            for net_id in del_ids]

        add_ids = desired_network_ids - plugged_network_ids
        add_nics = [n_data_models.Interface(
            network_id=add_net_id,
            fixed_ips=[
                n_data_models.FixedIP(
                    subnet_id=subnet_id)
                for subnet_id, net_id in desired_subnet_to_net_map.items()
                if net_id == add_net_id])
            for add_net_id in add_ids]

        # Calculate member Subnet deltas
        plugged_subnets = {}
        for nic in network_to_nic_map.values():
            for fixed_ip in nic.fixed_ips or []:
                plugged_subnets[fixed_ip.subnet_id] = nic.network_id

        plugged_subnet_ids = set(plugged_subnets)
        del_subnet_ids = plugged_subnet_ids - desired_subnet_ids
        add_subnet_ids = desired_subnet_ids - plugged_subnet_ids

        def _subnet_updates(subnet_ids, subnets):
            updates = []
            for s in subnet_ids:
                network_id = subnets[s]
                nic = network_to_nic_map.get(network_id)
                port_id = nic.port_id if nic else None
                updates.append({
                    constants.SUBNET_ID: s,
                    constants.NETWORK_ID: network_id,
                    constants.PORT_ID: port_id
                })
            return updates

        add_subnets = _subnet_updates(add_subnet_ids,
                                      desired_subnet_to_net_map)
        del_subnets = _subnet_updates(del_subnet_ids,
                                      plugged_subnets)

        delta = n_data_models.Delta(
            amphora_id=amphora[constants.ID],
            compute_id=amphora[constants.COMPUTE_ID],
            add_nics=add_nics, delete_nics=delete_nics,
            add_subnets=add_subnets,
            delete_subnets=del_subnets)
        return delta.to_dict(recurse=True)

class CalculateDelta(BaseNetworkTask):
    """Task to calculate the delta between

    the nics on the amphora and the ones
    we need. Returns a list for
    plumbing them.
    """

    default_provides = constants.DELTAS

    def execute(self, loadbalancer, loadbalancers_list, member_list):
        """Compute which NICs need to be plugged

        for the amphora to become operational.

        :param loadbalancer: the loadbalancer to calculate deltas for all
                             amphorae
        :returns: dict of octavia.network.data_models.Delta keyed off amphora
                  id
        """
        calculate_amp = CalculateAmphoraDelta()
        deltas = {}
        session = db_apis.get_session()
        with session.begin():
            db_lb = self.loadbalancer_repo.get(
                session, id=loadbalancer[constants.LOADBALANCER_ID])
        for amphora in six.moves.filter(
            lambda amp: amp.status == constants.AMPHORA_ALLOCATED,
                db_lb.amphorae):

            delta = calculate_amp.execute(loadbalancer, loadbalancers_list, amphora.to_dict(), member_list)
            deltas[amphora.id] = delta
        return deltas


class GetPlumbedNetworks(BaseNetworkTask):
    """Task to figure out the NICS on an amphora.

    This will likely move into the amphora driver
    :returns: Array of networks
    """

    default_provides = constants.NICS

    def execute(self, amphora):
        """Get plumbed networks for the amphora."""

        LOG.debug("Getting plumbed networks for amphora id: %s", amphora[constants.ID])

        return self.network_driver.get_plugged_networks(amphora[constants.COMPUTE_ID])


class PlugNetworks(BaseNetworkTask):
    """Task to plug the networks.

    This uses the delta to add all missing networks/nics
    """

    def execute(self, amphora, delta):
        """Update the amphora networks for the delta."""

        LOG.debug("Plug or unplug networks for amphora id: %s", amphora[constants.ID])

        if not delta:
            LOG.debug("No network deltas for amphora id: %s", amphora[constants.ID])
            return

        # add nics
        for nic in delta[constants.ADD_NICS]:
            self.network_driver.plug_network(amphora[constants.COMPUTE_ID],
                                             nic[constants.NETWORK_ID])

    def revert(self, amphora, delta, *args, **kwargs):
        """Handle a failed network plug by removing all nics added."""

        LOG.warning("Unable to plug networks for amp id %s", amphora[constants.ID])
        if not delta:
            return

        for nic in delta[constants.ADD_NICS]:
            try:
                self.network_driver.unplug_network(amphora[constants.COMPUTE_ID],
                                                   nic[constants.NETWORK_ID])
            except base.NetworkNotFound:
                pass


class UnPlugNetworks(BaseNetworkTask):
    """Task to unplug the networks

    Loop over all nics and unplug them
    based on delta
    """

    def execute(self, amphora, delta):
        """Unplug the networks."""

        LOG.debug("Unplug network for amphora")
        if not delta:
            LOG.debug("No network deltas for amphora id: %s", amphora[constants.ID])
            return

        for nic in delta[constants.DELETE_NICS]:
            try:
                self.network_driver.unplug_network(amphora[constants.COMPUTE_ID],
                                                   nic[constants.NETWORK_ID])
            except base.NetworkNotFound:
                LOG.debug("Network %d not found", nic[constants.NETWORK_ID])
            except Exception:
                LOG.exception("Unable to unplug network")


class PlugNetworksByID(BaseNetworkTask):
    """Task to plug the networks in the list."""

    def __init__(self, *arg, **kwargs):
        self.added_network = []
        super(PlugNetworksByID, self).__init__(*arg, **kwargs)

    def execute(self, vthunder, network_list):
        nets = set(network_list)
        nics = self.network_driver.get_plugged_networks(vthunder.compute_id)
        exist_ids = set([nic.network_id for nic in nics])

        self.added_network = list(nets.difference(exist_ids))
        for net in self.added_network:
            try:
                self.network_driver.plug_network(vthunder.compute_id, net)
            except Exception as e:
                LOG.exception("Failed to plug network: %s", net)
                raise e
        return self.added_network

    def revert(self, vthunder, network_list, *args, **kwargs):
        for net in self.added_network:
            try:
                self.network_driver.unplug_network(vthunder.compute_id, net)
            except base.NetworkNotFound:
                pass


class GetMemberPorts(BaseNetworkTask):

    def execute(self, loadbalancer, amphora):
        vip_port = self.network_driver.get_port(loadbalancer['vip_port_id'])
        member_ports = []
        interfaces = self.network_driver.get_plugged_networks(
            amphora[constants.COMPUTE_ID])
        for interface in interfaces:
            port = self.network_driver.get_port(interface.port_id)
            if vip_port.network_id == port.network_id:
                continue
            port.network = self.network_driver.get_network(port.network_id)
            for fixed_ip in port.fixed_ips:
                if amphora['lb_network_ip'] == fixed_ip.ip_address:
                    break
                fixed_ip.subnet = self.network_driver.get_subnet(
                    fixed_ip.subnet_id)
            # Only add the port to the list if the IP wasn't the mgmt IP
            else:
                member_ports.append(port)
        return member_ports


class HandleNetworkDelta(BaseNetworkTask):
    """Task to plug and unplug networks

    Plug or unplug networks based on delta
    """

    # def execute(self, amphora, delta):
    #     """Handle network plugging based off deltas."""
    #     added_ports = {}
    #     added_ports[amphora.id] = []
    #     for nic in delta.add_nics:
    #         interface = self.network_driver.plug_network(delta.compute_id,
    #                                                      nic.network_id)
    #         port = self.network_driver.get_port(interface.port_id)
    #         port.network = self.network_driver.get_network(port.network_id)
    #         for fixed_ip in port.fixed_ips:
    #             fixed_ip.subnet = self.network_driver.get_subnet(
    #                 fixed_ip.subnet_id)
    #         added_ports[amphora.id].append(port)
    #     for nic in delta.delete_nics:
    #         try:
    #             self.network_driver.unplug_network(delta.compute_id,
    #                                                nic.network_id)

    #         except base.NetworkNotFound:
    #             LOG.debug("Network %d not found ", nic.network_id)
    #         except Exception:
    #             LOG.exception("Unable to unplug network")
    #     return added_ports

    def _fill_port_info(self, port):
        port.network = self.network_driver.get_network(port.network_id)
        for fixed_ip in port.fixed_ips:
            fixed_ip.subnet = self.network_driver.get_subnet(
                fixed_ip.subnet_id)

    def execute(self, amphora, delta):
        """Handle network plugging based off deltas."""
        session = db_apis.get_session()
        with session.begin():
            db_amp = self.amphora_repo.get(session,
                                           id=amphora.get(constants.ID))
        updated_ports = {}
        for nic in delta[constants.ADD_NICS]:
            subnet_id = nic[constants.FIXED_IPS][0][constants.SUBNET_ID]
            LOG.debug("[NetIF] plug_network %s on %s", nic[constants.NETWORK_ID], db_amp.compute_id)
            interface = self.network_driver.plug_network(
                db_amp.compute_id, nic[constants.NETWORK_ID])
            port = self.network_driver.get_port(interface.port_id)
            # nova may plugged undesired subnets (it plugs one of the subnets
            # of the network), we can safely unplug the subnets we don't need,
            # the desired subnet will be added in the 'ADD_SUBNETS' loop.
            extra_subnets = [
                fixed_ip.subnet_id
                for fixed_ip in port.fixed_ips
                if fixed_ip.subnet_id != subnet_id]
            for subnet_id in extra_subnets:
                port = self.network_driver.unplug_fixed_ip(
                    port_id=interface.port_id, subnet_id=subnet_id)
            self._fill_port_info(port)
            updated_ports[port.network_id] = port.to_dict(recurse=True)

        for update in delta.get(constants.ADD_SUBNETS, []):
            network_id = update[constants.NETWORK_ID]
            # Get already existing port from Deltas or
            # newly created port from updated_ports dict
            port_id = (update[constants.PORT_ID] or
                       updated_ports[network_id][constants.ID])
            subnet_id = update[constants.SUBNET_ID]
            # Avoid duplicated subnets
            has_subnet = False
            if network_id in updated_ports:
                has_subnet = any(
                    fixed_ip[constants.SUBNET_ID] == subnet_id
                    for fixed_ip in updated_ports[network_id][
                        constants.FIXED_IPS])
            if not has_subnet:
                port = self.network_driver.plug_fixed_ip(
                    port_id=port_id, subnet_id=subnet_id)
                self._fill_port_info(port)
                updated_ports[network_id] = (
                    port.to_dict(recurse=True))

        for update in delta.get(constants.DELETE_SUBNETS, []):
            network_id = update[constants.NETWORK_ID]
            port_id = update[constants.PORT_ID]
            subnet_id = update[constants.SUBNET_ID]
            port = self.network_driver.unplug_fixed_ip(
                port_id=port_id, subnet_id=subnet_id)
            self._fill_port_info(port)
            # In neutron, when removing an ipv6 subnet (with slaac) from a
            # port, it just ignores it.
            # https://bugs.launchpad.net/neutron/+bug/1945156
            # When it happens, don't add the port to the updated_ports dict
            has_subnet = any(
                fixed_ip.subnet_id == subnet_id
                for fixed_ip in port.fixed_ips)
            if not has_subnet:
                updated_ports[network_id] = (
                    port.to_dict(recurse=True))

        for nic in delta[constants.DELETE_NICS]:
            network_id = nic[constants.NETWORK_ID]
            try:
                LOG.debug("[NetIF] unplug_network %s on %s", network_id, db_amp.compute_id)
                self.network_driver.unplug_network(
                    db_amp.compute_id, network_id)
            except base.NetworkNotFound:
                LOG.debug("Network %s not found", network_id)
            except Exception:
                LOG.exception("Unable to unplug network")

            port_id = nic[constants.PORT_ID]
            try:
                self.network_driver.delete_port(port_id)
            except Exception:
                LOG.exception("Unable to delete the port")

            updated_ports.pop(network_id, None)
        return {amphora[constants.ID]: list(updated_ports.values())}

    def revert(self, result, amphora, delta, *args, **kwargs):
        """Handle a network plug or unplug failures."""

        if isinstance(result, failure.Failure):
            return

        if not delta:
            return

        LOG.warning("Unable to plug networks for amp id %s",
                    delta['amphora_id'])

        for nic in delta[constants.ADD_NICS]:
            try:
                self.network_driver.unplug_network(delta[constants.COMPUTE_ID],
                                                   nic[constants.NETWORK_ID])
            except Exception:
                LOG.exception("Unable to unplug network %s",
                              nic[constants.NETWORK_ID])

            port_id = nic[constants.PORT_ID]
            try:
                self.network_driver.delete_port(port_id)
            except Exception:
                LOG.exception("Unable to delete port %s", port_id)


class HandleNetworkDeltas(BaseNetworkTask):
    """Task to plug and unplug networks

    Loop through the deltas and plug or unplug
    networks based on delta
    """

    def execute(self, deltas, loadbalancer):
        """Handle network plugging based off deltas."""
        # added_ports = {}
        # for amp_id, delta in six.iteritems(deltas):
        #     added_ports[amp_id] = []
        #     for nic in delta.add_nics:
        #         LOG.debug("[NetIF] plug_network %s on %s", nic.network_id, delta.compute_id)
        #         interface = self.network_driver.plug_network(delta.compute_id,
        #                                                      nic.network_id)
        #         port = self.network_driver.get_port(interface.port_id)
        #         port.network = self.network_driver.get_network(port.network_id)
        #         for fixed_ip in port.fixed_ips:
        #             fixed_ip.subnet = self.network_driver.get_subnet(
        #                 fixed_ip.subnet_id)
        #         added_ports[amp_id].append(port)
        #     for nic in delta.delete_nics:
        #         try:
        #             LOG.debug("[NetIF] unplug_network %s on %s", nic.network_id, delta.compute_id)
        #             self.network_driver.unplug_network(delta.compute_id,
        #                                                nic.network_id)
        #             **network = self.network_driver.get_network(nic.network_id)
        #             **added_ports[amp_id].append(network)
        #         except base.NetworkNotFound:
        #             LOG.debug("Network %d not found ", nic.network_id)
        #         except Exception as e:
        #             LOG.exception(
        #                 "Unable to unplug network due to: %s", str(e))
        #             raise e
        # return added_ports
        session = db_apis.get_session()
        with session.begin():
            db_lb = self.loadbalancer_repo.get(
                session, id=loadbalancer[constants.LOADBALANCER_ID])
        amphorae = {amp.id: amp for amp in db_lb.amphorae}

        updated_ports = {}
        handle_delta = HandleNetworkDelta()

        for amp_id, delta in six.iteritems(deltas):
            ret = handle_delta.execute(amphorae[amp_id].to_dict(), delta)
            updated_ports.update(ret)

        return updated_ports

    def revert(self, result, deltas, *args, **kwargs):
        """Handle a network plug or unplug failures."""

        if isinstance(result, failure.Failure):
            return

        if not deltas:
            return

        for amp_id, delta in six.iteritems(deltas):
            LOG.warning("Unable to plug networks for amp id %s",
                        delta[constants.AMPHORA_ID])

            for nic in delta[constants.ADD_NICS]:
                try:
                    self.network_driver.unplug_network(delta[constants.COMPUTE_ID],
                                                       nic[constants.NETWORK_ID])
                except Exception:
                    LOG.exception("Unable to unplug network %s",
                                  nic[constants.NETWORK_ID])

                port_id = nic[constants.PORT_ID]
                try:
                    self.network_driver.delete_port(port_id)
                except Exception:
                    LOG.exception("Unable to delete port %s", port_id)


#class PlugVIP(BaseNetworkTask):
#    """Task to plumb a VIP."""
#
#     def execute(self, loadbalancer):
#         """Plumb a vip to an amphora."""
# 
#         LOG.debug("Plumbing VIP for loadbalancer id: %s", loadbalancer.id)
#         amps_data = self.network_driver.plug_vip(loadbalancer,
#                                                  loadbalancer.vip)
#         return amps_data
# 
#     def revert(self, result, loadbalancer, *args, **kwargs):
#         """Handle a failure to plumb a vip."""
# 
#         if isinstance(result, failure.Failure):
#             return
#         LOG.warning("Unable to plug VIP for loadbalancer id %s",
#                     loadbalancer.id)
# 
#         try:
#             # Make sure we have the current port IDs for cleanup
#             for amp_data in result:
#                 for amphora in six.moves.filter(
#                         # pylint: disable=cell-var-from-loop
#                         lambda amp: amp.id == amp_data.id,
#                         loadbalancer.amphorae):
#                     amphora.vrrp_port_id = amp_data.vrrp_port_id
#                     amphora.ha_port_id = amp_data.ha_port_id
# 
#             self.network_driver.unplug_vip_revert(loadbalancer, loadbalancer.vip)
#         except Exception as e:
#             LOG.error("Failed to unplug VIP.  Resources may still "
#                       "be in use from vip: %(vip)s due to error: %(except)s",
#                       {'vip': loadbalancer.vip.ip_address, 'except': e})


class UpdateVIPSecurityGroup(BaseNetworkTask):
    """Task to setup SG for LB."""

    def execute(self, loadbalancer):
        """Task to setup SG for LB."""

        LOG.debug("Setup SG for loadbalancer id: %s", loadbalancer[constants.LOADBALANCER_ID])

        session = db_apis.get_session()
        with session.begin():
            db_lb = self.loadbalancer_repo.get(
                session, id=loadbalancer[constants.LOADBALANCER_ID])

        #self.network_driver.update_vip_sg(loadbalancer, loadbalancer.vip)
        sg_id = self.network_driver.update_vip_sg(db_lb, db_lb.vip)
        LOG.info("Set up VIP SG %s for load balancer %s complete",
                 sg_id if sg_id else "None", loadbalancer[constants.LOADBALANCER_ID])
        return sg_id


class GetSubnetFromVIP(BaseNetworkTask):
    """Task to plumb a VIP."""

    def execute(self, loadbalancer):
        """Plumb a vip to an amphora."""

        # LOG.debug("Getting subnet for LB: %s", loadbalancer.id)

        # return self.network_driver.get_subnet(loadbalancer.vip.subnet_id)
        LOG.debug("Getting subnet for LB: %s",
                  loadbalancer[constants.LOADBALANCER_ID])

        subnet = self.network_driver.get_subnet(loadbalancer['vip_subnet_id'])
        LOG.info("Got subnet %s for load balancer %s",
                 loadbalancer['vip_subnet_id'] if subnet else "None",
                 loadbalancer[constants.LOADBALANCER_ID])
        return subnet.to_dict()


class PlugVIPAmphora(BaseNetworkTask):
    """Task to plumb a VIP."""

    def execute(self, loadbalancer, amphora, subnet):
        """Plumb a vip to an amphora."""

        # LOG.debug("Plumbing VIP for amphora id: %s", amphora.id)

        # amp_data = self.network_driver.plug_aap_port(
        #     loadbalancer, loadbalancer.vip, amphora, subnet)
        # return amp_data
        amps_data = []
        session = db_apis.get_session()
        with session.begin():
            for amphora in filter(
                lambda amp: amp[constants.STATUS] == constants.AMPHORA_ALLOCATED,
                    amphora):
                LOG.debug("Plumbing VIP for amphora id: %s",
                  amphora[constants.ID])
                db_amp = self.amphora_repo.get(session,
                                            id=amphora[constants.ID])
                db_subnet = self.network_driver.get_subnet(subnet.id)
                db_lb = self.loadbalancer_repo.get(
                    session, id=loadbalancer[constants.LOADBALANCER_ID])
                amps_data.append(self.network_driver.plug_aap_port(
                    db_lb, db_lb.vip, db_amp, db_subnet).to_dict())
        return amps_data

    def revert(self, result, loadbalancer, amphora, subnet, *args, **kwargs):
        """Handle a failure to plumb a vip."""

        if isinstance(result, failure.Failure):
            return
        lb_id = loadbalancer[constants.LOADBALANCER_ID]
        LOG.warning("Unable to plug VIP for amphora id %s "
                    "load balancer id %s",
                    amphora[0].get(constants.ID), lb_id)

        # try:
        #     amphora.vrrp_port_id = result.vrrp_port_id
        #     amphora.ha_port_id = result.ha_port_id

        #     self.network_driver.unplug_aap_port(loadbalancer.vip,
        #                                         amphora, subnet)
        # except Exception as e:
        #     LOG.error('Failed to unplug AAP port. Resources may still be in '
        #               'use for VIP: %s due to error: %s', loadbalancer.vip, e)
        try:
            session = db_apis.get_session()
            with session.begin():
                db_amp = self.amphora_repo.get(session,
                                               id=amphora.get(constants.ID))
                db_amp.vrrp_port_id = result[constants.VRRP_PORT_ID]
                db_amp.ha_port_id = result[constants.HA_PORT_ID]
                db_subnet = self.network_driver.get_subnet(
                    subnet[constants.ID])
                db_lb = self.loadbalancer_repo.get(session, id=lb_id)
            self.network_driver.unplug_aap_port(db_lb.vip,
                                                db_amp, db_subnet)
        except Exception as e:
            LOG.error(
                'Failed to unplug AAP port for load balancer: %s. '
                'Resources may still be in use for VRRP port: %s. '
                'Due to error: %s',
                lb_id, result, str(e)
            )


class UnplugVIP(BaseNetworkTask):
    """Task to unplug the vip."""

    def execute(self, loadbalancer):
        """Unplug the vip."""

        LOG.debug("Unplug vip on amphora")
        try:
            session = db_apis.get_session()
            with session.begin():
                db_lb = self.loadbalancer_repo.get(
                    session,
                    id=loadbalancer[constants.LOADBALANCER_ID])
            self.network_driver.unplug_vip(db_lb, db_lb.vip)
        except Exception:
            LOG.exception("Unable to unplug vip from load balancer %s",
                          loadbalancer[constants.LOADBALANCER_ID])


class AllocateVIP(BaseNetworkTask):
    """Task to allocate a VIP."""

    def execute(self, loadbalancer, lb_count_subnet):

        """Allocate a vip to the loadbalancer."""
        # LOG.debug("Allocate_vip port_id %s, subnet_id %s,"
        #           "ip_address %s",
        #           loadbalancer.vip.port_id,
        #           loadbalancer.vip.subnet_id,
        #           loadbalancer.vip.ip_address)
        # return self.network_driver.allocate_vip(loadbalancer)
        LOG.debug("Allocating vip with port id %s, subnet id %s, "
                  "ip address %s for load balancer %s",
                  loadbalancer[constants.VIP_PORT_ID],
                  loadbalancer[constants.VIP_SUBNET_ID],
                  loadbalancer[constants.VIP_ADDRESS],
                  loadbalancer[constants.LOADBALANCER_ID])
        session = db_apis.get_session()
        with session.begin():
            db_lb = self.loadbalancer_repo.get(
                session, id=loadbalancer[constants.LOADBALANCER_ID])
        vip, additional_vips = self.network_driver.allocate_vip(db_lb)
        LOG.info("Allocated vip with port id %s, subnet id %s, ip address %s "
                 "for load balancer %s",
                 loadbalancer[constants.VIP_PORT_ID],
                 loadbalancer[constants.VIP_SUBNET_ID],
                 loadbalancer[constants.VIP_ADDRESS],
                 loadbalancer[constants.LOADBALANCER_ID])
        # for add_vip in additional_vips:
        #     LOG.debug('Allocated an additional VIP: subnet=%(subnet)s '
        #               'ip_address=%(ip)s', {'subnet': add_vip.subnet_id,
        #                                     'ip': add_vip.ip_address})
        return vip.to_dict()

    def revert(self, result, loadbalancer, lb_count_subnet, *args, **kwargs):
        """Handle a failure to allocate vip."""

        if isinstance(result, failure.Failure):
            LOG.exception("Unable to allocate VIP")
            return
        vip = result
        vip = o_data_models.Vip(**vip)
        LOG.warning("Deallocating vip %s", vip.ip_address)
        try:
            self.network_driver.deallocate_vip(vip, lb_count_subnet)
        except Exception as e:
            LOG.error("Failed to deallocate VIP.  Resources may still "
                      "be in use from vip: %(vip)s due to error: %(except)s",
                      {'vip': vip.ip_address, 'except': e})


class DeallocateVIP(BaseNetworkTask):
    """Task to deallocate a VIP."""

    def execute(self, loadbalancer, lb_count_subnet):
        """Deallocate a VIP."""
        LOG.debug("Deallocating a VIP %s", loadbalancer[constants.VIP_ADDRESS])
        try:
            session = db_apis.get_session()
            with session.begin():
                db_lb = self.loadbalancer_repo.get(
                    session, id=loadbalancer[constants.LOADBALANCER_ID])
            self.network_driver.deallocate_vip(db_lb, lb_count_subnet)
        except Exception as e:
            LOG.error("Failed to deallocate VIP.  Resources may still "
                      "be in use from vip: %(vip)s due to error: %(except)s",
                      {'vip': loadbalancer.get(constants.VIP_ADDRESS) or (loadbalancer.get(constants.VIP) or {}).get(constants.IP_ADDRESS), 'except': e})


class UpdateVIP(BaseNetworkTask):
    """Task to update a VIP."""

    def execute(self, loadbalancer):
        session = db_apis.get_session()
        with session.begin():
            loadbalancer = self.loadbalancer_repo.get(
                session, id=loadbalancer[constants.LOADBALANCER_ID])
        LOG.debug("Updating VIP of load_balancer %s.", loadbalancer.id)
        self.network_driver.update_vip(loadbalancer)


class UpdateVIPForDelete(BaseNetworkTask):
    """Task to update a VIP for listener delete flows."""

    def execute(self, loadbalancer_id):
        session = db_apis.get_session()
        with session.begin():
            loadbalancer = self.loadbalancer_repo.get(
                session, id=loadbalancer_id)
        LOG.debug("Updating VIP for listener delete on load_balancer %s.",
                  loadbalancer.id)

        try:
            self.network_driver.update_vip(loadbalancer, for_delete=True)
        except Exception as e:
            LOG.error("Failed to update vip error: %s", str(e))


class GetAmphoraNetworkConfigs(BaseNetworkTask):
    """Task to retrieve amphora network details."""

    def execute(self, loadbalancer, amphora=None):
        LOG.debug("Retrieving vip network details.")
        # return self.network_driver.get_network_configs(loadbalancer,
        #                                                amphora=amphora)
        session = db_apis.get_session()
        with session.begin():
            db_amp = self.amphora_repo.get(session,
                                           id=amphora.get(constants.ID))
            db_lb = self.loadbalancer_repo.get(
                session, id=loadbalancer[constants.LOADBALANCER_ID])
        db_configs = self.network_driver.get_network_configs(
            db_lb, amphora=db_amp)
        provider_dict = {}
        for amp_id, amp_conf in db_configs.items():
            provider_dict[amp_id] = amp_conf.to_dict(recurse=True)
        return provider_dict


class GetAmphoraeNetworkConfigs(BaseNetworkTask):
    """Task to retrieve amphorae network details."""

    def execute(self, loadbalancer):
        LOG.debug("Retrieving vip network details.")
        #return self.network_driver.get_network_configs(loadbalancer)
        session = db_apis.get_session()
        with session.begin():
            db_lb = self.loadbalancer_repo.get(
                session, id=loadbalancer[constants.LOADBALANCER_ID])
        db_configs = self.network_driver.get_network_configs(db_lb)
        provider_dict = {}
        for amp_id, amp_conf in db_configs.items():
            provider_dict[amp_id] = amp_conf.to_dict(recurse=True)
        return provider_dict


# class FailoverPreparationForAmphora(BaseNetworkTask):
#     """Task to prepare an amphora for failover."""

#     def execute(self, amphora):
#         LOG.debug("Prepare amphora %s for failover.", amphora.id)

#         self.network_driver.failover_preparation(amphora)


class RetrievePortIDsOnAmphoraExceptLBNetwork(BaseNetworkTask):
    """Task retrieving all the port ids on an amphora, except lb network."""

    def execute(self, amphora):
        LOG.debug("Retrieve all but the lb network port id on amphora %s.",
                  amphora[constants.ID])

        interfaces = self.network_driver.get_plugged_networks(
            compute_id=amphora[constants.COMPUTE_ID])

        ports = []
        for interface_ in interfaces:
            if interface_.port_id not in ports:
                port = self.network_driver.get_port(port_id=interface_.port_id)
                ips = port.fixed_ips
                lb_network = False
                for ip in ips:
                    if ip.ip_address == amphora[constants.LB_NETWORK_IP]:
                        lb_network = True
                if not lb_network:
                    ports.append(port)

        return ports


class PlugPorts(BaseNetworkTask):
    """Task to plug neutron ports into a compute instance."""

    def execute(self, amphora, ports):
        session = db_apis.get_session()
        with session.begin():
            db_amp = self.amphora_repo.get(session,
                                           id=amphora[constants.ID])
        for port in ports:
            LOG.debug('Plugging port ID: %(port_id)s into compute instance: '
                      '%(compute_id)s.',
                      {constants.PORT_ID: port.id,
                       constants.COMPUTE_ID: amphora[constants.COMPUTE_ID]})
            self.network_driver.plug_port(db_amp, port)


class PlugVIPPort(BaseNetworkTask):
    """Task to plug a VIP into a compute instance."""

    def execute(self, amphora, amphorae_network_config):
        vrrp_port = amphorae_network_config.get(amphora[constants.ID]).vrrp_port
        LOG.debug('Plugging VIP VRRP port ID: %(port_id)s into compute '
                  'instance: %(compute_id)s.',
                  {'port_id': vrrp_port.id, 'compute_id': amphora[constants.COMPUTE_ID]})
        self.network_driver.plug_port(amphora, vrrp_port)

    def revert(self, result, amphora, amphorae_network_config,
               *args, **kwargs):
        vrrp_port = None
        try:
            vrrp_port = amphorae_network_config.get(amphora.id).vrrp_port
            self.network_driver.unplug_port(amphora, vrrp_port)
        except Exception:
            LOG.warning('Failed to unplug vrrp port: %(port)s from amphora: '
                        '%(amp)s', {'port': vrrp_port.id, 'amp': amphora.id})


class WaitForPortDetach(BaseNetworkTask):
    """Task to wait for the neutron ports to detach from an amphora."""

    def execute(self, amphora):
        LOG.debug('Waiting for ports to detach from amphora: %(amp_id)s.',
                  {'amp_id': amphora[constants.ID]})
        self.network_driver.wait_for_port_detach(amphora)


class ApplyQos(BaseNetworkTask):
    """Apply Quality of Services to the VIP"""

    def _apply_qos_on_vrrp_ports(self, loadbalancer, amps_data, qos_policy_id,
                                 is_revert=False, request_qos_id=None):
        """Call network driver to apply QoS Policy on the vrrp ports."""
        session = db_apis.get_session()
        with session.begin():
            if not amps_data:
                db_lb = self.loadbalancer_repo.get(
                    session,
                    id=loadbalancer[constants.LOADBALANCER_ID])
                amps_data = db_lb.amphorae

        apply_qos = ApplyQosAmphora()
        for amp_data in amps_data:
            apply_qos._apply_qos_on_vrrp_port(loadbalancer, amp_data.to_dict(),
                                              qos_policy_id)

    def execute(self, loadbalancer, amps_data=None, update_dict=None):
        """Apply qos policy on the vrrp ports which are related with vip."""
        session = db_apis.get_session()
        with session.begin():
            db_lb = self.loadbalancer_repo.get(
                session,
                id=loadbalancer[constants.LOADBALANCER_ID])

        qos_policy_id = db_lb.vip.qos_policy_id
        if not qos_policy_id and (
            update_dict and (
                'vip' not in update_dict or
                'qos_policy_id' not in update_dict[constants.VIP])):
            return
        if update_dict and update_dict.get(constants.VIP):
            vip_dict = update_dict[constants.VIP]
            if vip_dict.get(constants.QOS_POLICY_ID):
                qos_policy_id = vip_dict[constants.QOS_POLICY_ID]

        self._apply_qos_on_vrrp_ports(loadbalancer, amps_data, qos_policy_id)

    def revert(self, result, loadbalancer, amps_data=None, update_dict=None,
               *args, **kwargs):
        """Handle a failure to apply QoS to VIP"""
        try:
            request_qos_id = loadbalancer['vip_qos_policy_id']
            orig_lb = self.task_utils.get_current_loadbalancer_from_db(
                loadbalancer[constants.LOADBALANCER_ID])
            orig_qos_id = orig_lb.vip.qos_policy_id
            if request_qos_id != orig_qos_id:
                self._apply_qos_on_vrrp_ports(loadbalancer, amps_data, orig_qos_id,
                                              is_revert=True,
                                              request_qos_id=request_qos_id)
        except Exception:
            LOG.exception("Error for Apply qos policy on the vrrp ports")
        return


class ApplyQosAmphora(BaseNetworkTask):
    """Apply Quality of Services to the VIP"""

    def _apply_qos_on_vrrp_port(self, loadbalancer, amp_data, qos_policy_id,
                                is_revert=False, request_qos_id=None):
        """Call network driver to apply QoS Policy on the vrrp ports."""
        try:
            self.network_driver.apply_qos_on_port(
                qos_policy_id,
                amp_data[constants.VRRP_PORT_ID])
        except Exception:
            if not is_revert:
                raise
            else:
                LOG.warning('Failed to undo qos policy %(qos_id)s '
                            'on vrrp port: %(port)s from '
                            'amphorae: %(amp)s',
                            {'qos_id': request_qos_id,
                             'port': amp_data[constants.VRRP_PORT_ID],
                             'amp': [amp.get(constants.ID) for amp in amp_data]})

    def execute(self, loadbalancer, amp_data=None, update_dict=None):
        """Apply qos policy on the vrrp ports which are related with vip."""
        qos_policy_id = loadbalancer['vip_qos_policy_id']
        if not qos_policy_id and (
            update_dict and (
                'vip' not in update_dict or
                'qos_policy_id' not in update_dict[constants.VIP])):
            return
        self._apply_qos_on_vrrp_port(loadbalancer, amp_data, qos_policy_id)

    def revert(self, result, loadbalancer, amp_data=None, update_dict=None,
               *args, **kwargs):
        """Handle a failure to apply QoS to VIP"""
        try:
            request_qos_id = loadbalancer['vip_qos_policy_id']
            orig_lb = self.task_utils.get_current_loadbalancer_from_db(
                loadbalancer[constants.LOADBALANCER_ID])
            orig_qos_id = orig_lb.vip.qos_policy_id
            if request_qos_id != orig_qos_id:
                self._apply_qos_on_vrrp_port(loadbalancer, amp_data,
                                             orig_qos_id, is_revert=True,
                                             request_qos_id=request_qos_id)
        except Exception as e:
            LOG.error('Failed to remove QoS policy: %s from port: %s due '
                      'to error: %s', orig_qos_id, amp_data[constants.VRRP_PORT_ID], e)


class HandleVRIDFloatingIP(BaseNetworkTask):
    """Handle VRID floating IP configurations for loadbalancer resourse"""

    def __init__(self, *arg, **kwargs):
        self.added_fip_ports = []
        super(HandleVRIDFloatingIP, self).__init__(*arg, **kwargs)

    def _add_vrid_to_list(self, vrid_list, subnet, owner):
        vrid_value = CONF.a10_global.vrid
        subnet_ids = set([s.id for s in subnet]) if isinstance(subnet, list) else [subnet.id]
        for subnet_id in subnet_ids:
            LOG.debug("Creating new VRID entry for subnet_id: %s", subnet_id)
            filtered_vrid_list = list(filter(lambda x: x.subnet_id == subnet_id, vrid_list))
            if not filtered_vrid_list:
                vrid_list.append(data_models.VRID(
                    id=uuidutils.generate_uuid(),
                    vrid=vrid_value,
                    owner=owner,
                    vrid_port_id=None,
                    vrid_floating_ip=None,
                    subnet_id=subnet_id))

    def _remove_device_vrid_fip(self, partition_name, vrid_value):
        try:
            is_partition = (partition_name is not None and partition_name != 'shared')
            self.axapi_client.vrrpa.update(vrid_value, floating_ips=[], is_partition=is_partition)
        except (acos_errors.ACOSException, req_exceptions.ConnectionError) as e:
            LOG.exception("Failed to remove VRRP floating IPs for vrid: %s",
                          str(vrid_value))
            raise e

    def _update_device_vrid_fip(self, partition_name, vrid_floating_ip_list, vrid_value):
        try:
            is_partition = (partition_name is not None and partition_name != 'shared')
            self.axapi_client.vrrpa.update(
                vrid_value, floating_ips=vrid_floating_ip_list, is_partition=is_partition)
        except (acos_errors.ACOSException, req_exceptions.ConnectionError) as e:
            LOG.exception("Failed to update VRRP floating IP %s for vrid: %s",
                          vrid_floating_ip_list, str(vrid_value))
            raise e

    def _delete_vrid_port(self, vrid_port_id):
        try:
            self.network_driver.delete_port(vrid_port_id)
        except Exception as e:
            LOG.error("Failed to delete neutron port for VRID port: %s",
                      vrid_port_id)
            raise e

    def _replace_vrid_port(self, vrid, subnet, lb_resource, conf_floating_ip=None):
        if vrid.vrid_port_id:
            self._delete_vrid_port(vrid.vrid_port_id)

        try:
            amphorae = a10_task_utils.attribute_search(lb_resource, 'amphorae')
            fip_obj = self.network_driver.allocate_vrid_fip(
                vrid, subnet.network_id, amphorae,
                fixed_ip=conf_floating_ip)
            vrid.vrid_port_id = fip_obj.id
            vrid.vrid_floating_ip = fip_obj.fixed_ips[0].ip_address
            self.added_fip_ports.append(fip_obj)
        except Exception as e:
            msg = "Failed to create neutron port for SLB resource: %s "
            if conf_floating_ip:
                msg += "with floating IP {}".format(conf_floating_ip)
            LOG.error(msg, lb_resource[constants.LOADBALANCER_ID])
            raise e
        return vrid

    @axapi_client_decorator
    def execute(self, vthunder, lb_resource, vrid_list, subnet,
                vthunder_config, use_device_flavor=False):
        """
        :param vthunder:
        :param lb_resource: Can accept LB or member
        :param vrid_list: VRID object list for LB resource's project.
        :param subnet: subnet of the resource in question, will be helpful if there is no
        VRID object present for the provided subnet then is should create new VRID
        floating IP instead of updating existing(delete + create -> update)

        :return: return the update list of VRID object, If empty the need to remove all VRID
        objects from DB else need update existing ones.
        """
        updated_vrid_list = []
        if not subnet:
            LOG.warning("No subnet provided to HandleVRIDFloatingIP; skipping task.")
            return updated_vrid_list
        vrid_value = CONF.a10_global.vrid
        prev_vrid_value = vrid_list[0].vrid if vrid_list else None
        updated_vrid_list = copy.copy(vrid_list)
        if use_device_flavor:
            if vthunder_config.vrid_floating_ip:
                conf_floating_ip = vthunder_config.vrid_floating_ip
            else:
                conf_floating_ip = CONF.a10_global.vrid_floating_ip
        else:
            project_id = lb_resource.get(constants.PROJECT_ID)
            if not project_id:
                raise Exception("PROJECT_ID not found in lb_resource")
            conf_floating_ip = a10_utils.get_vrid_floating_ip_for_project(project_id)

        if not conf_floating_ip:
            for vrid in updated_vrid_list:
                self._delete_vrid_port(vrid.vrid_port_id)
            vrid_value = prev_vrid_value if prev_vrid_value else vrid_value
            self._remove_device_vrid_fip(vthunder.partition_name, vrid_value)
            return []

        vrid_floating_ips = []
        update_vrid_flag = False
        existing_fips = []
        owner = vthunder.ip_address + "_" + vthunder.partition_name
        self._add_vrid_to_list(updated_vrid_list, subnet, owner)
        for vrid in updated_vrid_list:
            vrid_subnet = self.network_driver.get_subnet(vrid.subnet_id)
            try:
                vrid_summary = self.axapi_client.vrrpa.get(vrid.vrid)
            except Exception as e:
                vrid_summary = {}
                LOG.exception("Failed to get existing VRID summary due to: %s", str(e))

            if vrid_summary and 'floating-ip' in vrid_summary['vrid']:
                vrid_fip = vrid_summary['vrid']['floating-ip']
                if vthunder.partition_name != 'shared':
                    if vrid_fip.get(a10constants.IP_ADDRESS_PARTITION_CFG):
                        for i in range(len(vrid_fip[a10constants.IP_ADDRESS_PARTITION_CFG])):
                            existing_fips.append(
                                vrid_fip[a10constants.IP_ADDRESS_PARTITION_CFG][i]
                                        [a10constants.IP_ADDRESS_PARTITION])
                    else:
                        for i in range(len(vrid_fip[a10constants.IPV6_ADDRESS_PARTITION_CFG])):
                            existing_fips.append(
                                vrid_fip[a10constants.IPV6_ADDRESS_PARTITION_CFG][i]
                                        [a10constants.IPV6_ADDRESS_PARTITION])

                else:
                    if vrid_fip.get(a10constants.IP_ADDRESS_CFG):
                        for i in range(len(vrid_fip[a10constants.IP_ADDRESS_CFG])):
                            existing_fips.append(
                                vrid_fip[a10constants.IP_ADDRESS_CFG][i][a10constants.IP_ADDRESS])
                    if vrid_fip.get(a10constants.IPV6_ADDRESS_CFG):
                        for i in range(len(vrid_fip[a10constants.IPV6_ADDRESS_CFG])):
                            existing_fips.append(
                                vrid_fip[a10constants.IPV6_ADDRESS_CFG][i]
                                        [a10constants.IPV6_ADDRESS])

            vrid.vrid = vrid_value
            if conf_floating_ip.lower() == 'dhcp':
                subnet_ip, subnet_mask = a10_utils.get_net_info_from_cidr(
                    vrid_subnet.cidr, vrid_subnet.ip_version)
                if not a10_utils.check_ip_in_subnet_range(vrid.vrid_floating_ip, subnet_ip,
                                                          subnet_mask, vrid_subnet.ip_version,
                                                          vrid_subnet.cidr):
                    vrid = self._replace_vrid_port(vrid, vrid_subnet, lb_resource)
                    update_vrid_flag = True
            else:
                if vrid.vrid_floating_ip is None:
                    new_ip = a10_utils.get_patched_ip_address(
                        conf_floating_ip, vrid_subnet.cidr, vrid_subnet.ip_version)
                else:
                    new_ip = vrid.vrid_floating_ip
                if new_ip != vrid.vrid_floating_ip:
                    vrid = self._replace_vrid_port(vrid, vrid_subnet, lb_resource, new_ip)
                    update_vrid_flag = True
            if isinstance(subnet, list):
                subnet_ids = set([s.id for s in subnet])
                if vrid_subnet.id in subnet_ids or vrid.vrid_floating_ip in existing_fips:
                    vrid_floating_ips.append(vrid.vrid_floating_ip)
            else:
                if vrid_subnet.id == subnet.id or vrid.vrid_floating_ip in existing_fips:
                    vrid_floating_ips.append(vrid.vrid_floating_ip)

        if (prev_vrid_value is not None) and (prev_vrid_value != vrid_value):
            self._remove_device_vrid_fip(vthunder.partition_name, prev_vrid_value)
            self._update_device_vrid_fip(vthunder.partition_name, vrid_floating_ips, vrid_value)
        elif update_vrid_flag:
            self._update_device_vrid_fip(vthunder.partition_name, vrid_floating_ips, vrid_value)

        return updated_vrid_list

    @axapi_client_decorator
    def revert(self, result, vthunder, lb_resource, vrid_list, subnet, *args, **kwargs):
        lb_id = lb_resource.get('id') if isinstance(lb_resource, dict) else getattr(lb_resource, 'id', 'unknown')
        LOG.warning("Reverting VRRP floating IP delta task for lb_resource %s", lb_id)
        # Delete newly added ports
        for port in self.added_fip_ports:
            try:
                self.network_driver.delete_port(port.id)
            except Exception as e:
                LOG.error(
                    "Failed to delete port %s due to %s",
                    port.id,
                    str(e))

        vrid_floating_ip_list = [ip for ip in (vrid.vrid_floating_ip for vrid in vrid_list) if ip]

        if isinstance(vrid_floating_ip_list, list):
            vrid_value = CONF.a10_global.vrid
            try:
                self._update_device_vrid_fip(
                    vthunder.partition_name, vrid_floating_ip_list, vrid_value)
            except Exception as e:
                LOG.error("Failed to update VRID floating IPs %s due to %s",
                          vrid_floating_ip_list, str(e))


class DeleteVRIDPort(BaseNetworkTask):

    """Delete VRID Port if the last resource associated with it is deleted"""

    @axapi_client_decorator
    def execute(self, vthunder, vrid_list, subnet,
                use_device_flavor, lb_count_subnet, member_count,
                lb_count_thunder, member_count_thunder, lb_resource):
        if not subnet:
            return None, False
        vrid = None
        vrid_floating_ip_list = []
        existing_fips = []
        if use_device_flavor:
            resource_count = lb_count_thunder + member_count_thunder
        else:
            resource_count = lb_count_subnet + member_count
        if resource_count <= 1 and vthunder:
            partition = vthunder.partition_name
            for vr in vrid_list:
                vr_subnet = self.network_driver.get_subnet(vr.subnet_id)
                IP_addr, IP_addr_cfg = a10_utils.get_acos_parameter_for_vrid(vr_subnet.ip_version,
                                                                             partition)
                try:
                    vrid_summary = self.axapi_client.vrrpa.get(vr.vrid)
                except Exception as e:
                    vrid_summary = {}
                    LOG.exception("Failed to get existing VRID summary due to: %s", str(e))

                if vrid_summary and 'floating-ip' in vrid_summary['vrid']:
                    vrid_fip = vrid_summary['vrid']['floating-ip']
                    if vthunder.partition_name != 'shared':
                        for i in range(len(vrid_fip[IP_addr_cfg])):
                            existing_fips.append(
                                vrid_fip[IP_addr_cfg][i][IP_addr])
                    else:
                        for i in range(len(vrid_fip[IP_addr_cfg])):
                            existing_fips.append(vrid_fip[IP_addr_cfg][i][IP_addr])
                if vr.subnet_id == subnet.id:
                    vrid = vr
                elif vr.vrid_floating_ip in existing_fips:
                    vrid_floating_ip_list.append(vr.vrid_floating_ip)
            if vrid:
                try:
                    amphorae = a10_task_utils.attribute_search(lb_resource, 'amphorae')
                    self.network_driver.deallocate_vrid_fip(vrid, subnet, amphorae)
                    if not vthunder.partition_name or vthunder.partition_name == 'shared':
                        self.axapi_client.vrrpa.update(
                            vrid.vrid, floating_ips=vrid_floating_ip_list)
                    else:
                        self.axapi_client.vrrpa.update(
                            vrid.vrid, floating_ips=vrid_floating_ip_list, is_partition=True)
                    LOG.info(
                        "VRID floating IP: %s deleted",
                        vrid.vrid_floating_ip)
                    return vrid, True
                except Exception as e:
                    LOG.exception(
                        "Failed to delete vrid floating ip : %s", str(e))
                    raise e
        return None, False


class DeleteMultipleVRIDPort(BaseNetworkTask):
    @axapi_client_decorator
    def execute(self, vthunder, vrid_list, subnet_list, lb_resource):
        try:
            if subnet_list and vthunder and vrid_list:
                amphorae = a10_task_utils.attribute_search(lb_resource, 'amphorae')
                vrids = []
                vrid_floating_ip_list = []
                existing_fips = []
                partition = vthunder.partition_name
                for vrid in vrid_list:
                    try:
                        vrid_summary = self.axapi_client.vrrpa.get(vrid.vrid)
                    except Exception as e:
                        vrid_summary = {}
                        LOG.exception("Failed to get existing VRID summary due to: %s", str(e))

                    subnet = self.network_driver.get_subnet(vrid.subnet_id)
                    IP_addr, IP_addr_cfg = a10_utils.get_acos_parameter_for_vrid(subnet.ip_version,
                                                                                 partition)
                    if vrid_summary and 'floating-ip' in vrid_summary['vrid']:
                        vrid_fip = vrid_summary['vrid']['floating-ip']
                        if vthunder.partition_name != 'shared':
                            for i in range(len(vrid_fip[IP_addr_cfg])):
                                existing_fips.append(
                                    vrid_fip[IP_addr_cfg][i][IP_addr])
                        else:
                            for i in range(len(vrid_fip[IP_addr_cfg])):
                                existing_fips.append(vrid_fip[IP_addr_cfg][i][IP_addr])

                    subnet_matched = list(filter(lambda x: x == vrid.subnet_id,
                                          subnet_list))
                    if subnet_matched:
                        vrids.append(vrid)
                        subnet = self.network_driver.get_subnet(vrid.subnet_id)
                        self.network_driver.deallocate_vrid_fip(vrid, subnet, amphorae)
                    elif vrid.vrid_floating_ip in existing_fips:
                        vrid_floating_ip_list.append(vrid.vrid_floating_ip)
                if not vthunder.partition_name or vthunder.partition_name == 'shared':
                    self.axapi_client.vrrpa.update(
                        vrid.vrid, floating_ips=vrid_floating_ip_list)
                else:
                    self.axapi_client.vrrpa.update(
                        vrid.vrid, floating_ips=vrid_floating_ip_list, is_partition=True)
                LOG.info("VRID floating IP: %s deleted", vrid_floating_ip_list)
                return vrids
        except Exception as e:
            LOG.exception("Failed to delete vrid floating ip : %s", str(e))
            raise e


class GetSubnetVLANIDParent(object):
    """Get the Subnet VLAN_ID"""

    def get_vlan_id(self, subnet_id):
        network_id = self.network_driver.get_subnet(subnet_id).network_id
        network = self.network_driver.get_network(network_id)
        if network.provider_network_type != 'vlan':
            raise Exception()
        return network.provider_segmentation_id


class GetVipSubnetVLANID(GetSubnetVLANIDParent, BaseNetworkTask):

    default_provides = a10constants.VLAN_ID

    def execute(self, loadbalancer):
        return self.get_vlan_id(loadbalancer[constants.VIP_SUBNET_ID])


class GetMemberSubnetVLANID(GetSubnetVLANIDParent, BaseNetworkTask):

    default_provides = a10constants.VLAN_ID

    def execute(self, member):
        return self.get_vlan_id(member[constants.SUBNET_ID])


class GetLBResourceSubnet(BaseNetworkTask):
    "Provides subnet ID for LB resource"

    def execute(self, lb_resource):
        #if not hasattr(lb_resource, 'vip_subnet_id'):
        # if not lb_resource[constants.VIP_SUBNET_ID]:
            # Special case for load balancers as their vips have the subnet
            # info
        #     subnet = self.network_driver.get_subnet(lb_resource[constants.VIP_NETWORK_ID])
        # elif lb_resource[constants.VIP_SUBNET_ID]:
        #     subnet = self.network_driver.get_subnet(lb_resource[constants.VIP_SUBNET_ID])
        # else:
        #     return
        if constants.SUBNET_ID not in lb_resource:
            # Special case for load balancers as their vips have the subnet info
            vip_subnet_id = lb_resource.get(constants.VIP_SUBNET_ID) or (lb_resource.get(constants.VIP) or {}).get(constants.SUBNET_ID)
            if not vip_subnet_id:
                raise Exception("Missing vip_subnet_id in load balancer resource")
            subnet = self.network_driver.get_subnet(vip_subnet_id)
        elif lb_resource[constants.SUBNET_ID]:
            subnet = self.network_driver.get_subnet(lb_resource[constants.SUBNET_ID])
        else:
            return
        return subnet


class GetAllResourceSubnet(BaseNetworkTask):
    "Provides subnet ID for LB resources"

    def execute(self, members):
        subnet = []
        for member in members:
            if member[constants.SUBNET_ID]:
                subnet.append(self.network_driver.get_subnet(member[constants.SUBNET_ID]))
        return subnet


class ReserveSubnetAddressForMember(BaseNetworkTask):

    def execute(self, member, nat_flavor=None, nat_pool=None):
        if nat_flavor is None:
            return

        if nat_pool is None:
            try:
                addr_list = a10_utils.get_natpool_addr_list(nat_flavor)
                if not CONF.vthunder.slb_no_snat_support:
                    amphorae = a10_task_utils.attribute_search(member, 'amphorae')
                else:
                    amphorae = None
                port = self.network_driver.reserve_subnet_addresses(
                    member.subnet_id, addr_list, amphorae)
                LOG.debug("Successfully allocated addresses for nat pool %s on port %s",
                          nat_flavor['pool_name'], port.id)
                return port
            #except neutron_exceptions.InvalidIpForSubnetClient as e:
            except os_exceptions.ResourceNotFound as e:
                # The NAT pool addresses is not in member subnet, a10-octavia will allow it but
                # will not able to reserve address for it. (since we don't know the subnet)
                LOG.exception("Failed to reserve addresses in NAT pool %s from subnet %s: %s",
                              nat_flavor['pool_name'], member[constants.SUBNET_ID], str(e))
            except Exception as e:
                LOG.exception("Failed to reserve addresses in NAT pool %s from subnet %s",
                              nat_flavor['pool_name'], member[constants.SUBNET_ID])
                raise e
        return


class ReleaseSubnetAddressForMember(BaseNetworkTask):

    def execute(self, member, nat_flavor=None, nat_pool=None):
        if nat_flavor is None or nat_pool is None:
            return

        if nat_pool.member_ref_count == 1:
            try:
                self.network_driver.delete_port(nat_pool.port_id)
                if not CONF.vthunder.slb_no_snat_support:
                    addr_list = a10_utils.get_natpool_addr_list(nat_flavor)
                    amphorae = a10_task_utils.attribute_search(member, 'amphorae')
                    if amphorae is not None:
                        self.network_driver.release_subnet_addresses(
                            member[constants.SUBNET_ID], addr_list, amphorae)
            except Exception as e:
                LOG.exception("Failed to release addresses in NAT pool %s from subnet %s",
                              nat_flavor['pool_name'], member[constants.SUBNET_ID])
                raise e


class GetMembersOnThunder(BaseNetworkTask):

    @axapi_client_decorator
    def execute(self, vthunder, use_device_flavor):
        if vthunder and use_device_flavor:
            try:
                member_list = []
                members = []
                member_list = self.axapi_client.slb.server.get_all()
                if member_list:
                    for member in range(len(member_list['server-list'])):
                        members.append(member_list['server-list'][member]['host'])
                return members
            except Exception as e:
                LOG.exception("Failed to get members on the vthunder due to %s ",
                              str(e))
                raise e
        else:
            return


class GetPoolsOnThunder(BaseNetworkTask):

    @axapi_client_decorator
    def execute(self, vthunder, use_device_flavor):
        if vthunder and use_device_flavor:
            try:
                server_group_list = []
                server_groups = []
                server_group_list = self.axapi_client.slb.service_group.all()
                if server_group_list:
                    for server_group in range(len(server_group_list['service-group-list'])):
                        server_groups.append(
                            server_group_list['service-group-list'][server_group]['name'])
                return server_groups
            except Exception as e:
                LOG.exception("Failed to get pools on the vthunder due to %s ",
                              str(e))
                raise e
        else:
            return


class GetVThunderNetworkList(BaseNetworkTask):

    def execute(self, vthunder):
        try:
            nics = self.network_driver.get_plugged_networks(vthunder.compute_id)

            # in case the compute is deleted by some reason
            if not nics:
                # Since stale vthunder will switch to backup, so peer is current master
                peer = self.vthunder_repo.get_vthunder_from_lb(
                    db_apis.get_session(), vthunder.loadbalancer_id)

                # in case role switch failed
                if peer.compute_id == vthunder.compute_id:
                    peer = self.vthunder_repo.get_backup_vthunder_from_lb(
                        db_apis.get_session(), vthunder.loadbalancer_id)
                nics = self.network_driver.get_plugged_networks(peer.compute_id)

            network_ids = [nic.network_id for nic in nics]
            return network_ids
        except Exception as e:
            LOG.exception("Failed to get network list for vthunder duo to %s", str(e))
            raise e


class PlugVipNetworkOnSpare(BaseNetworkTask):
    """Task to plug vip network on spare vThunder"""

    def __init__(self, *arg, **kwargs):
        self.added_network = []
        super(PlugVipNetworkOnSpare, self).__init__(*arg, **kwargs)

    def execute(self, spare_vthunder, loadbalancer):
        if spare_vthunder:
            try:
                nics = self.network_driver.get_plugged_networks(spare_vthunder.compute_id)
                network_ids = [nic.network_id for nic in nics]
                vip_net_id = self.network_driver.get_subnet(loadbalancer['vip_subnet_id']).network_id
                if vip_net_id not in network_ids:
                    self.network_driver.plug_network(spare_vthunder.compute_id, vip_net_id)
                    self.added_network.append(vip_net_id)
            except Exception as e:
                LOG.exception("Failed to check vip subnet on spare vThunder du to %s", str(e))
            return self.added_network

    def revert(self, spare_vthunder, loadbalancer, *args, **kwargs):
        for net in self.added_network:
            try:
                self.network_driver.unplug_network(spare_vthunder.compute_id, net)
            except base.NetworkNotFound:
                pass


class ValidateSubnet(BaseNetworkTask):

    def execute(self, member):
        if member[constants.SUBNET_ID]:
            member_subnet = self.network_driver.get_subnet(member[constants.SUBNET_ID])
            subnet_ip, subnet_mask = a10_utils.get_net_info_from_cidr(member_subnet.cidr,
                                                                      member_subnet.ip_version)
            if not a10_utils.check_ip_in_subnet_range(
                    member.get('address'), subnet_ip, subnet_mask, member_subnet.ip_version,
                    member_subnet.cidr):
                raise exceptions.IPAddressNotInSubnetRangeError(
                    member.get('address'), member_subnet.cidr)
