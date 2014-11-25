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

from neutron.common import exceptions as neutron_exc
from neutron.db.infoblox import infoblox_db as infoblox_db
from neutron.ipam.drivers.infoblox import ea_manager
from neutron.ipam.drivers.infoblox import exceptions as ib_exceptions
from neutron.ipam.drivers.infoblox import infoblox_ipam
from neutron.ipam.drivers.infoblox import ipam_controller
from neutron.ipam.drivers.infoblox import objects
from neutron.tests import base


class SubstringMatcher(object):
    def __init__(self, expected):
        self.expected = expected

    def __eq__(self, actual):
        return self.expected in actual

    def __repr__(self):
        return "Expected substring: '{}'".format(self.expected)


class CreateSubnetTestCases(base.BaseTestCase):
    def setUp(self):
        super(CreateSubnetTestCases, self).setUp()

        self.expected_net_view_name = 'some-tenant-id'
        self.cidr = 'some-cidr'
        self.first_ip = '192.168.0.1'
        self.last_ip = '192.168.0.254'
        self.subnet = mock.MagicMock()
        self.subnet.__getitem__.side_effect = mock.MagicMock()
        self.object_manipulator = mock.Mock()
        ip_allocator = mock.Mock()
        self.object_manipulator.network_exists.return_value = False
        self.object_manipulator.set_network_view = mock.MagicMock()

        cfg = mock.Mock()
        cfg.reserve_dhcp_members = mock.Mock(return_value=[])
        cfg.reserve_dns_members = mock.Mock(return_value=[])
        cfg.dhcp_members = ['member1.com']
        cfg.dns_members = ['member1.com']

        config_finder = mock.Mock()
        config_finder.find_config_for_subnet = mock.Mock(return_value=cfg)

        context = infoblox_ipam.FlowContext(mock.MagicMock(), 'create-subnet')

        b = ipam_controller.InfobloxIPAMController(self.object_manipulator,
                                                   config_finder,
                                                   ip_allocator)
        b.ea_manager = mock.Mock()
        b.create_subnet(context, self.subnet)
        taskflow.engines.run(context.parent_flow, store=context.store)

    def test_network_view_is_created_on_subnet_creation(self):
        assert self.object_manipulator.create_network_view.called_once

    def test_dns_view_is_created_on_subnet_creation(self):
        assert self.object_manipulator.create_dns_view.called_once

    def test_infoblox_network_is_created_on_subnet_create(self):
        assert self.object_manipulator.create_network.called_once

    def test_ip_range_is_created_on_subnet_create(self):
        assert self.object_manipulator.create_ip_range.called_once


