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

import mock

import taskflow.engines

from neutron.common import constants as neutron_constants
from neutron.ipam.drivers.infoblox import dns_controller
from neutron.ipam.drivers.infoblox import infoblox_ipam
from neutron.plugins.common import constants as plugins_constants
from neutron.tests import base


class SubstringMatcher(object):
    def __init__(self, names):
        if not isinstance(names, list):
            names = [names]
        self.names = names

    def __eq__(self, expected):
        return all([name in expected for name in self.names])


class DnsControllerTestCase(base.BaseTestCase):
    fip_netview_name = 'my-test-fip-netview-name'

    def setUp(self):
        super(DnsControllerTestCase, self).setUp()
        self.manip = mock.Mock()
        self.context = mock.Mock()
        self.port = mock.MagicMock()
        config_finder = mock.MagicMock()
        expected_value = 'some-expected-value'

        def port_dict(item):
            if item == 'fixed_ips':
                return [{'ip_address': 'some-ip',
                         'subnet_id': 'some-id'}]

            return expected_value
        self.port.__getitem__.side_effect = port_dict

        subnet = {'network_id': 'some-net-id',
                  'name': 'some-dns'}

        self.ip_allocator = mock.Mock()

        self.dns_ctrlr = dns_controller.InfobloxDNSController(
            self.ip_allocator, self.manip, config_finder=config_finder)
        self.dns_ctrlr.ea_manager = mock.Mock()
        self.dns_ctrlr.pattern_builder = mock.Mock()
        self.dns_ctrlr._get_subnet = mock.Mock()
        self.dns_ctrlr._get_subnet.return_value = subnet

    def test_bind_host_names_binds_fqdn_with_ip_in_dns_view(self):
        self.dns_ctrlr.bind_names(self.context, self.port)
        assert self.ip_allocator.bind_names.called_once

    def test_unbind_host_names_binds_fqdn_with_ip_in_dns_view(self):
        self.dns_ctrlr.unbind_names(self.context, self.port)
        assert self.ip_allocator.unbind_names.called_once

    def test_restarts_services_on_bind(self):
        self.dns_ctrlr.bind_names(self.context, self.port)
        assert self.manip.restart_all_services.called_once

    def test_restarts_services_on_unbind(self):
        self.dns_ctrlr.unbind_names(self.context, self.port)
        assert self.manip.restart_all_services.called_once

    def test_get_hostname_pattern_dhcp_port(self):
        port = {'device_owner': neutron_constants.DEVICE_OWNER_DHCP}
        result = self.dns_ctrlr._get_hostname_pattern(port, mock.Mock())
        self.assertEqual('dhcp-port-{ip_address}', result)

    def test_get_hostname_pattern_router_iface(self):
        port = {'device_owner': neutron_constants.DEVICE_OWNER_ROUTER_INTF}
        result = self.dns_ctrlr._get_hostname_pattern(port, mock.Mock())
        self.assertEqual('router-iface-{ip_address}', result)

    def test_get_hostname_pattern_router_gw(self):
        port = {'device_owner': neutron_constants.DEVICE_OWNER_ROUTER_GW}
        result = self.dns_ctrlr._get_hostname_pattern(port, mock.Mock())
        self.assertEqual('router-gw-{ip_address}', result)

    def test_get_hostname_pattern_lb_vip(self):
        port = {'device_owner': 'neutron:' + plugins_constants.LOADBALANCER}
        result = self.dns_ctrlr._get_hostname_pattern(port, mock.Mock())
        self.assertEqual('lb-vip-{ip_address}', result)

    def test_get_hostname_pattern_instance_port(self):
        port = {'device_owner': 'nova:compute'}
        cfg_mock = mock.Mock()
        cfg_mock.hostname_pattern = 'host-{ip_address}'

        result = self.dns_ctrlr._get_hostname_pattern(port, cfg_mock)
        self.assertEqual('host-{ip_address}', result)


class GenericDNSControllerTestCase(base.BaseTestCase):
    def test_fqdn_is_built_with_prefix_ip_address_and_dns_zone(self):
        ip_address = '192.168.1.1'
        prefix = 'host-'
        zone = 'some.dns.zone'

        fqdn = dns_controller.build_fqdn(prefix, zone, ip_address)

        self.assertTrue(fqdn.startswith(prefix))
        self.assertTrue(fqdn.endswith(zone))
        self.assertIn(ip_address.replace('.', '-'), fqdn)

    def test_no_exception_if_subnet_has_no_nameservers_defined(self):
        subnet = {}
        nss = dns_controller.get_nameservers(subnet)
        self.assertTrue(nss == [])

        subnet = {'dns_nameservers': object()}
        nss = dns_controller.get_nameservers(subnet)
        self.assertTrue(nss == [])

        subnet = {'dns_nameservers': []}
        nss = dns_controller.get_nameservers(subnet)
        self.assertTrue(nss == [])


