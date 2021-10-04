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
from neutronclient.common import exceptions as neutron_exceptions
from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import uuidutils
from requests import exceptions as req_exceptions
import six
from taskflow import task
from taskflow.types import failure

from octavia.common import constants
from octavia.controller.worker import task_utils
from octavia.network import base
from octavia.network import data_models as n_data_models

from a10_octavia.common import a10constants
from a10_octavia.common import data_models
from a10_octavia.common import exceptions
from a10_octavia.common import utils as a10_utils
from a10_octavia.controller.worker.tasks.decorators import axapi_client_decorator
from a10_octavia.controller.worker.tasks import utils as a10_task_utils

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class BaseNetworkTask(task.Task):
    """Base task to load drivers common to the tasks."""

    def __init__(self, **kwargs):
        super(BaseNetworkTask, self).__init__(**kwargs)
        self._network_driver = None
        self.task_utils = task_utils.TaskUtils()

    @property
    def network_driver(self):
        if self._network_driver is None:
            self._network_driver = a10_utils.get_network_driver()
        return self._network_driver


class CalculateAmphoraDelta(BaseNetworkTask):

    default_provides = constants.DELTA

    def execute(self, loadbalancers_list, amphora):
        LOG.debug("Calculating network delta for amphora id: %s", amphora.id)
        # Figure out what networks we want
        # seed with lb network(s)

        desired_network_ids = set(CONF.a10_controller_worker.amp_boot_network_list[:])
        member_networks = []
        for loadbalancer in loadbalancers_list:
            for pool in loadbalancer.pools:
                for member in pool.members:
                    if member.subnet_id:
                        member_networks = [
                            self.network_driver.get_subnet(member.subnet_id).network_id]
                    else:
                        LOG.warning("Subnet id argument was not specified during "
                                    "issuance of create command/API call for member %s. "
                                    "Skipping interface attachment", member.id)

                desired_network_ids.update(member_networks)

        loadbalancer_networks = [
            self.network_driver.get_subnet(loadbalancer.vip.subnet_id).network_id
            for loadbalancer in loadbalancers_list
            if loadbalancer.vip.subnet_id
        ]
        desired_network_ids.update(loadbalancer_networks)
        LOG.debug("[NetIF] desired_network_ids.update{0}".format(desired_network_ids))

        nics = self.network_driver.get_plugged_networks(amphora.compute_id)
        # assume we don't have two nics in the same network
        actual_network_nics = dict((nic.network_id, nic) for nic in nics)
        LOG.debug("[NetIF] actual_network_nics {0}".format(actual_network_nics))

        del_ids = set(actual_network_nics) - desired_network_ids
        delete_nics = list(
            actual_network_nics[net_id] for net_id in del_ids)

        add_ids = desired_network_ids - set(actual_network_nics)
        add_nics = list(n_data_models.Interface(
            network_id=net_id) for net_id in add_ids)
        delta = n_data_models.Delta(
            amphora_id=amphora.id, compute_id=amphora.compute_id,
            add_nics=add_nics, delete_nics=delete_nics)
        return delta


class CalculateDelta(BaseNetworkTask):
    """Task to calculate the delta between

    the nics on the amphora and the ones
    we need. Returns a list for
    plumbing them.
    """

    default_provides = constants.DELTAS

    def execute(self, loadbalancer, loadbalancers_list):
        """Compute which NICs need to be plugged

        for the amphora to become operational.

        :param loadbalancer: the loadbalancer to calculate deltas for all
                             amphorae
        :returns: dict of octavia.network.data_models.Delta keyed off amphora
                  id
        """

        calculate_amp = CalculateAmphoraDelta()
        deltas = {}
        for amphora in six.moves.filter(
            lambda amp: amp.status == constants.AMPHORA_ALLOCATED,
                loadbalancer.amphorae):

            delta = calculate_amp.execute(loadbalancers_list, amphora)
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

        LOG.debug("Getting plumbed networks for amphora id: %s", amphora.id)

        return self.network_driver.get_plugged_networks(amphora.compute_id)


