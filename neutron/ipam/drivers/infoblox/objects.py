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
import logging
import netaddr
import six

import neutron.ipam.drivers.infoblox.exceptions as ib_exc


LOG = logging.getLogger(__name__)


def is_valid_ip(ip):
    try:
        netaddr.IPAddress(ip)
    except netaddr.core.AddrFormatError:
        return False

    return True


class Network(object):
    """Sample Infoblox 'network' object in JSON format:
    [
        {
            "_ref": "network/ZG5zLm5ldHdvcmskMTAuMzkuMTEuMC8yNC8w:
                     10.39.11.0/24/default",
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
                    "value": "10.39.11.123",
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
    ]
    """
    DNS_NAMESERVERS_OPTION = 'domain-name-servers'

    def __init__(self):
        self.infoblox_type = 'network'
        self.members = []
        self.options = []
        self.member_ip_addrs = []
        self.infoblox_reference = None
        self.ref = None

    def __repr__(self):
        return "{0}".format(self.to_dict())

    @staticmethod
    def from_dict(network_ib_object):
        net = Network()
        net.members = network_ib_object['members']
        net.options = network_ib_object['options']

        for member in net.members:
            net.member_ip_addrs.append(member['ipv4addr'])
        net.ref = network_ib_object['_ref']
        return net

    @property
    def dns_nameservers(self):
        # NOTE(max_lobur): The behaviour of the WAPI is as follows:
        # * If the subnet created without domain-name-servers option it will
        # be absent in the options list.
        # * If the subnet created with domain-name-servers option and then
        # it's cleared by update operation, the option will be present in
        # the list, will carry the last data, but will have use_option = False
        # Both cases mean that there are NO specified nameservers on NIOS.
        dns_nameservers = []
        for opt in self.options:
            if self._is_dns_option(opt):
                if opt.get('use_option', True):
                    dns_nameservers = opt['value'].split(',')
                    break
        return dns_nameservers

    @dns_nameservers.setter
    def dns_nameservers(self, value):
        for opt in self.options:
            if self._is_dns_option(opt):
                if value:
                    opt['value'] = ",".join(value)
                    opt['use_option'] = True
                else:
                    opt['use_option'] = False
                break
        else:
            if value:
                self.options.append(dict(
                    name=self.DNS_NAMESERVERS_OPTION,
                    value=",".join(value),
                    use_option=True
                ))

    def has_dns_members(self):
        for opt in self.options:
            if self._is_dns_option(opt):
                return True
        return False

    def update_member_ip_in_dns_nameservers(self, relay_ip):
        for opt in self.options:
            if self._is_dns_option(opt):
                original_value = opt['value'].split(',')
                original_value.append(relay_ip)
                original_value = set(list(original_value))
                opt['value'] = ",".join(
                    [val for val in original_value if val])

                return

    def to_dict(self):
        return {
            'members': self.members,
            'options': self.options
        }

    @staticmethod
    def _is_dns_option(option):
        return option['name'] == Network.DNS_NAMESERVERS_OPTION


class IPAllocationObject(object):
    @staticmethod
    def next_available_ip_from_cidr(net_view_name, cidr):
        return ('func:nextavailableip:'
                '{cidr:s},{net_view_name:s}').format(**locals())

    @staticmethod
    def next_available_ip_from_range(net_view_name, first_ip, last_ip):
        return ('func:nextavailableip:'
                '{first_ip}-{last_ip},{net_view_name}').format(**locals())


class IPAddress(object):
    def __init__(self, ip=None, mac=None):
        self.ip = ip
        self.mac = mac
        self.configure_for_dhcp = True
        self.hostname = None
        self.dns_zone = None
        self.fqdn = None

    def __eq__(self, other):
        if isinstance(other, six.string_types):
            return self.ip == other
        elif isinstance(other, self.__class__):
            return self.ip == other.ip and self.dns_zone == other.dns_zone

        return False


