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

from oslo.config import cfg as neutron_conf
from taskflow.patterns import linear_flow

from neutron.db.infoblox import infoblox_db as infoblox_db
from neutron.ipam.drivers.infoblox import config
from neutron.ipam.drivers.infoblox import connector
from neutron.ipam.drivers.infoblox import constants as ib_constants
from neutron.ipam.drivers.infoblox import ea_manager
from neutron.ipam.drivers.infoblox import object_manipulator
from neutron.ipam.drivers.infoblox import tasks
from neutron.ipam.drivers import neutron_ipam
from neutron.openstack.common import log as logging

OPTS = [
    neutron_conf.StrOpt('private_dns_view_name',
                        default=None,
                        help=_("If single_network_view_name is specified, "
                               "this option will define DNS View name used "
                               "to serve networks from the single network "
                               "view. Otherwise it'signored and "
                               "'default.<netview_name>' is used.")),
    neutron_conf.StrOpt('external_dns_view_name',
                        default=None,
                        help=_("All the subnets created in external networks "
                               "will beassociated with DNS View with such "
                               "name. If not specified, name "
                               "'default.<netview_name>' will be used.")),
    neutron_conf.StrOpt('subnet_fqdn_suffix',
                        default='com',
                        help=_("Suffix for subnet domain name. Used to "
                               "generate subnet FQDN which is built using "
                               "the following pattern "
                               "<subnet_domain><subnet_fqdn_suffix>. "
                               "Subnet domain uniquely represents subnet and "
                               "equal to subnet name ifspecified, otherwise "
                               "equal to the first part of subnet uuid.")),
    neutron_conf.BoolOpt('use_global_dns_zone',
                         default=True,
                         help=_("Use global DNS zone. Global private DNS zone "
                                "only make sense when we use single network "
                                "view")),
]

LOG = logging.getLogger(__name__)
neutron_conf.CONF.register_opts(OPTS)


class InfobloxDNSController(neutron_ipam.NeutronDNSController):

    SUBDOMAIN_NAME_LEN = 8

    def __init__(self, ip_allocator, manipulator=None, config_finder=None):
        super(InfobloxDNSController, self).__init__()

        if not manipulator:
            manipulator = object_manipulator.InfobloxObjectManipulator(
                connector.Infoblox())

        self.infoblox = manipulator
        self.ip_allocator = ip_allocator
        self.config_finder = config_finder
        self.ea_manager = ea_manager.InfobloxEaManager(infoblox_db)
        self.pattern_builder = config.PatternBuilder

    def disassociate_floatingip(self, context, ip_address, port_id):
        subs = infoblox_db.get_subnets_by_port(context, port_id)
        port = infoblox_db.get_port_by_id(context, port_id)
        extattrs = self.ea_manager.get_extattrs_for_ip(context, port)
        del extattrs['VM ID']

        configs = set()
        for subnet in subs:
            configs.add(self.config_finder.find_config_for_subnet(context,
                                                                  subnet))

        for cfg in configs:
            self.infoblox.update_dns_record_eas(cfg.dns_view,
                                                ip_address.floating_ip_address,
                                                extattrs)

    def _get_hostname_pattern(self, port, cfg):

        port_owner = port['device_owner']
        if (port_owner
                in ib_constants.NEUTRON_DEVICE_OWNER_TO_PATTERN_MAP.keys()):
            return ib_constants.NEUTRON_DEVICE_OWNER_TO_PATTERN_MAP[port_owner]
        else:
            return cfg.hostname_pattern

    def _bind_names(self, context, backend_port, binding_func, extattrs=None):
        all_dns_members = []

        for ip in backend_port['fixed_ips']:
            subnet = self._get_subnet(context, ip['subnet_id'])
            cfg = self.config_finder.find_config_for_subnet(context, subnet)
            dns_members = cfg.reserve_dns_members()
            all_dns_members.extend(dns_members)
            ip_addr = ip['ip_address']

            hostname_pattern = self._get_hostname_pattern(backend_port, cfg)
            pattern_builder = self.pattern_builder(hostname_pattern,
                                                   cfg.domain_suffix_pattern)
            fqdn = pattern_builder.build(
                context, subnet, backend_port, ip_addr)

            binding_func(cfg.dns_view, ip_addr, fqdn)
            if extattrs:
                self.ip_allocator.update_extattrs(cfg.network_view,
                                                  cfg.dns_view,
                                                  ip_addr,
                                                  extattrs)

        for member in set(all_dns_members):
            self.infoblox.restart_all_services(member)

    def bind_names(self, context, backend_port):
        extattrs = self.ea_manager.get_extattrs_for_ip(context, backend_port)
        self._bind_names(context, backend_port, self.ip_allocator.bind_names,
                         extattrs)

    def unbind_names(self, context, backend_port):
        self._bind_names(context, backend_port, self.ip_allocator.unbind_names)

    def create_dns_zones(self, context, backend_subnet):
        cfg = self.config_finder.find_config_for_subnet(context,
                                                        backend_subnet)
        dns_members = cfg.reserve_dns_members()

        dns_zone = self.pattern_builder(cfg.domain_suffix_pattern).\
            build(context, backend_subnet)
        args = {
            'backend_subnet': backend_subnet,
            'dnsview_name': cfg.dns_view,
            'fqdn': dns_zone,
            'cidr': backend_subnet['cidr'],
            'zone_format': 'IPV4',
            'obj_manip': self.infoblox
        }
        create_dns_zones_flow = linear_flow.Flow('create-dns-zones')

        if cfg.ns_group:
            args['ns_group'] = cfg.ns_group
            create_dns_zones_flow.add(
                tasks.CreateDNSZonesFromNSGroupTask(),
                tasks.CreateDNSZonesCidrFromNSGroupTask(),
            )
        else:
            args['dns_member'] = dns_members[0]
            args['secondary_dns_members'] = dns_members[1:]
            create_dns_zones_flow.add(
                tasks.CreateDNSZonesTask(),
                tasks.CreateDNSZonesTaskCidr())

        context.store.update(args)
        context.parent_flow.add(create_dns_zones_flow)

    def delete_dns_zones(self, context, backend_subnet):
        cfg = self.config_finder.find_config_for_subnet(context,
                                                        backend_subnet)
        dns_zone_fqdn = self.pattern_builder(cfg.domain_suffix_pattern).\
            build(context, backend_subnet)
        dnsview_name = cfg.dns_view

        if not cfg.is_global_config:
            self.infoblox.delete_dns_zone(dnsview_name, dns_zone_fqdn)
        self.infoblox.delete_dns_zone(dnsview_name, backend_subnet['cidr'])


def has_nameservers(subnet):
    try:
        has_dns = iter(subnet['dns_nameservers']) is not None
    except (TypeError, KeyError):
        has_dns = False

    return has_dns


def get_nameservers(subnet):
    if has_nameservers(subnet):
        return subnet['dns_nameservers']
    return []


def build_fqdn(prefix, zone, ip_address):
    ip_address = ip_address.replace('.', '-')
    if zone:
        zone.lstrip('.')
    return "%(prefix)s%(ip_address)s.%(zone)s" % {
        'prefix': prefix,
        'ip_address': ip_address,
        'zone': zone
    }
