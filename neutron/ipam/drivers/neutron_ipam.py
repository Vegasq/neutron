# Copyright 2014 OpenStack LLC.
# All Rights Reserved.
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

from neutron.api.v2 import attributes
from neutron.common import constants
from neutron.common import exceptions as q_exc
from neutron.db import models_v2
from neutron.ipam import base
from neutron.ipam.drivers import neutron_db
from neutron.openstack.common import log as logging
from neutron.openstack.common import uuidutils

LOG = logging.getLogger(__name__)


class NeutronIPAMController(base.IPAMController):
    def _make_allocation_pools(self, context, backend_subnet, subnet):
        # Store information about allocation pools and ranges
        for pool in subnet['allocation_pools']:
            ip_pool = models_v2.IPAllocationPool(subnet=backend_subnet,
                                                 first_ip=pool['start'],
                                                 last_ip=pool['end'])
            context.session.add(ip_pool)
            ip_range = models_v2.IPAvailabilityRange(
                ipallocationpool=ip_pool,
                first_ip=pool['start'],
                last_ip=pool['end'])
            context.session.add(ip_range)

    def create_subnet(self, context, subnet):
        tenant_id = self._get_tenant_id_for_create(context, subnet)
        network = self._get_network(context, subnet['network_id'])

        # The 'shared' attribute for subnets is for internal plugin
        # use only. It is not exposed through the API
        args = {'tenant_id': tenant_id,
                'id': subnet.get('id') or uuidutils.generate_uuid(),
                'name': subnet['name'],
                'network_id': subnet['network_id'],
                'ip_version': subnet['ip_version'],
                'cidr': subnet['cidr'],
                'enable_dhcp': subnet['enable_dhcp'],
                'gateway_ip': subnet['gateway_ip'],
                'shared': network.shared}
        if subnet['ip_version'] == 6 and subnet['enable_dhcp']:
            if attributes.is_attr_set(subnet['ipv6_ra_mode']):
                args['ipv6_ra_mode'] = subnet['ipv6_ra_mode']
            if attributes.is_attr_set(subnet['ipv6_address_mode']):
                args['ipv6_address_mode'] = subnet['ipv6_address_mode']
        backend_subnet = models_v2.Subnet(**args)

        self._make_allocation_pools(context, backend_subnet, subnet)
        context.session.add(backend_subnet)

        return self._make_subnet_dict(backend_subnet)

    def create_network(self, context, network):
        return network

    def get_subnet_by_id(self, context, subnet_id):
        return self._get_subnet(context, subnet_id)

    def update_subnet(self, context, subnet_id, subnet):
        backend_subnet = self.get_subnet_by_id(context, subnet_id)
        return backend_subnet

    def _make_subnet_dict(self, subnet, fields=None):
        res = {'id': subnet['id'],
               'name': subnet['name'],
               'tenant_id': subnet['tenant_id'],
               'network_id': subnet['network_id'],
               'ip_version': subnet['ip_version'],
               'cidr': subnet['cidr'],
               'allocation_pools': [{'start': pool['first_ip'],
                                     'end': pool['last_ip']}
                                    for pool in subnet['allocation_pools']],
               'gateway_ip': subnet['gateway_ip'],
               'enable_dhcp': subnet['enable_dhcp'],
               'ipv6_ra_mode': subnet['ipv6_ra_mode'],
               'ipv6_address_mode': subnet['ipv6_address_mode'],
               'dns_nameservers': [dns['address']
                                   for dns in subnet['dns_nameservers']],
               'host_routes': [{'destination': route['destination'],
                                'nexthop': route['nexthop']}
                               for route in subnet['routes']],
               'shared': subnet['shared']
               }
        # Call auxiliary extend functions, if any
        self._apply_dict_extend_functions(attributes.SUBNETS, res, subnet)

        return self._fields(res, fields)

    def get_subnets_count(self, context, filters=None):
        return self._get_collection_count(context, models_v2.Subnet,
                                          filters=filters)

    def delete_subnet(self, context, backend_subnet):
        pass

    def force_off_ports(self, context, ports):
        """Force Off ports on subnet delete event."""
        for port in ports:
            query = (context.session.query(models_v2.Port).
                     enable_eagerloads(False).filter_by(id=port.id))
            if not context.is_admin:
                query = query.filter_by(tenant_id=context.tenant_id)

            query.delete()

    def allocate_ip(self, context, subnet, host, ip=None):
        if ip is not None and 'ip_address' in ip:
            subnet_id = subnet['id']
            ip_address = {'subnet_id': subnet_id,
                          'ip_address': ip['ip_address']}
            neutron_db.allocate_specific_ip(
                context, subnet_id,ip['ip_address'])
            return ip_address
        else:
            return neutron_db.generate_ip(context, subnet)

    def deallocate_ip(self, context, backend_subnet, host, ip_address):
        # IPAllocations are automatically handled by cascade deletion
        pass

    def delete_network(self, context, network_id):
        pass

    def set_dns_nameservers(self, context, port):
        pass