class IPv4(IPAddress):
    def to_dict(self, add_host=False):
        d = {
            "ipv4addr": self.ip,
            "configure_for_dhcp": self.configure_for_dhcp
        }

        if self.fqdn and add_host:
            d['host'] = self.fqdn

        if self.mac:
            d['mac'] = self.mac

        return d

    def __repr__(self):
        return 'IPv4Addr({})'.format(self.to_dict())

    @staticmethod
    def from_dict(d):
        ipv4obj = IPv4()
        ip = d.get('ipv4addr')
        if not is_valid_ip(ip):
            raise ib_exc.InfobloxInvalidIp(ip=ip)

        host = d.get('host', 'unknown.unknown')
        hostname, _, dns_zone = host.partition('.')
        ipv4obj.ip = ip
        ipv4obj.mac = d.get('mac')
        ipv4obj.configure_for_dhcp = d.get('configure_for_dhcp')
        ipv4obj.hostname = hostname
        ipv4obj.zone_auth = dns_zone
        ipv4obj.fqdn = host

        return ipv4obj


class IPv6(IPAddress):
    def to_dict(self, add_host=False):
        d = {
            "ipv6addr": self.ip,
            "configure_for_dhcp": self.configure_for_dhcp
        }

        if self.fqdn and add_host:
            d['host'] = self.fqdn

        if self.mac:
            d['duid'] = '00:03:00:01:%s' % self.mac

        return d

    def __repr__(self):
        return 'IPv6Addr({})'.format(self.to_dict())

    @staticmethod
    def from_dict(d):
        ipv6obj = IPv6()
        ip = d.get('ipv6addr')
        if not is_valid_ip(ip):
            raise ib_exc.InfobloxInvalidIp(ip=ip)

        host = d.get('host', 'unknown.unknown')
        hostname, _, dns_zone = host.partition('.')
        ipv6obj.ip = ip
        ipv6obj.duid = d.get('mac')
        ipv6obj.configure_for_dhcp = d.get('configure_for_dhcp')
        ipv6obj.hostname = hostname
        ipv6obj.zone_auth = dns_zone
        ipv6obj.fqdn = host

        return ipv6obj


class HostRecord(IPAllocationObject):
    def __init__(self):
        self.infoblox_type = 'record:host'
        self.ips = []
        self.ref = None
        self.name = None
        self.dns_view = None

    def __repr__(self):
        return "HostRecord{0}".format(self.to_dict())

    @property
    def zone_auth(self):
        return self._zone_auth

    @zone_auth.setter
    def zone_auth(self, value):
        if value:
            self._zone_auth = value.lstrip('.')

    def __eq__(self, other):
        return (isinstance(other, self.__class__) and
                self.ips == other.ips and
                self.name == other.name and
                self.dns_view == other.dns_view)


