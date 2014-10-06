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

import io
import logging
import operator

from oslo.config import cfg as neutron_conf

from neutron.db.infoblox import infoblox_db as ib_db
from neutron.db.infoblox import models as ib_models
from neutron.ipam.drivers.infoblox import exceptions
from neutron.ipam.drivers.infoblox import objects
from neutron.openstack.common import jsonutils

LOG = logging.getLogger(__name__)
OPTS = [
    neutron_conf.StrOpt('conditional_config', default=None,
                        help=_("Infoblox conditional config path")),
    neutron_conf.StrOpt('infoblox_members_config', default=None,
                        help=_("Path to infoblox members config file."))
]

neutron_conf.CONF.register_opts(OPTS)


class ConfigFinder(object):
    VALID_STATIC_CONDITIONS = ['global', 'tenant']
    VALID_VARIABLE_CONDITIONS = ['tenant_id:', 'subnet_range:']
    VALID_CONDITIONS = VALID_STATIC_CONDITIONS + VALID_VARIABLE_CONDITIONS

    def __init__(self, stream=None, member_manager=None):
        """Reads config from `io.IOBase`:stream:. Config is JSON format."""
        if not member_manager:
            member_manager = MemberManager()
        if not stream:
            config_file = neutron_conf.CONF.conditional_config
            if not config_file:
                raise exceptions.ConfigNotFound(object='conditional config')
            stream = io.FileIO(config_file)

        self.member_manager = member_manager

        with stream:
            try:
                self.conf = jsonutils.loads(stream.read())
                self._validate_conditions()
            except ValueError as e:
                raise exceptions.InfobloxInvalidConditionalConfig(msg=e)

    def find_config_for_subnet(self, context, subnet):
        """
        Returns first configuration which matches the object being created.
        :param context:
        :param subnet:
        :return: :raise exceptions.InfobloxNoConfigFoundForSubnet:
        """
        for cfg in self.conf:
            cfg = Config(cfg, context, subnet, self.member_manager)
            if self._condition_matches(context, cfg, subnet):
                return cfg

        raise exceptions.InfobloxNoConfigFoundForSubnet(subnet=subnet)

    @staticmethod
    def _variable_condition_match(condition, var, expected):
        return (condition.startswith(var) and
                condition.split(':')[1] == expected)

    def _condition_matches(self, context, config, subnet):
        net_id = subnet.get('network_id', subnet.get('id'))
        cidr = subnet.get('cidr')
        tenant_id = subnet['tenant_id']

        is_external = ib_db.is_network_external(context, net_id)
        cond = config.condition
        condition_matches = (
            cond == 'global' or cond == 'tenant' or
            self._variable_condition_match(cond, 'tenant_id', tenant_id) or
            self._variable_condition_match(cond, 'subnet_range', cidr))

        return config.is_external == is_external and condition_matches

    def _validate_conditions(self):
        # Define lambdas to check
        is_static_cond = lambda cond, static_conds: cond in static_conds
        is_var_cond = lambda cond, var_conds: any([cond.startswith(valid)
                                                  for valid in var_conds])
        for conf in self.conf:
            # If condition contain colon: validate it as variable
            if ':' in conf['condition'] and\
               is_var_cond(conf['condition'],
                           self.VALID_VARIABLE_CONDITIONS):
                pass
            # If not: validate it as static
            elif is_static_cond(conf['condition'],
                                self.VALID_STATIC_CONDITIONS):
                pass
            # If any of previous checker cannot validate value - rise error
            else:
                msg = 'Invalid condition specified: {}'.format(
                      conf['condition'])
                raise exceptions.InfobloxInvalidConditionalConfig(msg=msg)


class PatternBuilder(object):
    def __init__(self, *pattern):
        self.pattern = '.'.join([el.strip('.')
                                 for el in pattern if el is not None])

    def build(self, context, subnet, port=None, ip_addr=None):
        """
        Builds string by passing supplied values into pattern
        :raise exceptions.InvalidPattern:
        """
        self._validate_pattern()

        subnet_name = subnet['name'] if subnet['name'] else subnet['id']

        pattern_dict = {
            'network_id': subnet['network_id'],
            'network_name': ib_db.get_network_name(context, subnet),
            'tenant_id': subnet['tenant_id'],
            'subnet_name': subnet_name,
            'subnet_id': subnet['id'],
            'user_id': context.user_id
        }

        if ip_addr:
            octets = ip_addr.split('.')
            pattern_dict['ip_address'] = ip_addr.replace('.', '-')
            for i in xrange(len(octets)):
                octet_key = 'ip_address_octet{i}'.format(i=(i + 1))
                pattern_dict[octet_key] = octets[i]

        if port:
            pattern_dict['port_id'] = port['id']
            pattern_dict['instance_id'] = port['device_id']

        try:
            fqdn = self.pattern.format(**pattern_dict)
        except (KeyError, IndexError) as e:
            raise exceptions.InvalidPattern(msg=e)

        return fqdn

    def _validate_pattern(self):
        invalid_values = ['..']
        for val in invalid_values:
            if val in self.pattern:
                error_message = "Invalid value {}".format(val)
                raise exceptions.InvalidPattern(msg=error_message)