class PlugNetworks(BaseNetworkTask):
    """Task to plug the networks.

    This uses the delta to add all missing networks/nics
    """

    def execute(self, amphora, delta):
        """Update the amphora networks for the delta."""

        LOG.debug("Plug or unplug networks for amphora id: %s", amphora.id)

        if not delta:
            LOG.debug("No network deltas for amphora id: %s", amphora.id)
            return

        # add nics
        for nic in delta.add_nics:
            self.network_driver.plug_network(amphora.compute_id,
                                             nic.network_id)

    def revert(self, amphora, delta, *args, **kwargs):
        """Handle a failed network plug by removing all nics added."""

        LOG.warning("Unable to plug networks for amp id %s", amphora.id)
        if not delta:
            return

        for nic in delta.add_nics:
            try:
                self.network_driver.unplug_network(amphora.compute_id,
                                                   nic.network_id)
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
            LOG.debug("No network deltas for amphora id: %s", amphora.id)
            return

        for nic in delta.delete_nics:
            try:
                self.network_driver.unplug_network(amphora.compute_id,
                                                   nic.network_id)
            except base.NetworkNotFound:
                LOG.debug("Network %d not found", nic.network_id)
            except Exception:
                LOG.exception("Unable to unplug network")


class GetMemberPorts(BaseNetworkTask):

    def execute(self, loadbalancer, amphora):
        vip_port = self.network_driver.get_port(loadbalancer.vip.port_id)
        member_ports = []
        interfaces = self.network_driver.get_plugged_networks(
            amphora.compute_id)
        for interface in interfaces:
            port = self.network_driver.get_port(interface.port_id)
            if vip_port.network_id == port.network_id:
                continue
            port.network = self.network_driver.get_network(port.network_id)
            for fixed_ip in port.fixed_ips:
                if amphora.lb_network_ip == fixed_ip.ip_address:
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

    def execute(self, amphora, delta):
        """Handle network plugging based off deltas."""
        added_ports = {}
        added_ports[amphora.id] = []
        for nic in delta.add_nics:
            interface = self.network_driver.plug_network(delta.compute_id,
                                                         nic.network_id)
            port = self.network_driver.get_port(interface.port_id)
            port.network = self.network_driver.get_network(port.network_id)
            for fixed_ip in port.fixed_ips:
                fixed_ip.subnet = self.network_driver.get_subnet(
                    fixed_ip.subnet_id)
            added_ports[amphora.id].append(port)
        for nic in delta.delete_nics:
            try:
                self.network_driver.unplug_network(delta.compute_id,
                                                   nic.network_id)

            except base.NetworkNotFound:
                LOG.debug("Network %d not found ", nic.network_id)
            except Exception:
                LOG.exception("Unable to unplug network")
        return added_ports

    def revert(self, result, amphora, delta, *args, **kwargs):
        """Handle a network plug or unplug failures."""

        if isinstance(result, failure.Failure):
            return

        if not delta:
            return

        LOG.warning("Unable to plug networks for amp id %s",
                    delta.amphora_id)

        for nic in delta.add_nics:
            try:
                self.network_driver.unplug_network(delta.compute_id,
                                                   nic.network_id)
            except Exception:
                pass


