# Copyright 2014 OpenStack LLC.
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
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

from neutron.db import db_base_plugin_v2
from neutron.db import models_v2
from neutron.ipam.drivers.infoblox import connector
from neutron.ipam.drivers.infoblox import constants as ib_constants
from neutron.ipam.drivers.infoblox import exceptions
from neutron.ipam.drivers.infoblox import l2_driver
from neutron.openstack.common import log as logging

LOG = logging.getLogger(__name__)


class InfobloxEaManager(object):
    # CMP == cloud management platform
    OPENSTACK_OBJECT_FLAG = 'CMP Type'
    INFOBLOX_IS_SHARED = 'Is Shared'
    INFOBLOX_IS_EXTERNAL = 'Is External'

    def __init__(self, infoblox_db):
        # Passing this thru constructor to avoid cyclic imports
        self.db = infoblox_db
        self._network_l2_info_provider = l2_driver.L2Info()

    def get_extattrs_for_network(self, context, subnet=None, network=None):
        """
        Sets non-null values from subnet and network to corresponding EAs in
        NIOS
        :param context: current neutron context
        :param subnet: neutron subnet object
        :param network: neutron network object
        :return: dict with extensible attributes ready to be sent as part of
        NIOS WAPI
        """
        if subnet is None:
            subnet = {}
        if network is None:
            network = {}

        os_subnet_id = subnet.get('id')
        os_subnet_name = subnet.get('name')

        os_network_id = network.get('id')
        os_network_name = network.get('name')
        os_network_is_external = self.db.is_network_external(
            context, network.get('id'))
        os_network_is_shared = network.get('shared')
        os_network_l2_info = self._network_l2_info_provider.\
            get_network_l2_info(context.session, os_network_id)
        os_network_type = os_network_l2_info.get('network_type')
        os_segmentation_id = os_network_l2_info.get('segmentation_id')
        os_physical_network = os_network_l2_info.get('physical_network')
        os_tenant_id = (network.get('tenant_id') or
                        subnet.get('tenant_id') or
                        context.get('tenant_id'))
        os_user_id = context.user_id

        attributes = {
            'Subnet ID': os_subnet_id,
            'Subnet Name': os_subnet_name,
            'Network ID': os_network_id,
            'Network Name': os_network_name,
            InfobloxEaManager.INFOBLOX_IS_EXTERNAL: os_network_is_external,
            InfobloxEaManager.INFOBLOX_IS_SHARED: os_network_is_shared,
            'Network Encap': os_network_type,
            'Segmentation ID': os_segmentation_id,
            'Physical Network Name': os_physical_network,
            'Tenant ID': os_tenant_id,
            'Account': os_user_id,
        }

        return self._build_extattrs(attributes)

    def get_extattrs_for_ip(self, context, port):
        os_tenant_id = port.get('tenant_id')
        os_user_id = context.user_id

        neutron_internal_services_dev_owners = \
            ib_constants.NEUTRON_DEVICE_OWNER_TO_PATTERN_MAP.keys()

        set_os_instance_id = (port['device_owner'] not in
                              neutron_internal_services_dev_owners)

        if set_os_instance_id:
            os_instance_id = self._get_instance_id(context, port)
        else:
            os_instance_id = None

        attributes = {
            'Tenant ID': os_tenant_id,
            'Account': os_user_id,
            'Port ID': port['id']
        }
        if os_instance_id:
            attributes['VM ID'] = os_instance_id

        return self._build_extattrs(attributes)

    def _get_instance_id(self, context, port):
        network_is_external = self.db.is_network_external(
            context, port['network_id'])
        if network_is_external:
            os_instance_id = self.db.get_instance_id_by_floating_ip(
                context, floating_ip_id=port['device_id'])
        else:
            os_instance_id = port['device_id']

        return os_instance_id

    def _to_str_or_none(self, value):
        retval = None
        if not isinstance(value, basestring):
            if value is not None:
                retval = str(value)
        else:
            retval = value
        return retval

    def _build_extattrs(self, attributes):
        extattrs = {}
        for name, value in attributes.iteritems():
            str_val = self._to_str_or_none(value)
            if str_val:
                extattrs[name] = {'value': str_val}

        self.add_openstack_extattrs_marker(extattrs)
        return extattrs

    @classmethod
    def add_openstack_extattrs_marker(cls, extattrs):
        extattrs[cls.OPENSTACK_OBJECT_FLAG] = {'value': 'openstack'}