class Config(object):
    NEXT_AVAILABLE_MEMBER = '<next-available-member>'
    NETWORK_VIEW_TEMPLATES = ['{tenant_id}',
                              '{network_name}',
                              '{network_id}']

    DEFINING_ATTRS = ['condition', '_dhcp_members', '_dns_members',
                      '_net_view', '_dns_view']

    def __init__(self, config_dict, context, subnet,
                 member_manager=None):
        if not member_manager:
            member_manager = MemberManager()

        if 'condition' not in config_dict:
            raise exceptions.InfobloxInvalidConditionalConfig(
                msg="Missing mandatory 'condition' option")

        self.condition = config_dict['condition']
        self.is_external = config_dict.get('is_external', False)

        self._cached_network_view = None

        self._net_view = config_dict.get('network_view', 'default')
        self._dns_view = config_dict.get('dns_view')

        self.require_dhcp_relay = config_dict.get('require_dhcp_relay', False)

        self._dhcp_members = config_dict.get('dhcp_members',
                                             self.NEXT_AVAILABLE_MEMBER)
        self._dns_members = config_dict.get('dns_members')

        self.domain_suffix_pattern = config_dict.get(
            'domain_suffix_pattern', 'global.com')
        self.hostname_pattern = config_dict.get(
            'hostname_pattern', 'host-{ip_address}.{subnet_name}')

        self.network_template = config_dict.get('network_template')
        self.ns_group = config_dict.get('ns_group')

        self.context = context
        self.subnet = subnet
        self.member_manager = member_manager

    def __eq__(self, other):
        return (isinstance(other, self.__class__) and
                all(map(lambda attr:
                        getattr(self, attr) == getattr(other, attr),
                        self.DEFINING_ATTRS)))

    def __hash__(self):
        return hash(tuple(self.DEFINING_ATTRS))

    def __repr__(self):
        values = {
            'condition': self.condition,
            'dns_members': self._dns_members,
            'dhcp_members': self._dhcp_members,
            'net_view': self._net_view,
            'dns_view': self._dns_view
        }

        return "ConditionalConfig({})".format(values)

    @property
    def network_view(self):
        if self._cached_network_view is not None:
            # do all the heavy stuff once
            return self._cached_network_view

        if (self._net_view.startswith('{') and
                self._net_view not in self.NETWORK_VIEW_TEMPLATES):
            raise exceptions.InfobloxInvalidConditionalConfig(
                msg="Invalid value for 'network_view'")

        if self._net_view == '{tenant_id}':
            self._cached_network_view = self.subnet['tenant_id']
        elif self._net_view == '{network_name}':
            self._cached_network_view = ib_db.get_network_name(
                self.context, self.subnet)
        elif self._net_view == '{network_id}':
            self._cached_network_view = self.subnet['network_id']
        else:
            self._cached_network_view = self._net_view

        return self._cached_network_view

    @property
    def dns_view(self):
        if self._dns_view:
            return self._dns_view

        if self.network_view and self.network_view != 'default':
            return '.'.join(['default', self.network_view])
        return 'default'

    @property
    def dhcp_members(self):
        return self._get_members(ib_models.DHCP_MEMBER_TYPE)

    @property
    def dns_members(self):
        return self._get_members(ib_models.DNS_MEMBER_TYPE)

    @property
    def is_global_config(self):
        return self.condition == 'global'

    def reserve_dns_members(self):
        reserved_members = self._reserve_member(self._dns_members,
                                                self.ns_group,
                                                ib_models.DNS_MEMBER_TYPE)

        if isinstance(reserved_members, list):
            return reserved_members
        elif reserved_members:
            return [reserved_members]
        else:
            return []

    def reserve_dhcp_members(self):
        reserved_members = self._reserve_member(self._dhcp_members,
                                                self.network_template,
                                                ib_models.DHCP_MEMBER_TYPE)
        # use DHCP member for DNS if DNS is not set
        if self._dns_members is None:
            self._dns_members = self._dhcp_members
            self._reserve_member(self._dhcp_members,
                                 self.network_template,
                                 ib_models.DNS_MEMBER_TYPE)

        if isinstance(reserved_members, list):
            return reserved_members
        else:
            return [reserved_members]

    def requires_net_view(self):
        return not self.is_external

    def verify_subnet_update_is_allowed(self):
        """
        Subnet update procedure is not allowed if Infoblox zone name exists on
        NIOS. This can only happen if domain suffix pattern has subnet name
        included.
        """
        subnet_name = self.subnet.get('name')
        pattern = self.domain_suffix_pattern
        update_allowed = not (subnet_name is not None and
                              '{subnet_name}' in pattern)

        if not update_allowed:
            raise exceptions.OperationNotAllowed(
                reason="subnet_name is in domain name pattern")

    def _get_members(self, member_type):
        members = self.member_manager.find_members(
            self.context, self.network_view, member_type)

        if members:
            return members

        msg = ("Looks like you're trying to call config.{member_type}_member "
               "without reserving one. You should call "
               "reserve_{member_type}_member() "
               "first!".format(member_type=member_type))
        raise RuntimeError(msg)

    def _reserve_members_list(self, members, member_type):
        members_to_reserve = [self.member_manager.get_member(member)
                              for member in members]
        for member in members_to_reserve:
            self.member_manager.reserve_member(self.context,
                                               self.network_view,
                                               member.name,
                                               member_type)
        return members_to_reserve

    def _reserve_by_template(self, members, template, member_type):
        member = self._get_member_from_template(members, template)
        self.member_manager.reserve_member(self.context,
                                           self.network_view,
                                           member.name,
                                           member_type)
        return member

    def _reserve_next_avaliable(self, members, member_type):
        member = self.member_manager.next_available(self.context,
                                                    members,
                                                    member_type)
        self.member_manager.reserve_member(self.context,
                                           self.network_view,
                                           member.name,
                                           member_type)
        return member

    def _reserve_member(self, members, template, member_type):
        member = self.member_manager.find_members(self.context,
                                                  self.network_view,
                                                  member_type)

        if member:
            return member

        if members == self.NEXT_AVAILABLE_MEMBER:
            return self._reserve_next_avaliable(members, member_type)
        elif isinstance(members, list):
            return self._reserve_members_list(members, member_type)
        elif template:
            return self._reserve_by_template(members,
                                             template,
                                             member_type)

    def _get_member_from_template(self, members, template):
        member_defined = (members != self.NEXT_AVAILABLE_MEMBER and
                          isinstance(members, basestring))
        if template and not member_defined:
            msg = 'Member MUST be configured for {template}'.format(
                template=template)
            raise exceptions.InfobloxInvalidConditionalConfig(msg=msg)
        return self.member_manager.get_member(members)