class DomainZoneTestCase(base.BaseTestCase):
    def test_two_dns_zones_created_on_create_dns_zone(self):
        manip = mock.Mock()
        context = infoblox_ipam.FlowContext(mock.Mock(), 'create-dns')
        subnet = {'network_id': 'some-id',
                  'cidr': 'some-cidr',
                  'ip_version': 4}
        expected_member = 'member-name'

        ip_allocator = mock.Mock()
        config_finder = mock.Mock()

        cfg = mock.Mock()
        cfg.ns_group = None
        cfg.reserve_dns_members.return_value = [expected_member]

        config_finder.find_config_for_subnet.return_value = cfg

        dns_ctrlr = dns_controller.InfobloxDNSController(
            ip_allocator, manip, config_finder)
        dns_ctrlr.pattern_builder = mock.Mock()
        dns_ctrlr.create_dns_zones(context, subnet)

        taskflow.engines.run(context.parent_flow, store=context.store)

        assert (manip.method_calls ==
                [mock.call.create_dns_zone(mock.ANY,
                                           mock.ANY,
                                           expected_member,
                                           mock.ANY),
                 mock.call.create_dns_zone(mock.ANY,
                                           mock.ANY,
                                           expected_member,
                                           mock.ANY,
                                           zone_format=mock.ANY)
                 ])

    def test_secondary_dns_members(self):
        manip = mock.Mock()
        context = infoblox_ipam.FlowContext(mock.Mock(), 'create-dns')
        subnet = {'network_id': 'some-id',
                  'cidr': 'some-cidr',
                  'ip_version': 4}
        primary_dns_member = 'member-primary'
        secondary_dns_members = ['member-secondary']

        ip_allocator = mock.Mock()
        config_finder = mock.Mock()

        cfg = mock.Mock()
        cfg.ns_group = None
        cfg.reserve_dns_members.return_value = ([primary_dns_member]
                                                + secondary_dns_members)

        config_finder.find_config_for_subnet.return_value = cfg

        dns_ctrlr = dns_controller.InfobloxDNSController(
            ip_allocator, manip, config_finder)
        dns_ctrlr.pattern_builder = mock.Mock()
        dns_ctrlr.create_dns_zones(context, subnet)

        taskflow.engines.run(context.parent_flow, store=context.store)

        assert (manip.method_calls ==
                [mock.call.create_dns_zone(mock.ANY,
                                           mock.ANY,
                                           primary_dns_member,
                                           secondary_dns_members),
                 mock.call.create_dns_zone(mock.ANY,
                                           mock.ANY,
                                           primary_dns_member,
                                           secondary_dns_members,
                                           zone_format=mock.ANY)
                 ])

    def test_two_dns_zones_deleted_when_not_using_global_dns_zone(self):
        manip = mock.Mock()
        context = mock.Mock()
        subnet = {'network_id': 'some-id',
                  'cidr': 'some-cidr',
                  'name': 'some-name'}
        expected_dns_view = 'some-expected-dns-view'

        cfg = mock.Mock()
        cfg.is_global_config = False
        cfg.dns_view = expected_dns_view

        ip_allocator = mock.Mock()
        config_finder = mock.Mock()
        config_finder.find_config_for_subnet.return_value = cfg
        dns_ctrlr = dns_controller.InfobloxDNSController(
            ip_allocator, manip, config_finder)
        dns_ctrlr.pattern_builder = mock.Mock()
        dns_ctrlr.delete_dns_zones(context, subnet)

        assert manip.method_calls == [
            mock.call.delete_dns_zone(expected_dns_view, mock.ANY),
            mock.call.delete_dns_zone(expected_dns_view, subnet['cidr'])
        ]

    def test_only_subnet_dns_zone_is_deleted_when_global_dns_zone_used(self):
        manip = mock.Mock()
        context = mock.Mock()
        subnet = {'network_id': 'some-id',
                  'cidr': 'some-cidr',
                  'name': 'some-name'}

        ip_allocator = mock.Mock()
        dns_ctrlr = dns_controller.InfobloxDNSController(
            ip_allocator, manip, config_finder=mock.Mock())
        dns_ctrlr.pattern_builder = mock.Mock()
        dns_ctrlr.delete_dns_zones(context, subnet)

        manip.delete_dns_zone.assert_called_once_with(mock.ANY, subnet['cidr'])
