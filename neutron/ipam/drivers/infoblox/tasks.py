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
import operator
import logging

from taskflow import task


LOG = logging.getLogger(__name__)

class CreateNetViewTask(task.Task):
    def execute(self, obj_manip, net_view_name):
        obj_manip.create_network_view(net_view_name)

    def revert(self, obj_manip, net_view_name, **kwargs):
        if not obj_manip.has_networks(net_view_name):
            obj_manip.delete_network_view(net_view_name)


class CreateNetworkTask(task.Task):
    def execute(self, obj_manip, net_view_name, cidr, nameservers, dhcp_member,
                gateway_ip, network_extattrs, related_members, dhcp_trel_ip,
                ip_version, ipv6_ra_mode, ipv6_address_mode):
        obj_manip.create_network(net_view_name, cidr, nameservers,
                                 dhcp_member, gateway_ip, dhcp_trel_ip,
                                 network_extattrs)
        for member in related_members:
            obj_manip.restart_all_services(member)

    def revert(self, obj_manip, net_view_name, cidr, **kwargs):
        obj_manip.delete_network(net_view_name, cidr)


class CreateNetworkFromTemplateTask(task.Task):
    def execute(self, obj_manip, net_view_name, cidr, template,
                network_extattrs):
        obj_manip.create_network_from_template(
            net_view_name, cidr, template, network_extattrs)

    def revert(self, obj_manip, net_view_name, cidr, **kwargs):
        obj_manip.delete_network(net_view_name, cidr)


class CreateIPRange(task.Task):
    def execute(self, obj_manip, net_view_name, start_ip, end_ip, disable,
                cidr, ip_version, ipv6_ra_mode, ipv6_address_mode):
        obj_manip.create_ip_range(net_view_name, start_ip, end_ip,
                                  cidr, disable)

    def revert(self, obj_manip, net_view_name, start_ip, end_ip,
                ip_version, ipv6_ra_mode, ipv6_address_mode, **kwargs):
        obj_manip.delete_ip_range(net_view_name, start_ip, end_ip)


class CreateDNSViewTask(task.Task):
    def execute(self, obj_manip, net_view_name, dns_view_name):
        obj_manip.create_dns_view(net_view_name, dns_view_name)

    def revert(self, **kwargs):
        # never delete DNS view
        pass


class CreateDNSZonesTask(task.Task):
    def execute(self, obj_manip, dnsview_name, fqdn, dns_member,
                secondary_dns_members, **kwargs):
        obj_manip.create_dns_zone(dnsview_name, fqdn, dns_member,
                                  secondary_dns_members)

    def revert(self, obj_manip, dnsview_name, fqdn, **kwargs):
        obj_manip.delete_dns_zone(dnsview_name, fqdn)


class CreateDNSZonesTaskCidr(task.Task):
    def execute(self, obj_manip, dnsview_name, cidr, dns_member, zone_format,
                secondary_dns_members, **kwargs):
        obj_manip.create_dns_zone(dnsview_name, cidr, dns_member,
                                  secondary_dns_members,
                                  zone_format=zone_format)

    def revert(self, obj_manip, dnsview_name, cidr, **kwargs):
        obj_manip.delete_dns_zone(dnsview_name, cidr)


class CreateDNSZonesFromNSGroupTask(task.Task):
    def execute(self, obj_manip, dnsview_name, fqdn, ns_group, **kwargs):
        obj_manip.create_dns_zone(dnsview_name, fqdn, ns_group=ns_group)

    def revert(self, obj_manip, dnsview_name, fqdn, **kwargs):
        obj_manip.delete_dns_zone(dnsview_name, fqdn)


class CreateDNSZonesCidrFromNSGroupTask(task.Task):
    def execute(self, obj_manip, dnsview_name, cidr, ns_group, zone_format,
                **kwargs):
        obj_manip.create_dns_zone(dnsview_name, cidr,
                                  ns_group=ns_group,
                                  zone_format=zone_format)

    def revert(self, obj_manip, dnsview_name, cidr, **kwargs):
        obj_manip.delete_dns_zone(dnsview_name, cidr)
