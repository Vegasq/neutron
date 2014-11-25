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

import abc

from oslo.config import cfg
import six


@six.add_metaclass(abc.ABCMeta)
class IPAllocator(object):

    def __init__(self, infoblox):
        self.infoblox = infoblox

    @abc.abstractmethod
    def allocate_ip_from_range(self, dnsview_name, networkview_name, zone_auth,
                               hostname, mac, first_ip, last_ip,
                               extattrs=None):
        pass

    @abc.abstractmethod
    def allocate_given_ip(self, netview_name, dnsview_name, zone_auth,
                          hostname, mac, ip, extattrs=None):
        pass

    @abc.abstractmethod
    def deallocate_ip(self, network_view, dns_view_name, ip):
        pass

    @abc.abstractmethod
    def bind_names(self, dnsview_name, ip, name):
        pass

    @abc.abstractmethod
    def unbind_names(self, dnsview_name, ip, name):
        pass

    @abc.abstractmethod
    def update_extattrs(self, network_view, dns_view, ip, extattrs):
        pass


class HostRecordIPAllocator(IPAllocator):
    def bind_names(self, dnsview_name, ip, name):
        # See OPENSTACK-181. In case hostname already exists on NIOS, update
        # host record which contains that hostname with the new IP address
        # rather than creating a separate host record object
        reserved_hostname_hr = self.infoblox.find_hostname(dnsview_name, name)
        reserved_ip_hr = self.infoblox.get_host_record(dnsview_name, ip)

        if reserved_hostname_hr == reserved_ip_hr:
            return

        if reserved_hostname_hr:
            for hr_ip in reserved_ip_hr.ips:
                if hr_ip == ip:
                    self.infoblox.delete_host_record(dnsview_name, ip)
                    self.infoblox.add_ip_to_record(reserved_hostname_hr,
                                                   ip,
                                                   hr_ip.mac)
                    break
        else:
            self.infoblox.bind_name_with_host_record(dnsview_name, ip, name)

    def unbind_names(self, dnsview_name, ip, name):
        # Nothing to delete, all will be deleted together with host record.
        pass

    def allocate_ip_from_range(self, dnsview_name, networkview_name, zone_auth,
                               hostname, mac, first_ip, last_ip,
                               extattrs=None):
        hr = self.infoblox.create_host_record_from_range(
            dnsview_name, networkview_name, zone_auth, hostname, mac,
            first_ip, last_ip)
        return hr.ips[-1].ip

    def allocate_given_ip(self, netview_name, dnsview_name, zone_auth,
                          hostname, mac, ip, extattrs=None):
        hr = self.infoblox.create_host_record_for_given_ip(
            dnsview_name, zone_auth, hostname, mac, ip)
        return hr.ips[-1].ip

    def deallocate_ip(self, network_view, dns_view_name, ip):
        host_record = self.infoblox.get_host_record(dns_view_name, ip)

        if len(host_record.ips) > 1:
            self.infoblox.delete_ip_from_host_record(host_record, ip)
        else:
            self.infoblox.delete_host_record(dns_view_name, ip)

    def update_extattrs(self, network_view, dns_view, ip, extattrs):
        self.infoblox.update_host_record_eas(dns_view, ip, extattrs)


class FixedAddressIPAllocator(IPAllocator):
    def bind_names(self, dnsview_name, ip, name):
        self.infoblox.bind_name_with_record_a(dnsview_name, ip, name)

    def unbind_names(self, dnsview_name, ip, name):
        self.infoblox.unbind_name_from_record_a(dnsview_name, ip, name)

    def allocate_ip_from_range(self, dnsview_name, networkview_name, zone_auth,
                               hostname, mac, first_ip, last_ip,
                               extattrs=None):
        fa = self.infoblox.create_fixed_address_from_range(
            networkview_name, mac, first_ip, last_ip, extattrs)
        return fa.ip

    def allocate_given_ip(self, netview_name, dnsview_name, zone_auth,
                          hostname, mac, ip, extattrs=None):
        fa = self.infoblox.create_fixed_address_for_given_ip(
            netview_name, mac, ip, extattrs)
        return fa.ip

    def deallocate_ip(self, network_view, dns_view_name, ip):
        self.infoblox.delete_fixed_address(network_view, ip)

    def update_extattrs(self, network_view, dns_view, ip, extattrs):
        self.infoblox.update_fixed_address_eas(network_view, ip, extattrs)
        self.infoblox.update_dns_record_eas(dns_view, ip, extattrs)


def get_ip_allocator(obj_manipulator):
    if cfg.CONF.use_host_records_for_ip_allocation:
        return HostRecordIPAllocator(obj_manipulator)
    else:
        return FixedAddressIPAllocator(obj_manipulator)