class UpdateSubnetTestCase(base.BaseTestCase):
    def setUp(self):
        super(UpdateSubnetTestCase, self).setUp()
        self.object_manipulator = mock.Mock()
        self.context = mock.Mock()
        ip_allocator = mock.Mock()
        config_finder = mock.Mock()

        cfg = mock.Mock()
        cfg.dhcp_members = ['member1.com']
        cfg.dns_members = ['member1.com']
        config_finder.find_config_for_subnet.return_value = cfg

        self.ipam = ipam_controller.InfobloxIPAMController(
            self.object_manipulator, config_finder, ip_allocator)
        self.ipam.ea_manager = mock.Mock()

        self.sub_id = 'fake-id'
        self.new_nameservers = ['new_serv1', 'new_serv2']
        self.sub = dict(
            id=self.sub_id,
            cidr='test-cidr',
            dns_nameservers=self.new_nameservers,
            network_id='some-net-id'
        )
        self.ib_net = objects.Network()
        self.object_manipulator.get_network.return_value = self.ib_net

    @mock.patch.object(infoblox_db, 'get_subnet_dhcp_port_address',
                       mock.Mock(return_value=None))
    def test_update_subnet_dns_no_primary_ip(self):
        self.ipam.update_subnet(self.context, self.sub_id, self.sub)

        self.assertEqual(self.new_nameservers, self.ib_net.dns_nameservers)
        self.object_manipulator.update_network_options.assert_called_once_with(
            self.ib_net, mock.ANY
        )

    @mock.patch.object(infoblox_db, 'get_subnet_dhcp_port_address',
                       mock.Mock(return_value=None))
    def test_update_subnet_dns_primary_is_member_ip(self):
        self.ib_net.member_ip_addrs = ['member-ip']
        self.ib_net.dns_nameservers = ['member-ip', 'old_serv1', 'old_serv']

        self.ipam.update_subnet(self.context, self.sub_id, self.sub)

        self.assertEqual(['member-ip'] + self.new_nameservers,
                         self.ib_net.dns_nameservers)
        self.object_manipulator.update_network_options.assert_called_once_with(
            self.ib_net, mock.ANY
        )

    @mock.patch.object(infoblox_db, 'get_subnet_dhcp_port_address',
                       mock.Mock())
    def test_update_subnet_dns_primary_is_relay_ip(self):
        self.ib_net.member_ip_addr = 'fake_ip'
        self.ib_net.dns_nameservers = ['relay_ip', '1.1.1.1', '2.2.2.2']

        infoblox_db.get_subnet_dhcp_port_address.return_value = 'relay-ip'

        self.ipam.update_subnet(self.context, self.sub_id, self.sub)

        self.assertEqual(['relay-ip'] + self.new_nameservers,
                         self.ib_net.dns_nameservers)
        self.object_manipulator.update_network_options.assert_called_once_with(
            self.ib_net, mock.ANY
        )

    def test_extensible_attributes_get_updated(self):
        ea_manager = mock.Mock()
        manip = mock.MagicMock()
        config_finder = mock.Mock()
        config = mock.Mock()
        config.dhcp_members = ['member1.com']
        config.dns_members = ['member1.com']
        config_finder.find_config_for_subnet = mock.Mock(return_value=config)
        context = mock.Mock()
        subnet_id = 'some-id'
        subnet = mock.MagicMock()
        subnet.name = None

        ctrlr = ipam_controller.InfobloxIPAMController(
            manip, config_finder, extattr_manager=ea_manager)

        ctrlr.update_subnet(context, subnet_id, subnet)

        assert manip.update_network_options.called_once


class AllocateIPTestCase(base.BaseTestCase):
    def test_host_record_created_on_allocate_ip(self):
        infoblox = mock.Mock()
        member_config = mock.MagicMock()
        ip_allocator = mock.Mock()
        context = mock.Mock()

        subnet = {'tenant_id': 'some-id', 'id': 'some-id'}
        mac = 'aa:bb:cc:dd:ee:ff'
        port = {'id': hostname,
                'mac_address': mac}
        ip_dict = {'ip_address': '192.168.1.1',
                   'subnet_id': 'fake-id'}
        ip = {'ip_address': '192.168.1.1'}

        b = ipam_controller.InfobloxIPAMController(infoblox,
                                                   member_config,
                                                   ip_allocator)
        b.pattern_builder = mock.Mock()
        b.ea_manager = mock.Mock()

        b.allocate_ip(context, subnet, port, ip_dict)

        ip_allocator.allocate_given_ip.assert_called_once_with(
            mock.ANY, mock.ANY, mock.ANY, hostname, mac, ip['ip_address'],
            mock.ANY)

    def test_host_record_from_range_created_on_allocate_ip(self):
        infoblox = mock.Mock()
        member_config = mock.MagicMock()
        ip_allocator = mock.Mock()
        context = mock.Mock()

        first_ip = '192.168.1.1'
        last_ip = '192.168.1.132'

        subnet = {'allocation_pools': [{'first_ip': first_ip,
                                        'last_ip': last_ip}],
                  'tenant_id': 'some-id',
                  'id': 'some-id'}

        mac = 'aa:bb:cc:dd:ee:ff'
        port = {'mac_address': mac,
                'device_owner': 'owner'}

        b = ipam_controller.InfobloxIPAMController(infoblox,
                                                   member_config,
                                                   ip_allocator)
        b.pattern_builder = mock.Mock()
        b.ea_manager = mock.Mock()
        b.allocate_ip(context, subnet, port)

        assert not ip_allocator.allocate_given_ip.called
        ip_allocator.allocate_ip_from_range.assert_called_once_with(
            mock.ANY, mock.ANY, mock.ANY, mock.ANY, mac, first_ip, last_ip,
            mock.ANY)

    def test_cannot_allocate_ip_raised_if_empty_range(self):
        infoblox = mock.Mock()
        member_config = mock.Mock()
        context = mock.Mock()
        ip_allocator = mock.Mock()

        hostname = 'hostname'
        subnet = {'allocation_pools': [],
                  'tenant_id': 'some-id',
                  'cidr': '192.168.0.0/24'}
        mac = 'aa:bb:cc:dd:ee:ff'
        host = {'name': hostname,
                'mac_address': mac,
                'device_owner': 'owner'}

        b = ipam_controller.InfobloxIPAMController(infoblox,
                                                   member_config,
                                                   ip_allocator)
        b.pattern_builder = mock.Mock()
        b.ea_manager = mock.Mock()

        assert not infoblox.create_host_record_range.called
        assert not infoblox.create_host_record_ip.called
        self.assertRaises(ib_exceptions.InfobloxCannotAllocateIpForSubnet,
                          b.allocate_ip, context, subnet, host)