class MemberManager(object):
    def __init__(self, member_config_stream=None):
        if not member_config_stream:
            config_file = neutron_conf.CONF.infoblox_members_config
            if not config_file:
                raise exceptions.ConfigNotFound(object='Infoblox members')

            member_config_stream = io.FileIO(config_file)
        with member_config_stream:
            all_members = jsonutils.loads(member_config_stream.read())

            try:
                self.available_members = map(
                    lambda m: objects.Member(name=m['name'], ip=m['ipv4addr']),
                    filter(lambda m: m.get('is_available', True), all_members))
            except KeyError as key:
                raise exceptions.InvalidMemberConfig(key=key)

    def next_available(self, context,
                       members_to_choose_from=Config.NEXT_AVAILABLE_MEMBER,
                       member_type=ib_models.DHCP_MEMBER_TYPE):
        if members_to_choose_from == Config.NEXT_AVAILABLE_MEMBER:
            members_to_choose_from = map(operator.attrgetter('name'),
                                         self.available_members)

        already_reserved = ib_db.get_used_members(context, member_type)
        for member in members_to_choose_from:
            if member not in already_reserved:
                return self.get_member(member)
        raise exceptions.NoInfobloxMemberAvailable()

    def reserve_member(self, context, mapping, member_name, member_type):
        ib_db.attach_member(context, mapping, member_name, member_type)

    def release_member(self, context, mapping):
        ib_db.delete_members(context, mapping)

    def get_member(self, member_name):
        for member in self.available_members:
            if member.name == member_name:
                return member
        raise exceptions.NoInfobloxMemberAvailable()

    def _get_reserved_conf_members(self, exists_members):
        members = []

        if not exists_members:
            return members

        for exists_member in exists_members:
            for member in self.available_members:
                if member.name == exists_member:
                    members.append(member)

        if not members:
            raise exceptions.ReservedMemberNotAvailableInConfig(
                member_name=", ".join(exists_members),
                config=neutron_conf.CONF.infoblox_members_config)

        return members

    def find_members(self, context, mapping, member_type):
        exists_members = ib_db.get_members(context, mapping, member_type)
        members = self._get_reserved_conf_members(exists_members)
        return members