class HostRecordIPv6(HostRecord):
    """Sample Infoblox host record object in JSON format:
    {
        "_ref": "record:host/ZG5zLmhvc3QkLjY3OC5jb20uZ2xvYmFsLmNsb3VkLnRl
                 :test_host_name.testsubnet.cloud.global.com/
                 default.687401e9f7a7471abbf301febf99854e",
        "ipv4addrs": [
            {
                "_ref": "record:host_ipv4addr/ZG5zLmhvc3RfYWRkcmVzcyQuNjc4L
                         :192.168.0.5/
                         test_host_name.testsubnet.cloud.global.com/
                         default.687401e9f7a7471abbf301febf99854e",
                "configure_for_dhcp": false,
                "host": "test_host_name.testsubnet.cloud.global.com",
                "ipv4addr": "192.168.0.5",
                "mac": "aa:bb:cc:dd:ee:ff"
            }
        ]
    }
    """
    return_fields = ['ipv6addrs']

    def to_dict(self):
        result = {
            'view': self.dns_view,
            'name': '.'.join([self.hostname, self.zone_auth]),
        }

        result['ipv6addrs'] = [{
            'configure_for_dhcp': True,
            'ipv6addr': self.ip,
            'duid': '00:03:00:01:%s' % self.mac
        }]

        return result

    @staticmethod
    def from_dict(hr_dict):
        ipv6addrs = hr_dict.get('ipv6addrs', None)
        if not ipv6addrs:
            raise ib_exc.HostRecordNoIPv6Addrs()

        ipv6addr = ipv6addrs[0]
        ip = ipv6addr['ipv6addr']
        if not is_valid_ip(ip):
            raise ib_exc.InfobloxInvalidIp(ip=ip)
        host = ipv6addr.get('host', 'unknown.unknown')
        mac = ipv6addr.get('mac')

        hostname, _, dns_zone = host.partition('.')

        host_record = HostRecordIPv6()
        host_record.hostname = hostname
        host_record.zone_auth = dns_zone
        host_record.mac = mac
        host_record.ip = ip
        host_record.ref = hr_dict.get('_ref')

        return host_record

    @property
    def ip(self):
        if self.ips:
            return self.ips[0].ip

    @ip.setter
    def ip(self, ip_address):
        if self.ips:
            self.ips[0].ip = ip_address
        else:
            ip_obj = IPv4()
            ip_obj.ip = ip_address

            self.ips.append(ip_obj)

    @property
    def mac(self):
        if self.ips:
            return self.ips[0].mac

    @mac.setter
    def mac(self, mac_address):
        if self.ips:
            self.ips[0].mac = mac_address
        else:
            ip_obj = IPv4()
            ip_obj.mac = mac_address
            self.ips.append(ip_obj)

    @property
    def hostname(self):
        if self.ips:
            return self.ips[0].hostname

    @hostname.setter
    def hostname(self, name):
        if self.ips:
            self.ips[0].hostname = name
        else:
            ip_obj = IPv4()
            ip_obj.hostname = name
            self.ips.append(ip_obj)


class HostRecordIPv4(HostRecord):
    """Sample Infoblox host record object in JSON format:
    {
        "_ref": "record:host/ZG5zLmhvc3QkLjY3OC5jb20uZ2xvYmFsLmNsb3VkLnRl
                 :test_host_name.testsubnet.cloud.global.com/
                 default.687401e9f7a7471abbf301febf99854e",
        "ipv4addrs": [
            {
                "_ref": "record:host_ipv4addr/ZG5zLmhvc3RfYWRkcmVzcyQuNjc4L
                         :192.168.0.5/
                         test_host_name.testsubnet.cloud.global.com/
                         default.687401e9f7a7471abbf301febf99854e",
                "configure_for_dhcp": false,
                "host": "test_host_name.testsubnet.cloud.global.com",
                "ipv4addr": "192.168.0.5",
                "mac": "aa:bb:cc:dd:ee:ff"
            }
        ]
    }
    """
    return_fields = ['ipv4addrs']
    def __init__(self):
        self.infoblox_type = 'record:host'
        self.ips = []
        self.ref = None
        self.name = None
        self.dns_view = None

    def __repr__(self):
        return "HostRecord({})".format(self.to_dict())

    def __eq__(self, other):
        return (isinstance(other, self.__class__) and
                self.ips == other.ips and
                self.name == other.name and
                self.dns_view == other.dns_view)

    @property
    def ip(self):
        if self.ips:
            return self.ips[0].ip

    @ip.setter
    def ip(self, ip_address):
        if self.ips:
            self.ips[0].ip = ip_address
        else:
            ip_obj = IPv4()
            ip_obj.ip = ip_address

            self.ips.append(ip_obj)

    @property
    def mac(self):
        if self.ips:
            return self.ips[0].mac

    @mac.setter
    def mac(self, mac_address):
        if self.ips:
            self.ips[0].mac = mac_address
        else:
            ip_obj = IPv4()
            ip_obj.mac = mac_address
            self.ips.append(ip_obj)

    @property
    def hostname(self):
        if self.ips:
            return self.ips[0].hostname

    @hostname.setter
    def hostname(self, name):
        if self.ips:
            self.ips[0].hostname = name
        else:
            ip_obj = IPv4()
            ip_obj.hostname = name
            self.ips.append(ip_obj)

    def to_dict(self):
        result = {
            'view': self.dns_view,
            'name': '.'.join([self.hostname, self.zone_auth]),
            'ipv4addrs': [ip.to_dict() for ip in self.ips]
        }

        return result

    @staticmethod
    def from_dict(hr_dict):
        ipv4addrs = hr_dict.get('ipv4addrs', None)
        if not ipv4addrs:
            raise ib_exc.HostRecordNoIPv4Addrs()

        ipv4addr = ipv4addrs[0]
        ip = ipv4addr['ipv4addr']
        if not is_valid_ip(ip):
            raise ib_exc.InfobloxInvalidIp(ip=ip)
        host = ipv4addr.get('host', 'unknown.unknown')
        mac = ipv4addr.get('mac')
        hostname, _, dns_zone = host.partition('.')

        host_record = HostRecordIPv4()
        host_record.hostname = hostname
        host_record.zone_auth = dns_zone
        host_record.ref = hr_dict.get('_ref')
        host_record.ips = [IPv4.from_dict(ip) for ip in ipv4addrs]

        return host_record