class DeallocateIPTestCase(base.BaseTestCase):
    def setUp(self):
        super(DeallocateIPTestCase, self).setUp()

        self.infoblox = mock.Mock()

        cfg = mock.Mock()
        cfg.dhcp_members = ['172.25.1.1']

        config_finder = mock.MagicMock()
        config_finder.find_config_for_subnet = mock.Mock(return_value=cfg)

        context = mock.MagicMock()
        self.ip_allocator = mock.Mock()

        hostname = 'hostname'
        self.ip = '192.168.0.1'
        subnet = {'tenant_id': 'some-id',
                  'network_id': 'some-id',
                  'id': 'some-id'}
        mac = 'aa:bb:cc:dd:ee:ff'
        host = {'name': hostname,
                'mac_address': mac}

        b = ipam_controller.InfobloxIPAMController(self.infoblox,
                                                   config_finder,
                                                   self.ip_allocator)
        b.deallocate_ip(context, subnet, host, self.ip)

    def test_ip_is_deallocated(self):
        self.ip_allocator.deallocate_ip.assert_called_once_with(
            mock.ANY, mock.ANY, self.ip)

    def test_dns_and_dhcp_services_restarted(self):
        assert self.infoblox.restart_all_services.called_once


class NetOptionsMatcher(object):
    def __init__(self, expected_ip):
        self.expected_ip = expected_ip

    def __eq__(self, actual_net):
        return self.expected_ip in actual_net.dns_nameservers

    def __repr__(self):
        return "{}".format(self.expected_ip)


class DnsNameserversTestCase(base.BaseTestCase):
    def test_network_is_updated_with_new_ip(self):
        infoblox = mock.Mock()
        ip_allocator = mock.Mock()
        member_config = mock.Mock()
        context = mock.MagicMock()

        expected_ip = '192.168.1.1'
        cidr = '192.168.1.0/24'
        port = {'fixed_ips': [{'subnet_id': 'some-id',
                               'ip_address': expected_ip}]}
        subnet = {'cidr': cidr,
                  'tenant_id': 'some-id'}

        network = objects.Network()
        network.members = ['member1']
        network.member_ip_addrs = ['192.168.1.2']
        network.dns_nameservers = [expected_ip]

        infoblox.get_network.return_value = network

        b = ipam_controller.InfobloxIPAMController(infoblox,
                                                   member_config,
                                                   ip_allocator)
        b._get_subnet = mock.Mock()
        b._get_subnet.return_value = subnet

        b.set_dns_nameservers(context, port)

        matcher = NetOptionsMatcher(expected_ip)
        infoblox.update_network_options.assert_called_once_with(matcher)

    def test_network_is_not_updated_if_network_has_no_members(self):
        infoblox = mock.Mock()
        member_config = mock.Mock()
        ip_allocator = mock.Mock()
        context = mock.MagicMock()

        expected_ip = '192.168.1.1'
        cidr = '192.168.1.0/24'
        port = {'fixed_ips': [{'subnet_id': 'some-id',
                               'ip_address': expected_ip}]}
        subnet = {'cidr': cidr,
                  'tenant_id': 'some-id'}

        infoblox.get_network.return_value = objects.Network()

        b = ipam_controller.InfobloxIPAMController(infoblox,
                                                   member_config,
                                                   ip_allocator)
        b._get_subnet = mock.Mock()
        b._get_subnet.return_value = subnet

        b.set_dns_nameservers(context, port)

        assert not infoblox.update_network_options.called

    def test_network_is_not_updated_if_network_has_no_dns_members(self):
        infoblox = mock.Mock()
        member_config = mock.Mock()
        ip_allocator = mock.Mock()
        context = mock.MagicMock()

        expected_ip = '192.168.1.1'
        cidr = '192.168.1.0/24'
        port = {'fixed_ips': [{'subnet_id': 'some-id',
                               'ip_address': expected_ip}]}
        subnet = {'cidr': cidr,
                  'tenant_id': 'some-id'}
        network = objects.Network()
        network.members = ['member1']

        infoblox.get_network.return_value = network

        b = ipam_controller.InfobloxIPAMController(infoblox,
                                                   member_config,
                                                   ip_allocator)
        b._get_subnet = mock.Mock()
        b._get_subnet.return_value = subnet

        b.set_dns_nameservers(context, port)

        assert not infoblox.update_network_options.called


