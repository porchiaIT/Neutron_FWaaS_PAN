# Copyright 2014 OpenStack Foundation
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

import copy
import mock

from neutron.services.l3_router.drivers.pan.connector import pan_connector
from neutron.tests import base


class FakeXapi(object):

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def __eq__(self, other):
        return (self.args == other.args and self.kwargs == other.kwargs)

    def xml_python(self, result=False):
        pass

    def keygen(self):
        pass

    def show(self, xpath=None):
        pass

    def delete(self, xpath=None):
        pass

    def set(self, xpath=None, element=None):
        pass

    def commit(self, cmd=None, action=None, sync=False,
               interval=None, timeout=None):
        pass

fake_devices = [{'name': 'device #1'}, {'name': 'device #2'}]
fake_interfaces = [{'name': 'ethernet1/2.1', 'comment': ''},
                   {'name': 'ethernet1/2.2', 'comment': ''}]


@mock.patch.object(pan_connector.xapi, "PanXapi", FakeXapi)
class TestPANConnector(base.BaseTestCase):

    def setUp(self):
        super(TestPANConnector, self).setUp()
        pan_connector.cfg.CONF.pan_host = '10.10.10.10'
        pan_connector.cfg.CONF.pan_username = 'fake user'
        pan_connector.cfg.CONF.pan_password = 'fake password'
        self.connector = pan_connector.PANConnector()

    @mock.patch.object(FakeXapi, "show", mock.Mock())
    @mock.patch.object(FakeXapi, "xml_python",
                       mock.Mock(return_value={'response':
                                               {'result':
                                                {'devices':
                                                 {'entry': fake_devices}}}}))
    def test_list_devices(self):
        xpath = ("/config/devices/entry[@name='localhost.localdomain']"
                 "/device-group/entry[@name='default']/devices")
        result = self.connector.list_devices()

        FakeXapi.show.assert_called_once_with(xpath)
        FakeXapi.xml_python.assert_any_call()
        self.assertEqual(['device #1', 'device #2'], result)

    @mock.patch.object(FakeXapi, "set", mock.Mock())
    def test_add_tags(self):
        device = 'fake device'
        tag = 'fake tag'
        xpath = "/config/mgt-config/devices"
        element = (
            "<entry name='fake device'><vsys><entry name='vsys1'>"
            "<tags><member>fake tag</member></tags></entry></vsys></entry>"
        )
        self.connector.add_device_tags(device, [tag])

        FakeXapi.set.assert_called_once_with(xpath, element)

    @mock.patch.object(FakeXapi, "delete", mock.Mock())
    def test_remove_tags(self):
        device = 'fake device'
        tag = 'fake tag'
        xpath = ("/config/mgt-config/devices/entry[@name='fake device']"
                 "/vsys/entry[@name='vsys1']/tags/member[text()='fake tag']")

        self.connector.remove_device_tags(device, [tag])

        FakeXapi.delete.assert_called_once_with(xpath)

    @mock.patch.object(FakeXapi, "commit", mock.Mock())
    def test_commit(self):

        self.connector.commit_configuration()

        FakeXapi.commit.assert_called_once_with(cmd='<commit></commit>',
                                                sync=True)

    @mock.patch.object(FakeXapi, "show", mock.Mock())
    @mock.patch.object(FakeXapi, "xml_python",
                       mock.Mock(return_value={'response':
                                               {'result':
                                                {'units':
                                                 {'entry': fake_interfaces}}}})
                       )
    def test_list_vlan_interfaces(self):
        api = FakeXapi()

        xpath = ("/config/devices/entry[@name='localhost.localdomain']"
                 "/network/interface/ethernet/entry[@name='ethernet1/2']"
                 "/layer3/units")

        result = self.connector._list_vlan_interfaces(api)

        self.assertEqual(fake_interfaces, result)
        FakeXapi.show.assert_called_once_with(xpath)
        FakeXapi.xml_python.assert_any_call()

    @mock.patch.object(FakeXapi, "set", mock.Mock())
    def test_add_router_iface(self):
        api = FakeXapi()
        iface_name = 'ethernet1/2.3'
        xpath = ("/config/devices/entry[@name='localhost.localdomain']"
                 "/network/virtual-router/entry[@name='default']/"
                 "interface")
        element = "<member>%s</member>" % iface_name
        self.connector._set_router_iface(api, iface_name)

        FakeXapi.set.assert_called_once_with(xpath, element)

    @mock.patch.object(FakeXapi, "set", mock.Mock())
    def test_add_security_zone_iface(self):
        api = FakeXapi()
        iface_name = 'ethernet1/2.3'
        xpath = ("/config/devices/entry[@name='localhost.localdomain']"
                 "/vsys/entry[@name='vsys1']/zone/entry[@name='internal']"
                 "/network/layer3")
        element = "<member>%s</member>" % iface_name
        self.connector._set_security_zone_iface(
            api,
            iface_name,
            pan_connector.cfg.CONF.pan_dev_internal_security_zone)

        FakeXapi.set.assert_called_once_with(xpath, element)

    @mock.patch.object(FakeXapi, "set", mock.Mock())
    @mock.patch.object(pan_connector.PANConnector, "_list_vlan_interfaces",
                       mock.Mock(return_value=fake_interfaces))
    @mock.patch.object(pan_connector.PANConnector, "_set_router_iface",
                       mock.Mock())
    @mock.patch.object(pan_connector.PANConnector, "_set_security_zone_iface",
                       mock.Mock())
    def test_add_vlan_iface(self):
        iface_dict = {'port_id': 'fake port id',
                      'ip_address': '10.0.0.1',
                      'cidr': '10.0.0.0/24',
                      'segmentation_id': '1111'}
        device = 'fake device'
        params = copy.deepcopy(self.connector._params)
        params['serial'] = device
        api = FakeXapi(**params)
        iface_name = 'ethernet1/2.3'
        xpath = ("/config/devices/entry[@name='localhost.localdomain']"
                 "/network/interface/ethernet/entry[@name='ethernet1/2']"
                 "/layer3/units/entry[@name='%s']" % iface_name)
        element = (
            "<ipv6><neighbor-discovery><router-advertisement>"
            " <enable>no</enable>"
            "</router-advertisement></neighbor-discovery></ipv6>"
            "<ip><entry name='10.0.0.1/24'/></ip>"
            "<tag>1111</tag>"
            "<comment>port_id=fake port id</comment>")

        self.connector.add_vlan_iface(device, iface_dict)

        FakeXapi.set.assert_called_once_with(xpath, element)
        self.connector._list_vlan_interfaces.assert_called_once_with(api)
        self.connector._set_router_iface.assert_called_once_with(api,
                                                                 iface_name)
        self.connector._set_security_zone_iface.assert_called_once_with(
            api,
            iface_name,
            pan_connector.cfg.CONF.pan_dev_internal_security_zone)

    @mock.patch.object(FakeXapi, "delete", mock.Mock())
    def test_remove_vlan_iface(self):
        iface_dict = {'port_id': 'fake port id'}
        ifaces = copy.deepcopy(fake_interfaces)
        ifaces[0]['comment'] = "port_id=%s" % iface_dict['port_id']
        iface_name = ifaces[0]['name']
        device = 'fake device serial'
        iface_xpath = ("/config/devices/entry[@name='localhost.localdomain']"
                       "/network/interface/ethernet/entry[@name='ethernet1/2']"
                       "/layer3/units/entry[@name='%s']" % iface_name)
        router_xpath = ("/config/devices/entry[@name='localhost.localdomain']"
                        "/network/virtual-router/entry[@name='default']/"
                        "interface/member[text()='%s']" % iface_name)
        zone_xpath = ("/config/devices/entry[@name='localhost.localdomain']"
                      "/vsys/entry[@name='vsys1']/zone/entry[@name='internal']"
                      "/network/layer3/member[text()='%s']" % iface_name)

        delete_calls = [mock.call(router_xpath),
                        mock.call(zone_xpath),
                        mock.call(iface_xpath)]

        with mock.patch.object(self.connector, '_list_vlan_interfaces',
                               mock.Mock(return_value=ifaces)):
            self.connector.remove_vlan_iface(device, iface_dict)

            FakeXapi.delete.assert_has_calls(delete_calls)

    @mock.patch.object(FakeXapi, "set", mock.Mock())
    def test_add_external_ip_private(self):
        device = 'fake device serial'
        params = copy.deepcopy(self.connector._params)
        params['serial'] = device
        api = FakeXapi(**params)
        ip_dict = {'ip_address': '10.0.0.1',
                   'cidr': '10.0.0.0/24'}
        xpath = ("/config/devices/entry[@name='localhost.localdomain']/"
                 "network/interface/ethernet/entry[@name='ethernet1/1']/"
                 "layer3/ip")
        element = "<entry name='10.0.0.1/24'/>"

        self.connector._add_external_ip(api, ip_dict)
        FakeXapi.set.assert_called_once_with(xpath, element)

    @mock.patch.object(pan_connector.PANConnector, "_add_external_ip",
                       mock.Mock())
    @mock.patch.object(pan_connector.PANConnector, "_set_router_iface",
                       mock.Mock())
    @mock.patch.object(pan_connector.PANConnector, "_set_security_zone_iface",
                       mock.Mock())
    @mock.patch.object(pan_connector.PANConnector, "_set_management_profile",
                       mock.Mock())
    def test_add_external_ip_public(self):
        device = 'fake device serial'
        params = copy.deepcopy(self.connector._params)
        params['serial'] = device
        api = FakeXapi(**params)
        ip_dict = {'ip_address': '10.0.0.1',
                   'cidr': '10.0.0.0/24'}
        iface_name = 'ethernet1/1'

        self.connector.add_external_ip(device, ip_dict)

        self.connector._add_external_ip.assert_called_once_with(api, ip_dict)
        self.connector._set_router_iface.assert_called_once_with(
            api, iface_name)
        self.connector._set_security_zone_iface.assert_called_once_with(
            api,
            iface_name,
            pan_connector.cfg.CONF.pan_dev_external_security_zone)
        self.connector._set_management_profile.assert_called_once_with(
            api, iface_name)

    @mock.patch.object(FakeXapi, "delete", mock.Mock())
    def test_remove_external_ip_private(self):
        device = 'fake device serial'
        params = copy.deepcopy(self.connector._params)
        params['serial'] = device
        api = FakeXapi(**params)
        xpath = ("/config/devices/entry[@name='localhost.localdomain']/"
                 "network/interface/ethernet/entry[@name='ethernet1/1']/"
                 "layer3/ip/entry")

        self.connector._remove_external_ip(api)
        FakeXapi.delete.assert_called_once_with(xpath)

    @mock.patch.object(pan_connector.PANConnector, "_remove_external_ip",
                       mock.Mock())
    @mock.patch.object(pan_connector.PANConnector, "_clear_router_iface",
                       mock.Mock())
    @mock.patch.object(pan_connector.PANConnector,
                       "_clear_security_zone_iface",
                       mock.Mock())
    @mock.patch.object(pan_connector.PANConnector, "_clear_management_profile",
                       mock.Mock())
    def test_remove_external_ip_public(self):
        device = 'fake device serial'
        params = copy.deepcopy(self.connector._params)
        params['serial'] = device
        api = FakeXapi(**params)
        iface_name = 'ethernet1/1'

        self.connector.remove_external_ip(device)

        self.connector._clear_router_iface.assert_called_once_with(
            api, iface_name)
        self.connector._clear_security_zone_iface.assert_called_once_with(
            api,
            iface_name,
            pan_connector.cfg.CONF.pan_dev_external_security_zone)
        self.connector._clear_management_profile.assert_called_once_with(
            api, iface_name)
        self.connector._remove_external_ip.assert_called_once_with(api)

    @mock.patch.object(FakeXapi, "set", mock.Mock())
    @mock.patch.object(FakeXapi, "__init__", mock.Mock(return_value=None))
    def test_add_external_nat(self):
        device = 'fake device serial'
        params = copy.deepcopy(self.connector._params)
        params['serial'] = device
        ip_dict = {'ip_address': '10.0.0.1',
                   'cidr': '10.0.0.0/24'}
        xpath = ("/config/devices/entry[@name='localhost.localdomain']/vsys"
                 "/entry[@name='vsys1']/rulebase/nat/rules")
        element = (
            "<entry name='OpenStack'>"
            "<source-translation>"
            "<dynamic-ip-and-port>"
            "<interface-address>"
            "<ip>10.0.0.1/24</ip>"
            "<interface>ethernet1/1</interface>"
            "</interface-address>"
            "</dynamic-ip-and-port>"
            "</source-translation>"
            "<to><member>%(destination_zone)s</member></to>"
            "<from><member>%(source_zone)s</member></from>"
            "<source><member>any</member></source>"
            "<destination><member>any</member></destination>"
            "<service>any</service>"
            "<nat-type>ipv4</nat-type>"
            "</entry>" %
            {'source_zone':
             pan_connector.cfg.CONF.pan_dev_internal_security_zone,
             'destination_zone':
             pan_connector.cfg.CONF.pan_dev_external_security_zone}
        )

        self.connector.add_external_nat(device, ip_dict)
        FakeXapi.__init__.assert_called_once_with(**params)
        FakeXapi.set.assert_called_once_with(xpath, element)

    @mock.patch.object(FakeXapi, "delete", mock.Mock())
    @mock.patch.object(FakeXapi, "__init__", mock.Mock(return_value=None))
    def test_remove_external_nat(self):
        device = 'fake device serial'
        params = copy.deepcopy(self.connector._params)
        params['serial'] = device
        xpath = ("/config/devices/entry[@name='localhost.localdomain']/vsys"
                 "/entry[@name='vsys1']/rulebase/nat/rules"
                 "/entry[@name='OpenStack']")

        self.connector.remove_external_nat(device)
        FakeXapi.__init__.assert_called_once_with(**params)
        FakeXapi.delete.assert_called_once_with(xpath)