class NeutronDHCPController(base.DHCPController):
    def __init__(self, db_mgr=None):
        if db_mgr is None:
            db_mgr = neutron_db

        self.db_manager = db_mgr

    def configure_dhcp(self, context, backend_subnet, dhcp_params):
        # Store information about DNS Servers
        if dhcp_params['dns_nameservers'] is not attributes.ATTR_NOT_SPECIFIED:
            for addr in dhcp_params['dns_nameservers']:
                ns = models_v2.DNSNameServer(address=addr,
                                             subnet_id=backend_subnet['id'])
                context.session.add(ns)
                backend_subnet['dns_nameservers'].append(addr)

        # Store host routes
        if dhcp_params['host_routes'] is not attributes.ATTR_NOT_SPECIFIED:
            for rt in dhcp_params['host_routes']:
                route = models_v2.SubnetRoute(
                    subnet_id=backend_subnet['id'],
                    destination=rt['destination'],
                    nexthop=rt['nexthop'])
                context.session.add(route)
                backend_subnet['host_routes'].append({
                    'destination': rt['destination'],
                    'nexthop': rt['nexthop']})

    def reconfigure_dhcp(self, context, backend_subnet, dhcp_params):
        changed_dns = False
        new_dns = []
        if "dns_nameservers" in dhcp_params:
            changed_dns = True
            old_dns_list = self.db_manager.get_dns_by_subnet(
                context, backend_subnet['id'])
            new_dns_addr_set = set(dhcp_params["dns_nameservers"])
            old_dns_addr_set = set([dns['address']
                                    for dns in old_dns_list])

            new_dns = list(new_dns_addr_set)
            for dns_addr in old_dns_addr_set - new_dns_addr_set:
                for dns in old_dns_list:
                    if dns['address'] == dns_addr:
                        context.session.delete(dns)
            for dns_addr in new_dns_addr_set - old_dns_addr_set:
                dns = models_v2.DNSNameServer(
                    address=dns_addr,
                    subnet_id=backend_subnet['id'])
                context.session.add(dns)

            if len(dhcp_params['dns_nameservers']):
                del dhcp_params['dns_nameservers']

        def _combine(ht):
            return ht['destination'] + "_" + ht['nexthop']

        changed_host_routes = False
        new_routes = []
        if "host_routes" in dhcp_params:
            changed_host_routes = True
            old_route_list = self.db_manager.get_route_by_subnet(
                context, backend_subnet['id'])

            new_route_set = set([_combine(route)
                                 for route in dhcp_params['host_routes']])

            old_route_set = set([_combine(route)
                                 for route in old_route_list])

            for route_str in old_route_set - new_route_set:
                for route in old_route_list:
                    if _combine(route) == route_str:
                        context.session.delete(route)
            for route_str in new_route_set - old_route_set:
                route = models_v2.SubnetRoute(
                    destination=route_str.partition("_")[0],
                    nexthop=route_str.partition("_")[2],
                    subnet_id=backend_subnet['id'])
                context.session.add(route)

            # Gather host routes for result
            for route_str in new_route_set:
                new_routes.append(
                    {'destination': route_str.partition("_")[0],
                     'nexthop': route_str.partition("_")[2]})
            del dhcp_params['host_routes']

        backend_subnet.update(dhcp_params)

        result = {}
        if changed_dns:
            result['new_dns'] = new_dns
        if changed_host_routes:
            result['new_routes'] = new_routes
        return result

    def bind_mac(self, context, backend_subnet, ip_address, mac_address):
        pass

    def unbind_mac(self, context, backend_subnet, ip_address):
        pass

    def dhcp_is_enabled(self, context, backend_subnet):
        pass

    def disable_dhcp(self, context, backend_subnet):
        pass

    def get_dhcp_ranges(self, context, backend_subnet):
        pass


class NeutronDNSController(base.DNSController):
    """DNS controller for standard neutron behavior is not implemented because
    neutron does not provide that functionality
    """
    def bind_names(self, context, backend_port):
        pass

    def unbind_names(self, context, backend_port):
        pass

    def create_dns_zones(self, context, backend_subnet):
        pass

    def delete_dns_zones(self, context, backend_subnet):
        pass

    def disassociate_floatingip(self, context, floatingip, port_id):
        pass


