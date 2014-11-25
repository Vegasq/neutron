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

from testtools import matchers

from neutron.ipam.drivers.infoblox import objects
from neutron.openstack.common import jsonutils
from neutron.tests import base


class InfobloxNetworkObjectTestCase(base.BaseTestCase):
    def setUp(self):
        super(InfobloxNetworkObjectTestCase, self).setUp()
        self.network_object_dict = jsonutils.loads("""[
        {
            "_ref": "network/ZG5zLldHdvcmskMTAuMzkuMTE:10.39.11.0/24/default",
            "members": [
                {
                    "_struct": "dhcpmember",
                    "ipv4addr": "10.39.11.123",
                    "name": "infoblox.localdomain"
                }
            ],
            "options": [
                {
                    "name": "dhcp-lease-time",
                    "num": 51,
                    "use_option": false,
                    "value": "43200",
                    "vendor_class": "DHCP"
                },
                {
                    "name": "domain-name-servers",
                    "num": 6,
                    "use_option": true,
                    "value": "10.39.11.123,10.39.11.124,10.39.11.125",
                    "vendor_class": "DHCP"
                },
                {
                    "name": "routers",
                    "num": 3,
                    "use_option": false,
                    "value": "10.39.11.1",
                    "vendor_class": "DHCP"
                }
            ]
        }
    ]""")[0]

    def _get_nameservers_opt(self, network):
        nameservers_opts = filter(lambda opt:
                                  opt['name'] ==
                                  objects.Network.DNS_NAMESERVERS_OPTION,
                                  network['options'])
        if nameservers_opts:
            return nameservers_opts[0]
        return None

    def test_has_members(self):
        net = objects.Network.from_dict(self.network_object_dict)
        self.assertTrue(net.members)

    def test_update_member_ip_modifies_member_ip(self):
        net = objects.Network.from_dict(self.network_object_dict)
        new_ip = '!!!NEW_IP!!!'
        net.update_member_ip_in_dns_nameservers(new_ip)
        self.assertIn(new_ip, net.dns_nameservers)

    def test_get_dns_nameservers(self):
        net = objects.Network.from_dict(self.network_object_dict)
        servers = "10.39.11.123,10.39.11.124,10.39.11.125".split(',')
        self.assertEqual(servers, net.dns_nameservers)

    def test_get_dns_nameservers_no_option(self):
        nameservers_opt = self._get_nameservers_opt(self.network_object_dict)
        self.network_object_dict['options'].remove(nameservers_opt)
        net = objects.Network.from_dict(self.network_object_dict)
        self.assertEqual([], net.dns_nameservers)

    def test_get_dns_nameservers_use_option_false(self):
        nameservers_opt = self._get_nameservers_opt(self.network_object_dict)
        nameservers_opt['use_option'] = False
        net = objects.Network.from_dict(self.network_object_dict)
        self.assertEqual([], net.dns_nameservers)

    def test_set_dns_nameservers(self):
        net = objects.Network.from_dict(self.network_object_dict)
        net.dns_nameservers = ['1.1.1.1', '3.3.3.3']
        net_dict = net.to_dict()
        nameservers_opt = self._get_nameservers_opt(net_dict)
        self.assertEqual('1.1.1.1,3.3.3.3', nameservers_opt['value'])
        self.assertTrue(nameservers_opt['use_option'])

    def test_set_dns_nameservers_empty_val(self):
        net = objects.Network.from_dict(self.network_object_dict)
        net.dns_nameservers = []
        net_dict = net.to_dict()
        nameservers_opt = self._get_nameservers_opt(net_dict)
        self.assertFalse(nameservers_opt['use_option'])

    def test_set_dns_nameservers_no_previous_option(self):
        nameservers_opt = self._get_nameservers_opt(self.network_object_dict)
        self.network_object_dict['options'].remove(nameservers_opt)
        net = objects.Network.from_dict(self.network_object_dict)
        net.dns_nameservers = ['7.7.7.7', '8.8.8.8']
        net_dict = net.to_dict()
        nameservers_opt = self._get_nameservers_opt(net_dict)
        self.assertEqual('7.7.7.7,8.8.8.8', nameservers_opt['value'])
        self.assertTrue(nameservers_opt['use_option'])

    def test_set_dns_nameservers_no_previous_option_and_empty_val(self):
        nameservers_opt = self._get_nameservers_opt(self.network_object_dict)
        self.network_object_dict['options'].remove(nameservers_opt)
        net = objects.Network.from_dict(self.network_object_dict)
        net.dns_nameservers = []
        net_dict = net.to_dict()
        nameservers_opt = self._get_nameservers_opt(net_dict)
        self.assertIsNone(nameservers_opt)