class FixedAddress(IPAllocationObject):
    def __init__(self):
        self.infoblox_type = 'fixedaddress'
        self.ip = None
        self.net_view = None
        self.mac = None
        self.duid = None
        self.extattrs = None
        self.ref = None

    def __repr__(self):
        return "FixedAddress({0})".format(self.to_dict())


class FixedAddressIPv4(FixedAddress):
    infoblox_type = 'fixedaddress'
    return_fields = [
        'ipv4addr',
        'mac',
        'network_view',
        'extattrs'
    ]

    def to_dict(self):
        return {
            'mac': self.mac,
            'network_view': self.net_view,
            'ipv4addr': self.ip,
            'extattrs': self.extattrs
        }

    @staticmethod
    def from_dict(fixed_address_dict):
        ip = fixed_address_dict.get('ipv4addr')
        if not is_valid_ip(ip):
            raise ib_exc.InfobloxInvalidIp(ip=ip)

        fa = FixedAddress()
        fa.ip = ip
        fa.mac = fixed_address_dict.get('mac')
        fa.net_view = fixed_address_dict.get('network_view')
        fa.extattrs = fixed_address_dict.get('extattrs')
        fa.ref = fixed_address_dict.get('_ref')

        return fa


class FixedAddressIPv6(FixedAddress):
    infoblox_type = 'ipv6fixedaddress'
    return_fields = [
        'ipv6addr',
        'duid',
        'network_view',
        'extattrs'
    ]

    def to_dict(self):
        return {
            'duid': '00:03:00:01:%s' % self.mac,
            'network_view': self.net_view,
            'ipv6addr': self.ip,
            'extattrs': self.extattrs
        }

    @staticmethod
    def from_dict(fixed_address_dict):
        ip = fixed_address_dict.get('ipv6addr')
        if not is_valid_ip(ip):
            raise ib_exc.InfobloxInvalidIp(ip=ip)

        fa = FixedAddress()
        fa.ip = ip
        fa.mac = fixed_address_dict.get('mac')
        fa.net_view = fixed_address_dict.get('network_view')
        fa.extattrs = fixed_address_dict.get('extattrs')
        fa.ref = fixed_address_dict.get('_ref')

        return fa


class Member(object):
    def __init__(self, ip, name, ipv6=None):
        self.ip = ip
        self.ipv6 = ipv6
        self.name = name

    def __eq__(self, other):
        return self.ip == other.ip and self.name == other.name

    def __repr__(self):
        return 'Member(IP={ip}, IPv6={ipv6}, name={name})'.format(
            ip=self.ip,
            ipv6=self.ipv6,
            name=self.name)