class HandleNetworkDeltas(BaseNetworkTask):
    """Task to plug and unplug networks

    Loop through the deltas and plug or unplug
    networks based on delta
    """

    def execute(self, deltas):
        """Handle network plugging based off deltas."""
        added_ports = {}
        for amp_id, delta in six.iteritems(deltas):
            added_ports[amp_id] = []
            for nic in delta.add_nics:
                LOG.debug("[NetIF] plug_network %s on %s", nic.network_id, delta.compute_id)
                interface = self.network_driver.plug_network(delta.compute_id,
                                                             nic.network_id)
                port = self.network_driver.get_port(interface.port_id)
                port.network = self.network_driver.get_network(port.network_id)
                for fixed_ip in port.fixed_ips:
                    fixed_ip.subnet = self.network_driver.get_subnet(
                        fixed_ip.subnet_id)
                added_ports[amp_id].append(port)
            for nic in delta.delete_nics:
                try:
                    LOG.debug("[NetIF] unplug_network %s on %s", nic.network_id, delta.compute_id)
                    self.network_driver.unplug_network(delta.compute_id,
                                                       nic.network_id)
                    network = self.network_driver.get_network(nic.network_id)
                    added_ports[amp_id].append(network)
                except base.NetworkNotFound:
                    LOG.debug("Network %d not found ", nic.network_id)
                except Exception as e:
                    LOG.exception(
                        "Unable to unplug network due to: %s", str(e))
                    raise e
        return added_ports

    def revert(self, result, deltas, *args, **kwargs):
        """Handle a network plug or unplug failures."""

        if isinstance(result, failure.Failure):
            return
        for amp_id, delta in six.iteritems(deltas):
            LOG.warning("Unable to plug networks for amp id %s",
                        delta.amphora_id)
            if not delta:
                return

            for nic in delta.add_nics:
                try:
                    self.network_driver.unplug_network(delta.compute_id,
                                                       nic.network_id)
                except base.NetworkNotFound:
                    pass


class PlugVIP(BaseNetworkTask):
    """Task to plumb a VIP."""

    def execute(self, loadbalancer):
        """Plumb a vip to an amphora."""

        LOG.debug("Plumbing VIP for loadbalancer id: %s", loadbalancer.id)

        amps_data = self.network_driver.plug_vip(loadbalancer,
                                                 loadbalancer.vip)
        return amps_data

    def revert(self, result, loadbalancer, *args, **kwargs):
        """Handle a failure to plumb a vip."""

        if isinstance(result, failure.Failure):
            return
        LOG.warning("Unable to plug VIP for loadbalancer id %s",
                    loadbalancer.id)

        try:
            # Make sure we have the current port IDs for cleanup
            for amp_data in result:
                for amphora in six.moves.filter(
                        # pylint: disable=cell-var-from-loop
                        lambda amp: amp.id == amp_data.id,
                        loadbalancer.amphorae):
                    amphora.vrrp_port_id = amp_data.vrrp_port_id
                    amphora.ha_port_id = amp_data.ha_port_id

            self.network_driver.unplug_vip_revert(loadbalancer, loadbalancer.vip)
        except Exception as e:
            LOG.error("Failed to unplug VIP.  Resources may still "
                      "be in use from vip: %(vip)s due to error: %(except)s",
                      {'vip': loadbalancer.vip.ip_address, 'except': e})


class UpdateVIPSecurityGroup(BaseNetworkTask):
    """Task to setup SG for LB."""

    def execute(self, loadbalancer):
        """Task to setup SG for LB."""

        LOG.debug("Setup SG for loadbalancer id: %s", loadbalancer.id)

        self.network_driver.update_vip_sg(loadbalancer, loadbalancer.vip)


class GetSubnetFromVIP(BaseNetworkTask):
    """Task to plumb a VIP."""

    def execute(self, loadbalancer):
        """Plumb a vip to an amphora."""

        LOG.debug("Getting subnet for LB: %s", loadbalancer.id)

        return self.network_driver.get_subnet(loadbalancer.vip.subnet_id)