class DeleteSubnetTestCase(base.BaseTestCase):
    def test_ib_network_deleted(self):
        infoblox = mock.Mock()
        member_conf = mock.Mock()
        config = mock.Mock()
        config.dhcp_members = ['member1.com']
        config.dns_members = ['member1.com']
        member_conf.find_config_for_subnet = mock.Mock(return_value=config)
        ip_allocator = mock.Mock()
        context = mock.MagicMock()

        cidr = '192.168.0.0/24'
        subnet = mock.MagicMock()
        subnet.__getitem__ = mock.Mock(return_value=cidr)

        b = ipam_controller.InfobloxIPAMController(infoblox,
                                                   member_conf,
                                                   ip_allocator)

        b.delete_subnet(context, subnet)

        infoblox.delete_network.assert_called_once_with(mock.ANY, cidr=cidr)

    def test_member_released(self):
        infoblox = mock.Mock()
        member_finder = mock.Mock()
        config = mock.Mock()
        config.dhcp_members = ['member1.com']
        config.dns_members = ['member1.com']
        member_finder.find_config_for_subnet = mock.Mock(return_value=config)
        ip_allocator = mock.Mock()
        context = mock.MagicMock()

        subnet = mock.MagicMock()

        b = ipam_controller.InfobloxIPAMController(infoblox,
                                                   member_finder,
                                                   ip_allocator)
        b.delete_subnet(context, subnet)

        assert member_finder.member_manager.release_member.called_once

    def test_preconfigured_dns_view_gets_deleted(self):
        dns_view = "fake dns view"
        infoblox = mock.Mock()
        infoblox.has_dns_zones = mock.Mock(return_value=False)
        ip_allocator = mock.Mock()
        config = mock.Mock()
        config.dhcp_members = ['member1.com']
        config.dns_members = ['member1.com']
        config._dns_view = dns_view
        config_finder = mock.Mock()
        config_finder.find_config_for_subnet = mock.Mock(return_value=config)
        context = mock.Mock()
        subnet = mock.MagicMock()

        b = ipam_controller.InfobloxIPAMController(infoblox,
                                                   config_finder,
                                                   ip_allocator)

        b.get_subnets_by_network = mock.MagicMock()
        b.delete_subnet(context, subnet)

        infoblox.delete_dns_view.assert_called_once_with(dns_view)

    def test_network_view_deleted(self):
        infoblox = mock.Mock()
        ip_allocator = mock.Mock()
        member_conf = mock.Mock()
        config = mock.Mock()
        config.dhcp_members = ['member1.com']
        config.dns_members = ['member1.com']
        member_conf.find_config_for_subnet = mock.Mock(return_value=config)
        context = mock.Mock()
        network = mock.MagicMock()

        b = ipam_controller.InfobloxIPAMController(infoblox,
                                                   member_conf,
                                                   ip_allocator)

        b.get_subnets_by_network = mock.MagicMock()
        b.delete_subnet(context, network)

        assert infoblox.delete_network_view.called_once