class InfobloxIPv4ObjectTestCase(base.BaseTestCase):
    def test_removes_correct_object_from_list_of_ips(self):
        removed_ip = '192.168.1.2'
        ips = [
            objects.IPv4(ip='192.168.1.1'),
            objects.IPv4(ip=removed_ip),
            objects.IPv4(ip='192.168.1.3')
        ]

        ips.remove(removed_ip)

        self.assertEqual(len(ips), 2)
        for ip in ips:
            self.assertTrue(ip.ip != removed_ip)


class InfobloxIPv4HostRecordObjectTestCase(base.BaseTestCase):
    def setUp(self):
        super(InfobloxIPv4HostRecordObjectTestCase, self).setUp()
        host_record_ref = ("record:host/ZG5zLmhvc3QkLjY3OC5jb20uZ2xvYmFsLmNs"
                           "b3VkLnRlc3RzdWJuZXQudGVzdF9ob3N0X25hbWU:"
                           "test_host_name.testsubnet.cloud.global.com/"
                           "default.687401e9f7a7471abbf301febf99854e")
        ipv4addrs_ref = ("record:host_ipv4addr/ZG5zLmhvc3RfYWRkcmVzcyQuNjc"
                         "4LmNvbS5nbG9iYWwuY2xvdWQudGVzdHN1Ym5ldC50ZXN0X2h"
                         "vc3RfbmFtZS4xOTIuMTY4LjAuNS4:192.168.0.5/"
                         "test_host_name.testsubnet.cloud.global.com/"
                         "default.687401e9f7a7471abbf301febf99854e")
        self.host_record = jsonutils.loads("""{
            "_ref": "%s",
            "ipv4addrs": [
                {
                    "_ref": "%s",
                    "configure_for_dhcp": false,
                    "host": "test_host_name.testsubnet.cloud.global.com",
                    "ipv4addr": "192.168.0.5",
                    "mac": "aa:bb:cc:dd:ee:ff"
                }
            ]
        }
        """ % (host_record_ref, ipv4addrs_ref))

    def test_constructs_object_from_dict(self):
        host_record = objects.HostRecordIPv4.from_dict(self.host_record)
        self.assertIsNotNone(host_record)

    def test_hostname_is_set_from_dict(self):
        expected_hostname = 'expected_hostname'
        expected_dns_zone = 'expected.dns.zone.com'
        self.host_record['ipv4addrs'][0]['host'] = '.'.join(
            [expected_hostname, expected_dns_zone])
        host_record = objects.HostRecordIPv4.from_dict(self.host_record)

        self.assertEqual(expected_hostname, host_record.hostname)
        self.assertEqual(expected_dns_zone, host_record.zone_auth)

    def test_all_attributes_are_set_from_dict(self):
        expected_attributes = ['hostname', 'dns_view', 'mac', 'ip']
        hr = objects.HostRecordIPv4.from_dict(self.host_record)
        self.assertTrue(all([expected in dir(hr)
                             for expected in expected_attributes]))


class InfobloxIPv6HostRecordObjectTestCase(base.BaseTestCase):
    def setUp(self):
        super(InfobloxIPv6HostRecordObjectTestCase, self).setUp()
        host_record_ref = ("record:host/ZG5zLmhvc3QkLjY3OC5jb20uZ2xvYmFsLmNs"
                           "b3VkLnRlc3RzdWJuZXQudGVzdF9ob3N0X25hbWU:"
                           "test_host_name.testsubnet.cloud.global.com/"
                           "default.687401e9f7a7471abbf301febf99854e")
        ipv6addrs_ref = ("record:host_ipv4addr/ZG5zLmhvc3RfYWRkcmVzcyQuNjc"
                         "4LmNvbS5nbG9iYWwuY2xvdWQudGVzdHN1Ym5ldC50ZXN0X2h"
                         "vc3RfbmFtZS4xOTIuMTY4LjAuNS4:2001:DB8::3/"
                         "test_host_name.testsubnet.cloud.global.com/"
                         "default.687401e9f7a7471abbf301febf99854e")
        self.host_record = jsonutils.loads("""{
            "_ref": "%s",
            "ipv6addrs": [
                {
                    "_ref": "%s",
                    "configure_for_dhcp": false,
                    "host": "test_host_name.testsubnet.cloud.global.com",
                    "ipv6addr": "2001:DB8::3",
                    "mac": "aa:bb:cc:dd:ee:ff"
                }
            ]
        }
        """ % (host_record_ref, ipv6addrs_ref))

    def test_constructs_object_from_dict(self):
        host_record = objects.HostRecordIPv6.from_dict(self.host_record)
        self.assertIsNotNone(host_record)

    def test_hostname_is_set_from_dict(self):
        expected_hostname = 'expected_hostname'
        expected_dns_zone = 'expected.dns.zone.com'
        self.host_record['ipv6addrs'][0]['host'] = '.'.join(
            [expected_hostname, expected_dns_zone])
        host_record = objects.HostRecordIPv6.from_dict(self.host_record)

        self.assertEqual(expected_hostname, host_record.hostname)
        self.assertEqual(expected_dns_zone, host_record.zone_auth)

    def test_all_attributes_are_set_from_dict(self):
        expected_attributes = ['hostname', 'dns_view', 'mac', 'ip']
        hr = objects.HostRecordIPv6.from_dict(self.host_record)
        self.assertTrue(all([expected in dir(hr)
                             for expected in expected_attributes]))