class PlugVIPAmpphora(BaseNetworkTask):
    """Task to plumb a VIP."""

    def execute(self, loadbalancer, amphora, subnet):
        """Plumb a vip to an amphora."""

        LOG.debug("Plumbing VIP for amphora id: %s", amphora.id)

        amp_data = self.network_driver.plug_aap_port(
            loadbalancer, loadbalancer.vip, amphora, subnet)
        return amp_data

    def revert(self, result, loadbalancer, amphora, subnet, *args, **kwargs):
        """Handle a failure to plumb a vip."""

        if isinstance(result, failure.Failure):
            return
        LOG.warning("Unable to plug VIP for amphora id %s "
                    "load balancer id %s",
                    amphora.id, loadbalancer.id)

        try:
            amphora.vrrp_port_id = result.vrrp_port_id
            amphora.ha_port_id = result.ha_port_id

            self.network_driver.unplug_aap_port(loadbalancer.vip,
                                                amphora, subnet)
        except Exception as e:
            LOG.error('Failed to unplug AAP port. Resources may still be in '
                      'use for VIP: %s due to error: %s', loadbalancer.vip, e)


class UnplugVIP(BaseNetworkTask):
    """Task to unplug the vip."""

    def execute(self, loadbalancer):
        """Unplug the vip."""

        LOG.debug("Unplug vip on amphora")
        try:
            self.network_driver.unplug_vip(loadbalancer, loadbalancer.vip)
        except Exception:
            LOG.exception("Unable to unplug vip from load balancer %s",
                          loadbalancer.id)


class AllocateVIP(BaseNetworkTask):
    """Task to allocate a VIP."""

    def execute(self, loadbalancer, lb_count_subnet):
        """Allocate a vip to the loadbalancer."""

        LOG.debug("Allocate_vip port_id %s, subnet_id %s,"
                  "ip_address %s",
                  loadbalancer.vip.port_id,
                  loadbalancer.vip.subnet_id,
                  loadbalancer.vip.ip_address)
        return self.network_driver.allocate_vip(loadbalancer)

    def revert(self, result, loadbalancer, lb_count_subnet, *args, **kwargs):
        """Handle a failure to allocate vip."""

        if isinstance(result, failure.Failure):
            LOG.exception("Unable to allocate VIP")
            return
        vip = result
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
        LOG.debug("Deallocating a VIP %s", loadbalancer.vip.ip_address)
        self.network_driver.deallocate_vip(loadbalancer, lb_count_subnet)


class UpdateVIP(BaseNetworkTask):
    """Task to update a VIP."""

    def execute(self, loadbalancer):
        LOG.debug("Updating VIP of load_balancer %s.", loadbalancer.id)
        self.network_driver.update_vip(loadbalancer)


class UpdateVIPForDelete(BaseNetworkTask):
    """Task to update a VIP for listener delete flows."""

    def execute(self, loadbalancer):
        LOG.debug("Updating VIP for listener delete on load_balancer %s.",
                  loadbalancer.id)

        self.network_driver.update_vip(loadbalancer, for_delete=True)


class GetAmphoraNetworkConfigs(BaseNetworkTask):
    """Task to retrieve amphora network details."""

    def execute(self, loadbalancer, amphora=None):
        LOG.debug("Retrieving vip network details.")
        return self.network_driver.get_network_configs(loadbalancer,
                                                       amphora=amphora)


class GetAmphoraeNetworkConfigs(BaseNetworkTask):
    """Task to retrieve amphorae network details."""

    def execute(self, loadbalancer):
        LOG.debug("Retrieving vip network details.")
        return self.network_driver.get_network_configs(loadbalancer)


class FailoverPreparationForAmphora(BaseNetworkTask):
    """Task to prepare an amphora for failover."""

    def execute(self, amphora):
        LOG.debug("Prepare amphora %s for failover.", amphora.id)

        self.network_driver.failover_preparation(amphora)


class RetrievePortIDsOnAmphoraExceptLBNetwork(BaseNetworkTask):
    """Task retrieving all the port ids on an amphora, except lb network."""

    def execute(self, amphora):
        LOG.debug("Retrieve all but the lb network port id on amphora %s.",
                  amphora.id)

        interfaces = self.network_driver.get_plugged_networks(
            compute_id=amphora.compute_id)

        ports = []
        for interface_ in interfaces:
            if interface_.port_id not in ports:
                port = self.network_driver.get_port(port_id=interface_.port_id)
                ips = port.fixed_ips
                lb_network = False
                for ip in ips:
                    if ip.ip_address == amphora.lb_network_ip:
                        lb_network = True
                if not lb_network:
                    ports.append(port)

        return ports


