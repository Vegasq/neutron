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

from oslo.config import cfg
from sqlalchemy.orm import exc

from neutron.db import external_net_db
from neutron.db.infoblox import models
from neutron.db import l3_db
from neutron.db import models_v2
from neutron.openstack.common import log as logging

LOG = logging.getLogger(__name__)


def get_used_members(context, member_type):
    """Returns used names of members."""
    query = context.session.query(models.InfobloxMemberMap.member_name)
    members = query.filter_by(member_type=member_type).distinct()
    return [m.member_name for m in members]


def get_members(context, map_id, member_type):
    """Returns names of members used by currently used mapping (tenant id,
    network id or Infoblox netview name).
    """
    q = context.session.query(models.InfobloxMemberMap)

    members = q.filter_by(map_id=map_id, member_type=member_type).all()

    if members:
        return [member.member_name for member in members]

    return None


def attach_member(context, map_id, member_name, member_type):
    context.session.add(models.InfobloxMemberMap(map_id=map_id,
                                                 member_name=member_name,
                                                 member_type=member_type))


def delete_members(context, map_id):
    with context.session.begin(subtransactions=True):
        context.session.query(
            models.InfobloxMemberMap).filter_by(map_id=map_id).delete()


def is_last_subnet(context, subnet_id):
    q = context.session.query(models_v2.Subnet)
    return q.filter(models_v2.Subnet.id != subnet_id).count() == 0


def is_network_external(context, network_id):
    try:
        context.session.query(external_net_db.ExternalNetwork).filter_by(
            network_id=network_id).one()
        return True
    except exc.NoResultFound:
        return False


def delete_ip_allocation(context, network_id, subnet, ip_address):
    # Delete the IP address from the IPAllocate table
    subnet_id = subnet['id']
    LOG.debug(_("Delete allocated IP %(ip_address)s "
                "(%(network_id)s/%(subnet_id)s)"), locals())
    alloc_qry = context.session.query(
        models_v2.IPAllocation).with_lockmode('update')
    alloc_qry.filter_by(network_id=network_id,
                        ip_address=ip_address,
                        subnet_id=subnet_id).delete()


def get_subnets_by_network(context, network_id):
    subnet_qry = context.session.query(models_v2.Subnet)
    return subnet_qry.filter_by(network_id=network_id).all()


def get_subnets_by_port(context, port_id):
    allocs = (context.session.query(models_v2.IPAllocation).
              join(models_v2.Port).
              filter_by(id=port_id)
              .all())
    subnets = []

    subnet_qry = context.session.query(models_v2.Subnet)
    for allocation in allocs:
        subnets.append(subnet_qry.filter_by(id=allocation.subnet_id).first())
    return subnets


def get_port_by_id(context, port_id):
    query = context.session.query(models_v2.Port)
    return query.filter_by(id=port_id).one()


def get_network_name(context, subnet):
    q = context.session.query(models_v2.Network)
    net_name = q.join(models_v2.Subnet).filter(
        models_v2.Subnet.id == subnet['id']).first()

    if net_name:
        return net_name.name


def get_instance_id_by_floating_ip(context, floating_ip_id):
    try:
        query = context.session.query(l3_db.FloatingIP, models_v2.Port)
        query = query.filter(l3_db.FloatingIP.id == floating_ip_id)
        query = query.filter(models_v2.Port.id
                             == l3_db.FloatingIP.fixed_port_id)
        result = query.one()
    except exc.NoResultFound:
        return None

    return result.Port.device_id


def get_subnet_dhcp_port_address(context, subnet_id):
    dhcp_port = (context.session.query(models_v2.IPAllocation).
                 filter_by(subnet_id=subnet_id).
                 join(models_v2.Port).
                 filter_by(device_owner='network:dhcp')
                 .first())
    if dhcp_port:
        return dhcp_port.ip_address
    return None


def get_network_view(context, network_id):
    query = context.session.query(models.InfobloxNetViews)
    try:
        net_view = query.filter_by(network_id=network_id).one()
    except exc.NoResultFound:
        return None

    return net_view.network_view


def set_network_view(context, network_view, network_id):
    ib_net_view = models.InfobloxNetViews(network_id=network_id,
                                          network_view=network_view)

    # there should be only one NIOS network view per Openstack network
    query = context.session.query(models.InfobloxNetViews)
    obj = query.filter_by(network_id=network_id).first()
    if not obj:
        context.session.add(ib_net_view)


class NetworkL2InfoProvider(object):
    def __init__(self, plugin=None):
        """plugin - OpenStack core plugin
        This class is nessesary for providing information
        about network_type, physical_network and segmentation_id
        for each core plugin
        """
        if not plugin:
            self.plugin = cfg.CONF.core_plugin
        else:
            self.plugin = plugin

    def get_network_l2_info(self, session, network_id):
        segments = None
        l2_info = {'network_type': None,
                   'segmentation_id': None,
                   'physical_network': None}

        if self.plugin == 'neutron.plugins.ml2.plugin.Ml2Plugin':
            from neutron.plugins.ml2 import db as ml2_db

            segments = ml2_db.get_network_segments(session, network_id)[0]
        elif self.plugin == 'neutron.plugins.openvswitch.' \
                            'ovs_neutron_plugin.OVSNeutronPluginV2':
            from neutron.plugins.openvswitch import ovs_db_v2
            segments = ovs_db_v2.get_network_binding(session, network_id)

        if segments:
            for name, value in segments.iteritems():
                l2_info[name] = value

        return l2_info


def add_management_ip(context, network_id, fixed_address):
    context.session.add(models.InfobloxManagementNetIps(
        network_id=network_id,
        ip_address=fixed_address.ip,
        fixed_address_ref=fixed_address.ref))


def delete_management_ip(context, network_id):
    query = context.session.query(models.InfobloxManagementNetIps)
    query.filter_by(network_id=network_id).delete()


def get_management_ip_ref(context, network_id):
    query = context.session.query(models.InfobloxManagementNetIps)
    mgmt_ip = query.filter_by(network_id=network_id).first()

    return mgmt_ip.fixed_address_ref if mgmt_ip else None


def get_management_net_ip(context, network_id):
    query = context.session.query(models.InfobloxManagementNetIps)
    mgmt_ip = query.filter_by(network_id=network_id).first()

    return mgmt_ip.ip_address if mgmt_ip else None

def get_subnet(context, subnet_id):
    subnet_qry = context.session.query(models_v2.Subnet)
    return subnet_qry.filter_by(id=subnet_id).one()