class CreateSubnetFlowTestCase(base.BaseTestCase):
    def setUp(self):
        super(CreateSubnetFlowTestCase, self).setUp()

        self.infoblox = mock.Mock()
        member_conf = mock.MagicMock()
        ip_allocator = mock.Mock()
        self.expected_exception = Exception
        self.context = infoblox_ipam.FlowContext(mock.MagicMock(),
                                                 'create-subnet')
        self.subnet = {'cidr': '192.168.0.0/24',
                       'tenant_id': 'some-id',
                       'network_id': 'some-id',
                       'gateway_ip': '192.168.1.1',
                       'allocation_pools': [{'start': 'start',
                                             'end': 'end'}],
                       'ip_version': 'ipv4',
                       'name': 'some-name',
                       'enable_dhcp': True}

        self.infoblox.create_ip_range.side_effect = Exception()
        self.infoblox.network_exists.return_value = False

        self.b = ipam_controller.InfobloxIPAMController(self.infoblox,
                                                        member_conf,
                                                        ip_allocator)
        self.b.pattern_builder = mock.Mock()
        self.b.ea_manager = mock.Mock()

    def test_flow_is_reverted_in_case_of_error(self):
        self.infoblox.has_networks.return_value = False
        self.b.create_subnet(self.context, self.subnet)
        self.assertRaises(self.expected_exception, taskflow.engines.run,
                          self.context.parent_flow, store=self.context.store)

        assert self.infoblox.delete_network.called
        assert not self.infoblox.delete_dns_view.called
        assert self.infoblox.delete_network_view.called

    def test_network_view_is_not_deleted_if_has_networks(self):
        self.infoblox.has_networks.return_value = True
        self.b.create_subnet(self.context, self.subnet)

        self.assertRaises(self.expected_exception, taskflow.engines.run,
                          self.context.parent_flow, store=self.context.store)

        assert self.infoblox.delete_network.called
        assert not self.infoblox.delete_dns_view.called
        assert not self.infoblox.delete_network_view.called


class CreateSubnetFlowNiosNetExistsTestCase(base.BaseTestCase):
    def setUp(self):
        super(CreateSubnetFlowNiosNetExistsTestCase, self).setUp()

        self.infoblox = mock.Mock()
        member_conf = mock.MagicMock()
        ip_allocator = mock.Mock()
        self.context = infoblox_ipam.FlowContext(mock.MagicMock(),
                                                 'create-subnet')
        self.subnet = mock.MagicMock()
        self.subnet.__getitem__.side_effect = mock.MagicMock()

        self.infoblox.network_exists.return_value = True

        self.b = ipam_controller.InfobloxIPAMController(self.infoblox,
                                                        member_conf,
                                                        ip_allocator)

    def test_nios_network_is_updated_for_shared_os_network(self):
        self.b.ea_manager.get_extattrs_for_network = mock.Mock(
            return_value={
                ea_manager.InfobloxEaManager.INFOBLOX_IS_EXTERNAL: {
                    'value': 'False'},
                ea_manager.InfobloxEaManager.INFOBLOX_IS_SHARED: {
                    'value': 'True'}
            })

        self.b.create_subnet(self.context, self.subnet)

        taskflow.engines.run(self.context.parent_flow,
                             store=self.context.store)
        assert self.infoblox.update_network_options.called_once

    def test_nios_network_is_updated_for_shared_external_os_network(self):
        self.b.ea_manager.get_extattrs_for_network = mock.Mock(
            return_value={
                ea_manager.InfobloxEaManager.INFOBLOX_IS_EXTERNAL: {
                    'value': 'True'},
                ea_manager.InfobloxEaManager.INFOBLOX_IS_SHARED: {
                    'value': 'True'}
            })

        self.b.create_subnet(self.context, self.subnet)

        taskflow.engines.run(self.context.parent_flow,
                             store=self.context.store)
        assert self.infoblox.update_network_options.called_once

    def test_nios_network_is_updated_for_external_os_network(self):
        self.b.ea_manager.get_extattrs_for_network = mock.Mock(
            return_value={
                ea_manager.InfobloxEaManager.INFOBLOX_IS_EXTERNAL: {
                    'value': 'True'},
                ea_manager.InfobloxEaManager.INFOBLOX_IS_SHARED: {
                    'value': 'False'}
            })

        self.b.create_subnet(self.context, self.subnet)

        taskflow.engines.run(self.context.parent_flow,
                             store=self.context.store)
        assert self.infoblox.update_network_options.called_once

    def test_exception_is_raised_if_network_is_private(self):
        self.b.ea_manager.get_extattrs_for_network = mock.Mock(
            return_value={
                ea_manager.InfobloxEaManager.INFOBLOX_IS_EXTERNAL: {
                    'value': 'False'},
                ea_manager.InfobloxEaManager.INFOBLOX_IS_SHARED: {
                    'value': 'False'}
            })

        self.b.create_subnet(self.context, self.subnet)

        self.assertRaises(
            ib_exceptions.InfobloxInternalPrivateSubnetAlreadyExist,
            taskflow.engines.run,
            self.context.parent_flow,
            store=self.context.store
        )


