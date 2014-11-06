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

from neutron.common import exceptions


class ConfigNotFound(exceptions.NeutronException):
    message = _("Configuration file for %(object)s not found.")


class InvalidPattern(exceptions.NeutronException):
    message = _("Invalid pattern syntax: %(msg)s")


class InfobloxException(exceptions.NeutronException):
    """Generic Infoblox Exception."""
    def __init__(self, response, **kwargs):
        self.response = response
        super(InfobloxException, self).__init__(**kwargs)


class InfobloxInvalidConditionalConfig(exceptions.NeutronException):
    message = _("Conditional config has invalid syntax: %(msg)s")


class InfobloxNoConfigFoundForSubnet(exceptions.NeutronException):
    message = _("No matching conditional configuration found for %(subnet)s")


class InfobloxIsMisconfigured(exceptions.NeutronException):
    message = _("Infoblox IPAM is misconfigured: infoblox_wapi, "
                "infoblox_username and infoblox_password must be defined.")


class InfobloxSearchError(InfobloxException):
    message = _("Cannot search '%(objtype)s' object(s): "
                "%(content)s [code %(code)s]")


class InfobloxCannotCreateObject(InfobloxException):
    message = _("Cannot create '%(objtype)s' object(s): "
                "%(content)s [code %(code)s]")


class InfobloxCannotDeleteObject(InfobloxException):
    message = _("Cannot delete object with ref %(ref)s: "
                "%(content)s [code %(code)s]")


class InfobloxCannotUpdateObject(InfobloxException):
    message = _("Cannot update object with ref %(ref)s: "
                "%(content)s [code %(code)s]")


class InfobloxFuncException(InfobloxException):
    message = _("Error occured during function's '%(func_name)s' call: "
                "ref %(ref)s: %(content)s [code %(code)s]")


class InfobloxCannotReserveIp(exceptions.NeutronException):
    message = _("Cannot reserve %(ip)s IP address in the %(net_view)s ")


class InfobloxReservationNotFound(exceptions.NeutronException):
    message = _("IP reservation object not found "
                "for %(reservation)s")


class InfobloxTooManyObjectsFound(exceptions.NeutronException):
    message = _("Too many objects found for %(request)s")


class InfobloxHostRecordIpAddrNotCreated(exceptions.NeutronException):
    message = _("Infoblox host record ipv4addr has not been created for "
                "IP %(ip)s, mac %(mac)s")


class InfobloxHostRecordIpv4AddrNotCreated(exceptions.NeutronException):
    """DEPRECATED. Use InfobloxHostRecordIpAddrNotCreated instead"""
    message = _("Infoblox host record ipv4addr has not been created for "
                "netview %(netview)s, cidr %(cidr)s, mac %(mac)s")


class NoInfobloxMemberAvailable(exceptions.ResourceExhausted):
    message = _("No Infoblox Member is available.")


class NoInfobloxMembersAssignedToTenant(exceptions.NeutronException):
    message = _("Tenant %(tenant)s has no Infoblox members assigned.")


class MoreThanOneInfobloxMemberAssignedToTenant(exceptions.NeutronException):
    message = _("Tenant %(tenant)s has more than one members assigned: "
                "%(members)s.")


class NoInfobloxMembersAssignedToNetwork(exceptions.NeutronException):
    message = _("Network %(network)s has no Infoblox members assigned.")


class MoreThanOneInfobloxMemberAssignedToNetwork(exceptions.NeutronException):
    message = _("Network %(network)s has more than one members assigned: "
                "%(members)s.")


class NoInfobloxMembersAssignedToNetview(exceptions.NeutronException):
    message = _("Network View %(netview)s has no Infoblox members assigned.")


class MoreThanOneInfobloxMemberAssignedToNetview(exceptions.NeutronException):
    message = _("Network View %(netview)s has more than one members assigned: "
                "%(members)s.")


class InfobloxCannotAllocateIpForSubnet(exceptions.NeutronException):
    message = _("Infoblox Network view %(netview)s, Network %(cidr)s does not "
                "have IPs available for allocation.")


class InfobloxCannotAllocateIp(exceptions.NeutronException):
    message = _("Cannot allocate IP %(ip_data)s")


class InfobloxDidNotReturnCreatedIPBack(exceptions.NeutronException):
    message = _("Infoblox did not return created IP back")


class InfobloxNetworkNotAvailable(exceptions.NeutronException):
    message = _("No network view %(net_view_name)s for %(cidr)s")


class InfobloxObjectParsingError(exceptions.NeutronException):
    message = _("Infoblox object cannot be parsed from dict: %(data)s")


class HostRecordNoIPv4Addrs(InfobloxObjectParsingError):
    message = _("Cannot parse Host Record object from dict because 'ipv4addrs'"
                "are absent.")


class HostRecordNoIPv6Addrs(InfobloxObjectParsingError):
    message = _("Cannot parse Host Record object from dict because 'ipv6addrs'"
                "are absent.")


class InfobloxInvalidIp(InfobloxObjectParsingError):
    message = _("Bad IP address: %(ip)s")


class HostRecordNotFound(exceptions.NeutronException):
    message = _("Infoblox record:host object with %(ip_address)s is not found")


class NoAttributeInInfobloxObject(exceptions.NeutronException):
    message = _("To find OpenStack %(os_object)s for Infoblox %(ib_object)s, "
                "%(attribute)s must be in extensible attributes.")


class ReservedMemberNotAvailableInConfig(exceptions.NeutronException):
    message = _('Reserved member %(member_name)s not available in members '
                'config %(config)s.')


class InvalidMemberConfig(exceptions.NeutronException):
    message = _("Infoblox member configuration has invalid syntax: "
                "expected %(key)s argument not found")


class OperationNotAllowed(exceptions.NeutronException):
    message = _("Requested operation is not allowed: %(reason)s")


class InfobloxConnectionError(exceptions.NeutronException):
    message = _("Infoblox HTTP request failed with: %(reason)s")