class FixedAddressIPv4TestCase(base.BaseTestCase):
    def test_builds_valid_fa_from_infoblox_returned_json(self):
        fixed_address_ref = ("fixedaddress/ZG5zLmZpeGVkX2FkZHJlc3MkMTAuMC4wLj"
                             "EwMC42ODAuLg:10.0.0.100/rv-test-netview")
        ip = "10.0.0.100"
        fixed_address = jsonutils.loads("""{
            "_ref": "%s",
            "ipv4addr": "%s"
        }""" % (fixed_address_ref, ip))

        fa = objects.FixedAddressIPv4.from_dict(fixed_address)
        self.assertEqual(fa.ip, ip)

    def test_dict_contains_mac_ip_and_net_view(self):
        expected_ip = "1.2.3.4"
        expected_mac = "aa:bb:cc:dd:ee:ff"
        expected_net_view = "test-net-view-name"
        expected_extattrs = "test-extattrs"

        expected_dict = {
            'mac': expected_mac,
            'ipv4addr': expected_ip,
            'network_view': expected_net_view,
            'extattrs': expected_extattrs
        }

        fa = objects.FixedAddressIPv4()
        fa.ip = expected_ip
        fa.net_view = expected_net_view
        fa.mac = expected_mac
        fa.extattrs = expected_extattrs

        self.assertThat(fa.to_dict(), matchers.KeysEqual(expected_dict))
        self.assertThat(fa.to_dict(), matchers.Equals(expected_dict))


class FixedAddressIPv6TestCase(base.BaseTestCase):
    def test_builds_valid_fa_from_infoblox_returned_json(self):
        fixed_address_ref = ("fixedaddress/ZG5zLmZpeGVkX2FkZHJlc3MkMTAuMC4wLj"
                             "EwMC42ODAuLg:10.0.0.100/rv-test-netview")
        ip = "2001:DB8::3"
        fixed_address = jsonutils.loads("""{
            "_ref": "%s",
            "ipv6addr": "%s"
        }""" % (fixed_address_ref, ip))

        fa = objects.FixedAddressIPv6.from_dict(fixed_address)
        self.assertEqual(fa.ip, ip)

    def test_dict_contains_mac_ip_and_net_view(self):
        expected_ip = "2001:DB8::3"
        duid = "aa:bb:cc:dd:ee:ff"
        expected_duid = "00:03:00:01:aa:bb:cc:dd:ee:ff"
        expected_net_view = "test-net-view-name"
        expected_extattrs = "test-extattrs"

        expected_dict = {
            'duid': expected_duid,
            'ipv6addr': expected_ip,
            'network_view': expected_net_view,
            'extattrs': expected_extattrs
        }

        fa = objects.FixedAddressIPv6()
        fa.ip = expected_ip
        fa.net_view = expected_net_view
        fa.mac = duid
        fa.extattrs = expected_extattrs

        self.assertThat(fa.to_dict(), matchers.KeysEqual(expected_dict))
        self.assertThat(fa.to_dict(), matchers.Equals(expected_dict))


class MemberTestCase(base.BaseTestCase):
    def test_two_identical_members_are_equal(self):
        ip = 'some-ip'
        name = 'some-name'

        m1 = objects.Member(ip, name)
        m2 = objects.Member(ip, name)

        self.assertEqual(m1, m2)


class IPAllocationObjectTestCase(base.BaseTestCase):
    def test_next_available_ip_returns_properly_formatted_string(self):
        net_view = 'expected_net_view_name'
        first_ip = '1.2.3.4'
        last_ip = '1.2.3.14'
        cidr = '1.2.3.0/24'

        naip = objects.IPAllocationObject.next_available_ip_from_range(
            net_view, first_ip, last_ip)

        self.assertTrue(isinstance(naip, basestring))
        self.assertTrue(naip.startswith('func:nextavailableip:'))
        self.assertTrue(naip.endswith(
            '{first_ip}-{last_ip},{net_view}'.format(**locals())))

        naip = objects.IPAllocationObject.next_available_ip_from_cidr(
            net_view, cidr)

        self.assertTrue(isinstance(naip, basestring))
        self.assertTrue(naip.startswith('func:nextavailableip:'))
        self.assertTrue(naip.endswith(
            '{cidr},{net_view}'.format(**locals())))
