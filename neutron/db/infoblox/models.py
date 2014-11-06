# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (c) 2012 OpenStack Foundation.
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

import sqlalchemy as sa

from neutron.db import model_base
from neutron.db import models_v2


DHCP_MEMBER_TYPE = 'dhcp'
DNS_MEMBER_TYPE = 'dns'


class InfobloxDNSMember(model_base.BASEV2, models_v2.HasId):
    __tablename__ = 'infoblox_dns_members'

    network_id = sa.Column(sa.String(36), sa.ForeignKey('networks.id',
                                                        ondelete="CASCADE"))
    server_ip = sa.Column(sa.String(40))
    server_ipv6 = sa.Column(sa.String(40))


class InfobloxDHCPMember(model_base.BASEV2, models_v2.HasId):
    __tablename__ = 'infoblox_dhcp_members'

    network_id = sa.Column(sa.String(36), sa.ForeignKey('networks.id',
                                                        ondelete="CASCADE"))
    server_ip = sa.Column(sa.String(40))
    server_ipv6 = sa.Column(sa.String(40))


class InfobloxMemberMap(model_base.BASEV2):
    """Maps Neutron object to Infoblox member.

    map_id may point to Network ID, Tenant ID or Infoblox network view name
    depending on configuration. Infoblox member names are unique.
    """
    __tablename__ = 'infoblox_member_maps'

    member_name = sa.Column(sa.String(255), nullable=False, primary_key=True)
    map_id = sa.Column(sa.String(255), nullable=False)
    member_type = sa.Column(sa.String(10))


class InfobloxNetViews(model_base.BASEV2):
    """Connects Infoblox network views with Openstack networks.
    This is needed to properly delete network views in NIOS on network
    delete
    """

    __tablename__ = 'infoblox_net_views'

    network_id = sa.Column(sa.String(36), sa.ForeignKey("networks.id",
                                                        ondelete="CASCADE"),
                           nullable=False, primary_key=True)
    network_view = sa.Column(sa.String(56))


class InfobloxManagementNetIps(model_base.BASEV2):
    """Holds IP addresses allocated on management network for DHCP relay
    interface
    """

    __tablename__ = 'infoblox_mgmt_net_ips'

    network_id = sa.Column(sa.String(length=255), primary_key=True)
    ip_address = sa.Column(sa.String(length=64), nullable=False)
    fixed_address_ref = sa.Column(sa.String(length=255), nullable=False)