class DeleteNetworkTestCase(base.BaseTestCase):
    def test_deletes_all_subnets(self):
        infoblox = mock.Mock()
        ip_allocator = mock.Mock()
        member_conf = mock.Mock()
        context = mock.Mock()
        db_manager = mock.Mock()
        network = {'id': 'some-id'}
        num_subnets = 5

        b = ipam_controller.InfobloxIPAMController(infoblox,
                                                   member_conf,
                                                   ip_allocator,
                                                   db_mgr=db_manager)

        b.delete_subnet = mock.Mock()
        db_manager.get_subnets_by_network = mock.Mock()
        db_manager.get_subnets_by_network.return_value = [
            mock.Mock() for _ in xrange(num_subnets)]

        b.delete_network(context, network)

        assert b.delete_subnet.called
        assert b.delete_subnet.call_count == num_subnets

    def test_deletes_network_view(self):
        infoblox = mock.Mock()
        ip_allocator = mock.Mock()
        member_conf = mock.Mock()
        context = mock.MagicMock()
        network_id = 'some-id'

        b = ipam_controller.InfobloxIPAMController(infoblox,
                                                   member_conf,
                                                   ip_allocator)

        b.delete_network(context, network_id)

        assert infoblox.delete_network_view.called_once

    def test_deletes_management_ip(self):
        infoblox = mock.Mock()
        ip_allocator = mock.Mock()
        member_conf = mock.Mock()
        context = mock.Mock()
        network = mock.MagicMock()
        ib_db = mock.Mock()
        ea_manager = mock.Mock()
        db_manager = mock.Mock()

        ib_db.is_network_external.return_value = False

        net_view_name = 'expected_network_view'
        cidr = 'expected_cidr'

        self.config(dhcp_relay_management_network_view=net_view_name,
                    dhcp_relay_management_network=cidr)

        b = ipam_controller.InfobloxIPAMController(infoblox,
                                                   member_conf,
                                                   ip_allocator,
                                                   ea_manager,
                                                   ib_db,
                                                   db_mgr=db_manager)

        b.delete_subnet = mock.Mock()
        db_manager.get_subnets_by_network = mock.MagicMock()

        b.delete_network(context, network)
        infoblox.delete_object_by_ref.assert_called_once_with(mock.ANY)

    def test_deletes_management_ip_from_db(self):
        infoblox = mock.Mock()
        ip_allocator = mock.Mock()
        member_conf = mock.Mock()
        context = mock.Mock()
        expected_net_id = 'some-net-id'
        ib_db = mock.Mock()
        db_manager = mock.Mock()

        ib_db.is_network_external.return_value = False
        net_view_name = 'expected_network_view'
        cidr = 'expected_cidr'

        self.config(dhcp_relay_management_network_view=net_view_name,
                    dhcp_relay_management_network=cidr)

        b = ipam_controller.InfobloxIPAMController(infoblox,
                                                   member_conf,
                                                   ip_allocator,
                                                   ib_db=ib_db,
                                                   db_mgr=db_manager)

        b.delete_subnet = mock.Mock()
        db_manager.get_subnets_by_network = mock.MagicMock()

        b.delete_network(context, expected_net_id)
        ib_db.delete_management_ip.assert_called_once_with(
            context, expected_net_id)

    def test_does_not_delete_management_network_ip_for_external_net(self):
        infoblox = mock.Mock()
        ip_allocator = mock.Mock()
        member_conf = mock.Mock()
        context = mock.MagicMock()
        network_id = mock.MagicMock()
        ib_db = mock.Mock()
        ea_manager = mock.Mock()

        ib_db.is_network_external.return_value = True

        net_view_name = 'expected_network_view'
        cidr = 'expected_cidr'

        self.config(dhcp_relay_management_network_view=net_view_name,
                    dhcp_relay_management_network=cidr)

        b = ipam_controller.InfobloxIPAMController(infoblox,
                                                   member_conf,
                                                   ip_allocator,
                                                   ea_manager,
                                                   ib_db)
        b.delete_network(context, network_id)

        assert not infoblox.delete_object_by_ref.called
        assert not ib_db.delete_management_ip.called