class NeutronIPAM(base.IPAMManager):
    def __init__(self, dhcp_controller=None, dns_controller=None,
                 ipam_controller=None, db_mgr=None):
        # These should be initialized in derived DDI class
        if dhcp_controller is None:
            dhcp_controller = NeutronDHCPController()

        if dns_controller is None:
            dns_controller = NeutronDNSController()

        if ipam_controller is None:
            ipam_controller = NeutronIPAMController()

        if db_mgr is None:
            db_mgr = neutron_db

        self.dns_controller = dns_controller
        self.ipam_controller = ipam_controller
        self.dhcp_controller = dhcp_controller
        self.db_manager = db_mgr

    def create_subnet(self, context, subnet):
        with context.session.begin(subtransactions=True):
            # Allocate IP addresses. Create allocation pools only
            backend_subnet = self.ipam_controller.create_subnet(context,
                                                                subnet)
            self.dns_controller.create_dns_zones(context, backend_subnet)
            # Configure DHCP
            dhcp_params = subnet
            self.dhcp_controller.configure_dhcp(context, backend_subnet,
                                                dhcp_params)

            self.ipam_controller.get_subnet_by_id(context,
                                                  backend_subnet['id'])
            return backend_subnet

    def update_subnet(self, context, subnet_id, subnet):
        with context.session.begin(subtransactions=True):
            backend_subnet = self.ipam_controller.update_subnet(
                context, subnet_id, subnet)

            # Reconfigure DHCP for subnet
            dhcp_params = subnet
            dhcp_changes = self.dhcp_controller.reconfigure_dhcp(
                context, backend_subnet, dhcp_params)

            return backend_subnet, dhcp_changes

    def delete_subnet(self, context, subnet):
        if isinstance(subnet, models_v2.Subnet):
            subnet_id = subnet.id
        else:
            subnet_id = subnet

        with context.session.begin(subtransactions=True):
            backend_subnet = self.ipam_controller.get_subnet_by_id(context,
                                                                   subnet_id)
            subnet_ports = self.db_manager.get_subnet_ports(context, subnet_id)

            ports_to_remove = [port for port in subnet_ports if
                neutron_db.get_subnets_by_port_id(context, port.id) <= 1]

            has_ports_allocated = not all(
                p.device_owner == constants.DEVICE_OWNER_DHCP
                for p in subnet_ports)

            if has_ports_allocated:
                raise q_exc.SubnetInUse(subnet_id=backend_subnet['id'])

            self.ipam_controller.force_off_ports(context, ports_to_remove)
            self.dns_controller.delete_dns_zones(context, backend_subnet)
            self.dhcp_controller.disable_dhcp(context, backend_subnet)
            self.ipam_controller.delete_subnet(context, backend_subnet)

            return subnet_id

    def allocate_ip(self, context, host, ip):
        with context.session.begin(subtransactions=True):
            subnet_id = ip.get('subnet_id', None)
            if not subnet_id:
                LOG.debug(_("ip object must have %(subnet_id)s") % subnet_id)
                raise
            backend_subnet = self.ipam_controller.get_subnet_by_id(context,
                                                                   subnet_id)
            ip_address = self.ipam_controller.allocate_ip(
                context,
                backend_subnet,
                host,
                ip)

            LOG.debug('IPAMManager allocate IP: %s' % ip_address)
            mac_address = host['mac_address']
            self.dhcp_controller.bind_mac(
                context,
                backend_subnet,
                ip_address,
                mac_address)
            return ip_address

    def deallocate_ip(self, context, host, ip):
        with context.session.begin(subtransactions=True):
            subnet_id = ip['subnet_id']
            ip_address = ip['ip_address']
            backend_subnet = self.ipam_controller.get_subnet_by_id(
                context, subnet_id)
            self.dhcp_controller.unbind_mac(
                context,
                backend_subnet,
                ip_address)
            self.ipam_controller.deallocate_ip(
                context,
                backend_subnet,
                host,
                ip_address)

    def create_network(self, context, network):
        return self.ipam_controller.create_network(context, network)

    def delete_network(self, context, network_id):
        self.ipam_controller.delete_network(
            context, network_id)

    def create_port(self, context, port):
        self.dns_controller.bind_names(context, port)
        if constants.DEVICE_OWNER_DHCP == port['device_owner']:
            self.ipam_controller.set_dns_nameservers(context, port)

    def update_port(self, context, port):
        self.dns_controller.bind_names(context, port)

    def delete_port(self, context, port):
        self.dns_controller.unbind_names(context, port)

    def associate_floatingip(self, context, floatingip, port):
        self.create_port(context, port)

    def disassociate_floatingip(self, context, floatingip, port_id):
        self.dns_controller.disassociate_floatingip(context, floatingip,
                                                    port_id)

    def get_additional_network_dict_params(self, ctx, network_id):
        return {}