class PlugPorts(BaseNetworkTask):
    """Task to plug neutron ports into a compute instance."""

    def execute(self, amphora, ports):
        for port in ports:
            LOG.debug('Plugging port ID: %(port_id)s into compute instance: '
                      '%(compute_id)s.',
                      {'port_id': port.id, 'compute_id': amphora.compute_id})
            self.network_driver.plug_port(amphora, port)


class PlugVIPPort(BaseNetworkTask):
    """Task to plug a VIP into a compute instance."""

    def execute(self, amphora, amphorae_network_config):
        vrrp_port = amphorae_network_config.get(amphora.id).vrrp_port
        LOG.debug('Plugging VIP VRRP port ID: %(port_id)s into compute '
                  'instance: %(compute_id)s.',
                  {'port_id': vrrp_port.id, 'compute_id': amphora.compute_id})
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
                  {'amp_id': amphora.id})
        self.network_driver.wait_for_port_detach(amphora)


class ApplyQos(BaseNetworkTask):
    """Apply Quality of Services to the VIP"""

    def _apply_qos_on_vrrp_ports(self, loadbalancer, amps_data, qos_policy_id,
                                 is_revert=False, request_qos_id=None):
        """Call network driver to apply QoS Policy on the vrrp ports."""
        if not amps_data:
            amps_data = loadbalancer.amphorae

        apply_qos = ApplyQosAmphora()
        for amp_data in amps_data:
            apply_qos._apply_qos_on_vrrp_port(loadbalancer, amp_data,
                                              qos_policy_id)

    def execute(self, loadbalancer, amps_data=None, update_dict=None):
        """Apply qos policy on the vrrp ports which are related with vip."""
        qos_policy_id = loadbalancer.vip.qos_policy_id
        if not qos_policy_id and (
            update_dict and (
                'vip' not in update_dict or
                'qos_policy_id' not in update_dict['vip'])):
            return
        self._apply_qos_on_vrrp_ports(loadbalancer, amps_data, qos_policy_id)

    def revert(self, result, loadbalancer, amps_data=None, update_dict=None,
               *args, **kwargs):
        """Handle a failure to apply QoS to VIP"""
        request_qos_id = loadbalancer.vip.qos_policy_id
        orig_lb = self.task_utils.get_current_loadbalancer_from_db(
            loadbalancer.id)
        orig_qos_id = orig_lb.vip.qos_policy_id
        if request_qos_id != orig_qos_id:
            self._apply_qos_on_vrrp_ports(loadbalancer, amps_data, orig_qos_id,
                                          is_revert=True,
                                          request_qos_id=request_qos_id)
        return