class CreateNetworkTestCase(base.BaseTestCase):
    def test_creates_fixed_address_object_in_management_network(self):
        infoblox = mock.Mock()
        config_finder = mock.Mock()
        ip_allocator = mock.Mock()
        ea_manager = mock.Mock()
        context = mock.Mock()
        network = mock.MagicMock()
        network.get.return_value = False
        network.__getitem__.side_effect = mock.Mock()

        expected_net_view = 'expected_net_view_name'
        cidr = '1.0.0.0/24'
        expected_mac = '00:00:00:00:00:00'
        self.config(dhcp_relay_management_network_view=expected_net_view,
                    dhcp_relay_management_network=cidr)

        c = ipam_controller.InfobloxIPAMController(infoblox, config_finder,
                                                   ip_allocator, ea_manager)

        c.create_network(context, network)
        infoblox.create_fixed_address_from_cidr.assert_called_once_with(
            expected_net_view, expected_mac, cidr)

    def test_stores_fixed_address_object_in_db(self):
        infoblox = mock.Mock()
        config_finder = mock.Mock()
        ip_allocator = mock.Mock()
        ea_manager = mock.Mock()
        context = mock.Mock()
        ib_db = mock.Mock()
        expected_net_id = 'some-net-id'

        network = mock.MagicMock()
        network.get.return_value = False
        network.__getitem__.side_effect = \
            lambda key: expected_net_id if key == 'id' else None

        expected_net_view = 'expected_net_view_name'
        cidr = '1.0.0.0/24'
        self.config(dhcp_relay_management_network_view=expected_net_view,
                    dhcp_relay_management_network=cidr)

        c = ipam_controller.InfobloxIPAMController(
            infoblox, config_finder, ip_allocator, ea_manager, ib_db)

        c.create_network(context, network)

        ib_db.add_management_ip.assert_called_once_with(
            context, expected_net_id, mock.ANY)

    def test_does_nothing_if_mgmt_net_is_not_set_in_config(self):
        infoblox = mock.Mock()
        config_finder = mock.Mock()
        ip_allocator = mock.Mock()
        ea_manager = mock.Mock()
        context = mock.Mock()
        ib_db = mock.Mock()
        network = mock.Mock()
        network.get.return_value = False

        c = ipam_controller.InfobloxIPAMController(
            infoblox, config_finder, ip_allocator, ea_manager, ib_db)

        c.create_network(context, network)

        assert not infoblox.create_fixed_address_from_cidr.called
        assert not ib_db.add_management_ip.called

    def test_does_nothing_for_external_net(self):
        infoblox = mock.Mock()
        config_finder = mock.Mock()
        ip_allocator = mock.Mock()
        ea_manager = mock.Mock()
        context = mock.Mock()
        ib_db = mock.Mock()
        network = mock.Mock()

        c = ipam_controller.InfobloxIPAMController(
            infoblox, config_finder, ip_allocator, ea_manager, ib_db)

        try:
            c.create_network(context, network)
        except neutron_exc.InvalidConfigurationOption as e:
            self.fail('Unexpected exception: {}'.format(e))

        assert not infoblox.create_fixed_address_from_cidr.called
        assert not ib_db.add_management_ip.called
