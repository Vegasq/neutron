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

from neutron.ipam.drivers.infoblox import config
from neutron.ipam.drivers.infoblox import exceptions
from neutron.tests import base


class PatternBuilderTestCase(base.BaseTestCase):
    def test_dots_in_ip_address_replaced_with_dashes(self):
        context = mock.MagicMock()
        subnet = mock.MagicMock()
        ip = '192.168.1.1'

        res = config.PatternBuilder("{ip_address}").build(
            context, subnet, ip_addr=ip)

        self.assertEqual(res, ip.replace('.', '-'))

    def test_raises_error_if_pattern_is_invalid(self):
        context = mock.MagicMock()
        subnet = mock.MagicMock()

        pb = config.PatternBuilder("{}")
        self.assertRaises(exceptions.InfobloxConfigException,
                          pb.build, context, subnet)

        pb = config.PatternBuilder("start..end")
        self.assertRaises(exceptions.InfobloxConfigException,
                          pb.build, context, subnet)

        pb = config.PatternBuilder("{non-existing-variable}")
        self.assertRaises(exceptions.InfobloxConfigException,
                          pb.build, context, subnet)

    def test_subnet_id_used_if_subnet_has_no_name(self):
        context = mock.MagicMock()
        subnet = mock.MagicMock()
        subnet_id = 'some-id'

        def get_id(item):
            if item == 'id':
                return subnet_id
            return None
        subnet.__getitem__.side_effect = get_id

        pb = config.PatternBuilder("{subnet_name}")
        built = pb.build(context, subnet)

        self.assertEqual(built, subnet_id)

    def test_value_is_built_using_pattern(self):
        context = mock.MagicMock()
        subnet = mock.MagicMock()
        subnet_name = 'subnet-name'
        ip_address = 'ip_address'

        def get_id(item):
            if item == 'name':
                return subnet_name
            else:
                return None
        subnet.__getitem__.side_effect = get_id

        pattern = "host-{ip_address}.{subnet_name}.custom_stuff"
        pb = config.PatternBuilder(pattern)
        built = pb.build(context, subnet, ip_addr=ip_address)

        self.assertEqual(built, pattern.format(subnet_name=subnet_name,
                                               ip_address=ip_address))

    def test_all_required_pattern_variables_are_supported(self):
        required_variables = [
            'tenant_id', 'instance_id', 'ip_address',
            'ip_address_octet1', 'ip_address_octet2', 'ip_address_octet3',
            'ip_address_octet4', 'subnet_id', 'subnet_name', 'user_id',
            'network_id', 'network_name'
        ]

        pattern = '.'.join(['{%s}' % v for v in required_variables])
        context = mock.Mock()
        context.user_id = 'user-id'
        subnet = {
            'network_id': 'some-net-id',
            'tenant_id': 'some-tenant-id',
            'id': 'some-subnet-id',
            'name': 'some-subnet-name'
        }
        port = {
            'id': 'some-port-id',
            'device_id': 'some-device-id'
        }
        ip_addr = '10.0.0.3'

        pb = config.PatternBuilder(pattern)

        try:
            pb.build(context, subnet, port, ip_addr)
        except exceptions.InvalidPattern as e:
            self.fail('Unexpected exception: {}'.format(e))
