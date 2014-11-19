# vim: tabstop=4 shiftwidth=4 softtabstop=4
#
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

import mock
import requests
from requests import exceptions as req_exc

from neutron.ipam.drivers.infoblox import connector
from neutron.ipam.drivers.infoblox import exceptions
from neutron.tests import base


valid_config = mock.Mock()
valid_config.infoblox_wapi = 'http://localhost'
valid_config.infoblox_username = 'user'
valid_config.infoblox_password = 'pass'
valid_config.infoblox_sslverify = False
valid_config.infoblox_http_max_retries = 3


class UrlMatcher(object):
    def __init__(self, url, obj):
        self.url = url
        self.obj = obj

    def __eq__(self, actual_url):
        return self.url in actual_url and self.obj in actual_url


class TestInfobloxConnector(base.BaseTestCase):
    def setUp(self):
        super(TestInfobloxConnector, self).setUp()
        self.config(infoblox_wapi='https://infoblox.example.org/wapi/v1.1/')
        self.config(infoblox_username='admin')
        self.config(infoblox_password='password')
        self.connector = connector.Infoblox()

    def test_throws_error_on_username_not_set(self):
        fake_conf = mock.Mock()
        fake_conf.infoblox_wapi = 'http://localhost'
        fake_conf.infoblox_username = None
        fake_conf.infoblox_password = 'password'

        with mock.patch.object(connector.cfg, 'CONF', fake_conf):
            self.assertRaises(exceptions.InfobloxIsMisconfigured,
                              connector.Infoblox)

    def test_throws_error_on_password_not_set(self):
        fake_conf = mock.Mock()
        fake_conf.infoblox_wapi = 'http://localhost'
        fake_conf.infoblox_username = 'user'
        fake_conf.infoblox_password = None

        with mock.patch.object(connector.cfg, 'CONF', fake_conf):
            self.assertRaises(exceptions.InfobloxIsMisconfigured,
                              connector.Infoblox)

    def test_throws_error_on_wapi_url_not_set(self):
        fake_conf = mock.Mock()
        fake_conf.infoblox_wapi = None
        fake_conf.infoblox_username = 'user'
        fake_conf.infoblox_password = 'pass'

        with mock.patch.object(connector.cfg, 'CONF', fake_conf):
            self.assertRaises(exceptions.InfobloxIsMisconfigured,
                              connector.Infoblox)

    @mock.patch.object(connector.cfg, 'CONF', valid_config)
    def test_create_object(self):
        objtype = 'network'
        payload = {'ip': '0.0.0.0'}

        with mock.patch.object(requests.Session, 'post',
                               return_value=mock.Mock()) as patched_create:
            patched_create.return_value.status_code = 201
            patched_create.return_value.content = '{}'
            self.connector.create_object(objtype, payload)
            patched_create.assert_called_once_with(
                'https://infoblox.example.org/wapi/v1.1/network',
                data='{"ip": "0.0.0.0"}',
                headers={'Content-type': 'application/json'},
                verify=False
            )

    def test_create_object_with_extattrs(self):
        objtype = 'network'
        payload = {'ip': '0.0.0.0',
                   'extattrs': {'Subnet ID': {'value': 'fake_subnet_id'}}}
        with mock.patch.object(requests.Session, 'post',
                               return_value=mock.Mock()) as patched_create:
            patched_create.return_value.status_code = 201
            patched_create.return_value.content = '{}'
            self.connector.create_object(objtype, payload)
            patched_create.assert_called_once_with(
                'https://infoblox.example.org/wapi/v1.1/network',
                data='{"ip": "0.0.0.0", "extattrs": {"Subnet ID":'
                     ' {"value": "fake_subnet_id"}}}',
                headers={'Content-type': 'application/json'},
                verify=False
            )

    @mock.patch.object(connector.cfg, 'CONF', valid_config)
    def test_get_object(self):
        objtype = 'network'
        payload = {'ip': '0.0.0.0'}

        with mock.patch.object(requests.Session, 'get',
                               return_value=mock.Mock()) as patched_get:
            patched_get.return_value.status_code = 200
            patched_get.return_value.content = '{}'
            self.connector.get_object(objtype, payload)
            patched_get.assert_called_once_with(
                'https://infoblox.example.org/wapi/v1.1/network',
                data='{"ip": "0.0.0.0"}',
                headers={'Content-type': 'application/json'},
                verify=False
            )

    def test_get_objects_with_extattrs(self):
        objtype = 'network'
        payload = {'ip': '0.0.0.0'}
        extattrs = {
            'Subnet ID': {'value': 'fake_subnet_id'}
        }
        with mock.patch.object(requests.Session, 'get',
                               return_value=mock.Mock()) as patched_get:
            patched_get.return_value.status_code = 200
            patched_get.return_value.content = '{}'
            self.connector.get_object(objtype, payload, extattrs=extattrs)
            patched_get.assert_called_once_with(
                'https://infoblox.example.org/wapi/'
                'v1.1/network?*Subnet ID=fake_subnet_id',
                data='{"ip": "0.0.0.0"}',
                headers={'Content-type': 'application/json'},
                verify=False
            )

    @mock.patch.object(connector.cfg, 'CONF', valid_config)
    def test_update_object(self):
        ref = 'network'
        payload = {'ip': '0.0.0.0'}

        with mock.patch.object(requests.Session, 'put',
                               return_value=mock.Mock()) as patched_update:
            patched_update.return_value.status_code = 200
            patched_update.return_value.content = '{}'
            self.connector.update_object(ref, payload)
            patched_update.assert_called_once_with(
                'https://infoblox.example.org/wapi/v1.1/network',
                data='{"ip": "0.0.0.0"}',
                headers={'Content-type': 'application/json'},
                verify=False
            )

    @mock.patch.object(connector.cfg, 'CONF', valid_config)
    def test_delete_object(self):
        ref = 'network'
        with mock.patch.object(requests.Session, 'delete',
                               return_value=mock.Mock()) as patched_delete:
            patched_delete.return_value.status_code = 200
            patched_delete.return_value.content = '{}'
            self.connector.delete_object(ref)
            patched_delete.assert_called_once_with(
                'https://infoblox.example.org/wapi/v1.1/network',
                verify=False
            )

    def test_neutron_exception_is_raised_on_any_request_connection_error(self):
        supported_exceptions = [req_exc.Timeout,
                                req_exc.HTTPError,
                                req_exc.ConnectionError,
                                req_exc.ProxyError,
                                req_exc.SSLError,
                                req_exc.TooManyRedirects,
                                req_exc.InvalidURL]

        for exc in supported_exceptions:
            f = mock.Mock()
            f.__name__ = 'mock'  # functools.wraps need a name of a function
            f.side_effect = exc
            self.assertRaises(exceptions.InfobloxConnectionError,
                              connector.reraise_neutron_exception(f))
