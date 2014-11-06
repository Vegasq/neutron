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

import taskflow.engines
from taskflow.patterns import linear_flow

from neutron.db.infoblox import models
from neutron.ipam.drivers.infoblox import config
from neutron.ipam.drivers.infoblox import connector
from neutron.ipam.drivers.infoblox import dns_controller
from neutron.ipam.drivers.infoblox import ip_allocator
from neutron.ipam.drivers.infoblox import ipam_controller
from neutron.ipam.drivers.infoblox import object_manipulator
from neutron.ipam.drivers import neutron_ipam


class FlowContext(object):
    def __init__(self, neutron_context, flow_name):
        self.parent_flow = linear_flow.Flow(flow_name)
        self.context = neutron_context
        self.store = {}

    def __getattr__(self, item):
        return getattr(self.context, item)


class InfobloxIPAM(neutron_ipam.NeutronIPAM):
    def __init__(self):
        super(InfobloxIPAM, self).__init__()

        config_finder = config.ConfigFinder()
        obj_manipulator = object_manipulator.InfobloxObjectManipulator(
            connector=connector.Infoblox())
        ip_alloc = ip_allocator.get_ip_allocator(obj_manipulator)

        self.ipam_controller = ipam_controller.InfobloxIPAMController(
            config_finder=config_finder,
            obj_manip=obj_manipulator,
            ip_allocator=ip_alloc)

        self.dns_controller = dns_controller.InfobloxDNSController(
            config_finder=config_finder,
            manipulator=obj_manipulator,
            ip_allocator=ip_alloc
        )

    def create_subnet(self, context, subnet):
        context = FlowContext(context, 'create-subnet')
        context.store['subnet'] = subnet

        retval = super(InfobloxIPAM, self).create_subnet(context, subnet)

        taskflow.engines.run(context.parent_flow, store=context.store)

        return retval

    def _collect_members_ips(self, context, network, model):
        members = context.session.query(model)
        result = members.filter_by(network_id=network['id'])
        ip_list = []
        ipv6_list = []
        for member in result:
            ip_list.append(member.server_ip)
            ipv6_list.append(member.server_ipv6)
        return (ip_list, ipv6_list)

    def get_additional_network_dict_params(self, ctx, network_id):
        network = self.ipam_controller._get_network(ctx, network_id)

        dns_list, dns_ipv6_list = self._collect_members_ips(
            ctx, network, models.InfobloxDNSMember)

        dhcp_list, dhcp_ipv6_list = self._collect_members_ips(
            ctx, network, models.InfobloxDHCPMember)

        ib_mgmt_ip = self.ipam_controller.ib_db.get_management_net_ip(
            ctx, network_id)

        return {
            'external_dhcp_servers': dhcp_list,
            'external_dns_servers': dns_list,
            'external_dhcp_ipv6_servers': dhcp_ipv6_list,
            'external_dns_ipv6_servers': dns_ipv6_list,
            'mgmt_iface_ip': ib_mgmt_ip
        }