def _construct_extattrs(filters):
    extattrs = {}
    for name, filter_value_list in filters.items():
        # Filters in Neutron look like a dict
        # {
        #   'filter1_name': ['filter1_value'],
        #   'filter2_name': ['filter2_value']
        # }
        # So we take only the first item from user's input which is
        # filter_value_list here.
        # Also not Infoblox filters must be removed from filters.
        # Infoblox filters must be as following:
        # neutron <command> --infoblox_ea:<EA_name> <EA_value>
        infoblox_prefix = 'infoblox_ea:'
        if name.startswith(infoblox_prefix) and filter_value_list:
            # "infoblox-ea:" removed from filter name
            prefix_len = len(infoblox_prefix)
            attr_name = name[prefix_len:]
            extattrs[attr_name] = {'value': filter_value_list[0]}
    return extattrs


def _extattrs_result_filter_hook(query, filters, db_model,
                                 os_object, ib_objtype, mapping_id):
    """Result filter hook which filters Infoblox objects by
     Extensible Attributes (EAs) and returns Query object containing
     OpenStack objects which are equal to Infoblox ones.
    """
    infoblox = connector.Infoblox()
    infoblox_objects_ids = []
    extattrs = _construct_extattrs(filters)

    if extattrs:
        InfobloxEaManager.add_openstack_extattrs_marker(extattrs)
        infoblox_objects = infoblox.get_object(
            ib_objtype, return_fields=['extattrs'],
            extattrs=extattrs)
        if infoblox_objects:
            for infoblox_object in infoblox_objects:
                try:
                    obj_id = infoblox_object['extattrs'][mapping_id]['value']
                except KeyError:
                    raise exceptions.NoAttributeInInfobloxObject(
                        os_object=os_object, ib_object=ib_objtype,
                        attribute=mapping_id)
                infoblox_objects_ids.append(obj_id)
        query = query.filter(db_model.id.in_(infoblox_objects_ids))
    return query


def subnet_extattrs_result_filter_hook(query, filters):
    return _extattrs_result_filter_hook(
        query, filters, models_v2.Subnet, 'subnet', 'network', 'Subnet ID')


def network_extattrs_result_filter_hook(query, filters):
    return _extattrs_result_filter_hook(
        query, filters, models_v2.Network, 'subnet', 'network',
        'Network ID')


def port_extattrs_result_filter_hook(query, filters):
    if cfg.CONF.use_host_records_for_ip_allocation:
        ib_objtype = 'record:host'
    else:
        ib_objtype = 'record:a'
    return _extattrs_result_filter_hook(
        query, filters, models_v2.Port, 'port', ib_objtype, 'Port ID')


if (cfg.CONF.ipam_driver ==
        'neutron.ipam.drivers.infoblox.infoblox_ipam.InfobloxIPAM'):

    db_base_plugin_v2.NeutronDbPluginV2.register_model_query_hook(
        models_v2.Port, 'port_extattrs', None, None,
        port_extattrs_result_filter_hook)

    db_base_plugin_v2.NeutronDbPluginV2.register_model_query_hook(
        models_v2.Network, 'network_extattrs', None, None,
        network_extattrs_result_filter_hook)

    db_base_plugin_v2.NeutronDbPluginV2.register_model_query_hook(
        models_v2.Subnet, 'subnet_extattrs', None, None,
        subnet_extattrs_result_filter_hook)