class ApplyQosAmphora(BaseNetworkTask):
    """Apply Quality of Services to the VIP"""

    def _apply_qos_on_vrrp_port(self, loadbalancer, amp_data, qos_policy_id,
                                is_revert=False, request_qos_id=None):
        """Call network driver to apply QoS Policy on the vrrp ports."""
        try:
            self.network_driver.apply_qos_on_port(qos_policy_id,
                                                  amp_data.vrrp_port_id)
        except Exception:
            if not is_revert:
                raise
            else:
                LOG.warning('Failed to undo qos policy %(qos_id)s '
                            'on vrrp port: %(port)s from '
                            'amphorae: %(amp)s',
                            {'qos_id': request_qos_id,
                             'port': amp_data.vrrp_port_id,
                             'amp': [amp.id for amp in amp_data]})

    def execute(self, loadbalancer, amp_data=None, update_dict=None):
        """Apply qos policy on the vrrp ports which are related with vip."""
        qos_policy_id = loadbalancer.vip.qos_policy_id
        if not qos_policy_id and (
            update_dict and (
                'vip' not in update_dict or
                'qos_policy_id' not in update_dict['vip'])):
            return
        self._apply_qos_on_vrrp_port(loadbalancer, amp_data, qos_policy_id)

    def revert(self, result, loadbalancer, amp_data=None, update_dict=None,
               *args, **kwargs):
        """Handle a failure to apply QoS to VIP"""
        try:
            request_qos_id = loadbalancer.vip.qos_policy_id
            orig_lb = self.task_utils.get_current_loadbalancer_from_db(
                loadbalancer.id)
            orig_qos_id = orig_lb.vip.qos_policy_id
            if request_qos_id != orig_qos_id:
                self._apply_qos_on_vrrp_port(loadbalancer, amp_data,
                                             orig_qos_id, is_revert=True,
                                             request_qos_id=request_qos_id)
        except Exception as e:
            LOG.error('Failed to remove QoS policy: %s from port: %s due '
                      'to error: %s', orig_qos_id, amp_data.vrrp_port_id, e)


class HandleVRIDFloatingIP(BaseNetworkTask):
    """Handle VRID floating IP configurations for loadbalancer resourse"""

    def __init__(self, *arg, **kwargs):
        self.added_fip_ports = []
        super(HandleVRIDFloatingIP, self).__init__(*arg, **kwargs)

    def _add_vrid_to_list(self, vrid_list, subnet, owner):
        vrid_value = CONF.a10_global.vrid
        subnet_ids = set([s.id for s in subnet]) if isinstance(subnet, list) else [subnet.id]
        for subnet_id in subnet_ids:
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
            LOG.error(msg, lb_resource.id)
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
            conf_floating_ip = a10_utils.get_vrid_floating_ip_for_project(
                lb_resource.project_id)

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
            try:
                vrid_summary = self.axapi_client.vrrpa.get(vrid.vrid)
            except Exception as e:
                vrid_summary = {}
                LOG.exception("Failed to get existing VRID summary due to: %s", str(e))

            if vrid_summary and 'floating-ip' in vrid_summary['vrid']:
                vrid_fip = vrid_summary['vrid']['floating-ip']
                if vthunder.partition_name != 'shared':
                    for i in range(len(vrid_fip['ip-address-part-cfg'])):
                        existing_fips.append(
                            vrid_fip['ip-address-part-cfg'][i]['ip-address-partition'])
                else:
                    for i in range(len(vrid_fip['ip-address-cfg'])):
                        existing_fips.append(vrid_fip['ip-address-cfg'][i]['ip-address'])
            vrid_subnet = self.network_driver.get_subnet(vrid.subnet_id)
            vrid.vrid = vrid_value
            if conf_floating_ip.lower() == 'dhcp':
                subnet_ip, subnet_mask = a10_utils.get_net_info_from_cidr(
                    vrid_subnet.cidr)
                if not a10_utils.check_ip_in_subnet_range(
                        vrid.vrid_floating_ip, subnet_ip, subnet_mask):
                    vrid = self._replace_vrid_port(vrid, vrid_subnet, lb_resource)
                    update_vrid_flag = True
            else:
                new_ip = a10_utils.get_patched_ip_address(
                    conf_floating_ip, vrid_subnet.cidr)
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
        LOG.warning(
            "Reverting VRRP floating IP delta task for lb_resource %s",
            lb_resource.id)
        # Delete newly added ports
        for port in self.added_fip_ports:
            try:
                self.network_driver.delete_port(port.id)
            except Exception as e:
                LOG.error(
                    "Failed to delete port %s due to %s",
                    port.id,
                    str(e))

        vrid_floating_ip_list = [vrid.vrid_floating_ip for vrid in vrid_list]

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
            for vr in vrid_list:
                try:
                    vrid_summary = self.axapi_client.vrrpa.get(vr.vrid)
                except Exception as e:
                    vrid_summary = {}
                    LOG.exception("Failed to get existing VRID summary due to: %s", str(e))

                if vrid_summary and 'floating-ip' in vrid_summary['vrid']:
                    vrid_fip = vrid_summary['vrid']['floating-ip']
                    if vthunder.partition_name != 'shared':
                        for i in range(len(vrid_fip['ip-address-part-cfg'])):
                            existing_fips.append(
                                vrid_fip['ip-address-part-cfg'][i]['ip-address-partition'])
                    else:
                        for i in range(len(vrid_fip['ip-address-cfg'])):
                            existing_fips.append(vrid_fip['ip-address-cfg'][i]['ip-address'])
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
                for vrid in vrid_list:
                    try:
                        vrid_summary = self.axapi_client.vrrpa.get(vrid.vrid)
                    except Exception as e:
                        vrid_summary = {}
                        LOG.exception("Failed to get existing VRID summary due to: %s", str(e))

                    if vrid_summary and 'floating-ip' in vrid_summary['vrid']:
                        vrid_fip = vrid_summary['vrid']['floating-ip']
                        if vthunder.partition_name != 'shared':
                            for i in range(len(vrid_fip['ip-address-part-cfg'])):
                                existing_fips.append(
                                    vrid_fip['ip-address-part-cfg'][i]['ip-address-partition'])
                        else:
                            for i in range(len(vrid_fip['ip-address-cfg'])):
                                existing_fips.append(vrid_fip['ip-address-cfg'][i]['ip-address'])

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
        return self.get_vlan_id(loadbalancer.vip.subnet_id)


class GetMemberSubnetVLANID(GetSubnetVLANIDParent, BaseNetworkTask):

    default_provides = a10constants.VLAN_ID

    def execute(self, member):
        return self.get_vlan_id(member.subnet_id)


class GetLBResourceSubnet(BaseNetworkTask):
    "Provides subnet ID for LB resource"

    def execute(self, lb_resource):
        if not hasattr(lb_resource, 'subnet_id'):
            # Special case for load balancers as their vips have the subnet
            # info
            subnet = self.network_driver.get_subnet(lb_resource.vip.subnet_id)
        elif lb_resource.subnet_id:
            subnet = self.network_driver.get_subnet(lb_resource.subnet_id)
        else:
            return
        return subnet


class GetAllResourceSubnet(BaseNetworkTask):
    "Provides subnet ID for LB resources"

    def execute(self, members):
        subnet = []
        for member in members:
            if member.subnet_id:
                subnet.append(self.network_driver.get_subnet(member.subnet_id))
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
            except neutron_exceptions.InvalidIpForSubnetClient as e:
                # The NAT pool addresses is not in member subnet, a10-octavia will allow it but
                # will not able to reserve address for it. (since we don't know the subnet)
                LOG.exception("Failed to reserve addresses in NAT pool %s from subnet %s: %s",
                              nat_flavor['pool_name'], member.subnet_id, str(e))
            except Exception as e:
                LOG.exception("Failed to reserve addresses in NAT pool %s from subnet %s",
                              nat_flavor['pool_name'], member.subnet_id)
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
                            member.subnet_id, addr_list, amphorae)
            except Exception as e:
                LOG.exception("Failed to release addresses in NAT pool %s from subnet %s",
                              nat_flavor['pool_name'], member.subnet_id)
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


class ValidateSubnet(BaseNetworkTask):

    def execute(self, member):
        if member.subnet_id:
            member_subnet = self.network_driver.get_subnet(member.subnet_id)
            subnet_ip, subnet_mask = a10_utils.get_net_info_from_cidr(member_subnet.cidr)
            if not a10_utils.check_ip_in_subnet_range(
                    member.ip_address, subnet_ip, subnet_mask):
                raise exceptions.IPAddressNotInSubnetRangeError(
                    member.ip_address, member_subnet.cidr)
