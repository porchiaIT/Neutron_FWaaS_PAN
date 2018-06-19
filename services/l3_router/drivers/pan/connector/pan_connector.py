# Copyright (c) 2014 OpenStack Foundation.
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
#

import copy
from oslo.config import cfg

from neutron.common import exceptions as neutron_exc
from neutron.openstack.common import log as logging
from neutron.services.l3_router.drivers.pan.connector.xml_api import commit
from neutron.services.l3_router.drivers.pan.connector.xml_api import xapi

OPTS = [
    cfg.StrOpt(
        'pan_host',
        default=None,
        help=_("PAN-OS hostname or IP address. Used to construct request URI."
               " Required")),
    cfg.StrOpt(
        'pan_port',
        default=None,
        help=_("Port number used in the URL. This can be used to perform port"
               " forwarding.")),
    cfg.StrOpt(
        'pan_username',
        default=None,
        help=_("PAN-OS username.")),
    cfg.StrOpt(
        'pan_password',
        default=None,
        help=_("PAN-OS user password.")),
    cfg.StrOpt(
        'pan_api_key',
        default=None,
        help=_("PAN-OS API key.")),
    cfg.StrOpt(
        'pan_device_group',
        default='default',
        help=_("PAN-OS device group name.")),
    cfg.StrOpt(
        'pan_dev_router',
        default='default',
        help=_("PAN device router name.")),
    cfg.StrOpt(
        'pan_dev_internal_security_zone',
        default='internal',
        help=_("PAN device internal security zone name.")),
    cfg.StrOpt(
        'pan_dev_external_security_zone',
        default='external',
        help=_("PAN device external security zone name.")),
    cfg.StrOpt(
        'pan_dev_interface_management_profile',
        default=None,
        help=_("PAN device interface management profile.")),
    cfg.StrOpt(
        'pan_dev_default_route_next_hop',
        default=None,
        help=_("PAN device virtual router next hop ip address for default"
               " route.")),
]
cfg.CONF.register_opts(OPTS)
LOG = logging.getLogger(__name__)


class PANConnector(object):
    """Connector to the PAN XML API."""
    def __init__(self):
        opts = ['pan_host']
        if cfg.CONF.pan_api_key:
            opts.append('pan_api_key')
        else:
            opts += ['pan_username', 'pan_password']

        for opt_name in opts:
            opt_value = getattr(cfg.CONF, opt_name, None)
            if not opt_value:
                raise neutron_exc.InvalidConfigurationOption(
                    opt_name=opt_name, opt_value=opt_value)

        self._params = {'hostname': cfg.CONF.pan_host}

        if 'pan_api_key' in opts:
            self._params['api_key'] = cfg.CONF.pan_api_key
        else:
            self._params['api_username'] = cfg.CONF.pan_username
            self._params['api_password'] = cfg.CONF.pan_password

        if cfg.CONF.pan_port:
            self._params['port'] = cfg.CONF.pan_port

    def add_external_ip(self, device_sn, ip_dict):
        """Add ip address to the device external interface.

        @param device_sn: PAN device serial number
        @param ip_dict: dict with ip address info. Contains:
            - 'ip_address': ip address allocated for this interface
            - 'cidr': interface subnet in cidr notation

        @return: None
        """
        params = copy.deepcopy(self._params)
        params['serial'] = device_sn
        xml_api = xapi.PanXapi(**params)
        iface_name = 'ethernet1/1'
        self._add_external_ip(xml_api, ip_dict)
        self._set_router_iface(xml_api, iface_name)
        if cfg.CONF.pan_dev_default_route_next_hop:
            self._set_default_route(xml_api)
        self._set_security_zone_iface(xml_api,
                                      iface_name,
                                      cfg.CONF.pan_dev_external_security_zone)
        self._set_management_profile(xml_api, iface_name)

    def remove_external_ip(self, device_sn):
        """Remove ip address from the device external interface.

        @param device_sn: PAN device serial number

        @return: None
        """
        params = copy.deepcopy(self._params)
        params['serial'] = device_sn
        xml_api = xapi.PanXapi(**params)
        iface_name = 'ethernet1/1'
        self._clear_router_iface(xml_api, iface_name)
        if cfg.CONF.pan_dev_default_route_next_hop:
            self._clear_default_route(xml_api)
        self._clear_security_zone_iface(
            xml_api,
            iface_name,
            cfg.CONF.pan_dev_external_security_zone)
        self._clear_management_profile(xml_api, iface_name)
        self._remove_external_ip(xml_api)

    def add_external_nat(self, device_sn, ip_dict):
        """Add external NAT rule to allow internet access from Nova instances.

        @param device_sn: PAN device serial number
        @param ip_dict: dict with ip address info. Contains:
            - 'ip_address': ip address allocated for this interface
            - 'cidr': interface subnet in cidr notation

        @return: None
        """
        ip = ip_dict['ip_address'] + '/' + ip_dict['cidr'].split('/')[1]
        params = copy.deepcopy(self._params)
        params['serial'] = device_sn
        xml_api = xapi.PanXapi(**params)

        # If the source (internal) zone doesn't exist, create it
        sz_xpath = ("/config/devices/entry[@name='localhost.localdomain']"
                    "/vsys/entry[@name='vsys1']/zone/entry[@name='%s']"
                    % cfg.CONF.pan_dev_internal_security_zone)

        try:
            xml_api.show(sz_xpath)
        except xapi.PanXapiError as e:
            if e.msg.lower() == 'no such node':
                element = "<network><layer3/></network>"
                xml_api.set(sz_xpath, element)
            else:
                raise

        xpath = ("/config/devices/entry[@name='localhost.localdomain']/vsys"
                 "/entry[@name='vsys1']/rulebase/nat/rules")
        element = (
            "<entry name='OpenStack'>"
            "<source-translation>"
            "<dynamic-ip-and-port>"
            "<interface-address>"
            "<ip>%(ip)s</ip>"
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
            {'ip': ip,
             'source_zone': cfg.CONF.pan_dev_internal_security_zone,
             'destination_zone': cfg.CONF.pan_dev_external_security_zone}
        )
        xml_api.set(xpath, element)

    def remove_external_nat(self, device_sn):
        """Remove external NAT rule to deny internet access for Nova instances.

        @param device_sn: PAN device serial number

        @return: None
        """
        params = copy.deepcopy(self._params)
        params['serial'] = device_sn
        xml_api = xapi.PanXapi(**params)
        xpath = ("/config/devices/entry[@name='localhost.localdomain']/vsys"
                 "/entry[@name='vsys1']/rulebase/nat/rules"
                 "/entry[@name='OpenStack']")
        xml_api.delete(xpath)

    def register_ip_address(self, device_sn, ip_address, tags):
        params = copy.deepcopy(self._params)
        params['serial'] = device_sn
        xml_api = xapi.PanXapi(**params)
        xml_tags = ""
        tags.sort()
        for tag in tags:
            xml_tag = "<member>%s</member>" % tag
            xml_tags += xml_tag
        cmd = ("<uid-message>"
               "<version>2.0</version>"
               "<type>update</type>"
               "<payload>"
               "<register>"
               "<entry ip=\"%s\">"
               "<tag>"
               "%s"
               "</tag>"
               "</entry>"
               "</register>"
               "</payload>"
               "</uid-message>" % (ip_address, xml_tags))

        try:
            xml_api.user_id(cmd)
        except xapi.PanXapiError as e:
            if 'already exists, ignore' in e.msg.lower():
                pass
            else:
                raise

    def unregister_ip_address(self, device_sn, ip_address):
        params = copy.deepcopy(self._params)
        params['serial'] = device_sn
        xml_api = xapi.PanXapi(**params)

        cmd = ("<uid-message>"
               "<version>2.0</version>"
               "<type>update</type>"
               "<payload>"
               "<unregister>"
               "<entry ip=\"%s\">"
               "</entry>"
               "</unregister>"
               "</payload>"
               "</uid-message>" % ip_address)

        xml_api.user_id(cmd)

    def list_devices(self):
        """Get list of PAN devices in specified (in the config file)
           device group.

        @return: list of devices serial numbers
        """
        xml_api = xapi.PanXapi(**self._params)
        return [item['name'] for item in self._list_group_devices(xml_api)]

    def add_vlan_iface(self, device_sn, iface_dict):
        """Add VLAN interface to specified device.

        @param device_sn: PAN device serial number
        @param iface_dict: dict with VLAN interface info. Contains:
            - 'port_id': Neutron port id
            - 'ip_address': ip address allocated for this interface
            - 'cidr': interface subnet in cidr notation
            - 'segmentation_id': vlan tag

        @return: None
        """
        params = copy.deepcopy(self._params)
        params['serial'] = device_sn
        xml_api = xapi.PanXapi(**params)
        vlan_ifaces = self._list_vlan_interfaces(xml_api)

        device_cnt = len(vlan_ifaces)
        vlan_iface_name = "ethernet1/2.%d" % (device_cnt + 1)

        self._add_vlan_iface(xml_api, vlan_iface_name, iface_dict)
        self._set_router_iface(xml_api, vlan_iface_name)
        self._set_security_zone_iface(xml_api,
                                      vlan_iface_name,
                                      cfg.CONF.pan_dev_internal_security_zone)

    def remove_vlan_iface(self, device_sn, iface_dict):
        """Remove VLAN interface from specified device.

        @param device_sn: PAN device serial number
        @param iface_dict: dict with VLAN interface info. Contains:
            - 'port_id': Neutron port id

        @return: None
        """
        params = copy.deepcopy(self._params)
        params['serial'] = device_sn
        xml_api = xapi.PanXapi(**params)
        vlan_ifaces = self._list_vlan_interfaces(xml_api)

        vlan_iface = next((item for item in vlan_ifaces
                           if iface_dict['port_id'] in item["comment"]), None)

        if vlan_iface:
            self._clear_router_iface(xml_api, vlan_iface['name'])
            self._clear_security_zone_iface(
                xml_api,
                vlan_iface['name'],
                cfg.CONF.pan_dev_internal_security_zone)
            self._remove_vlan_iface(xml_api, vlan_iface['name'])

    def add_device_tags(self, device_sn, tags):
        """Add tags to specified device.

        @param device_sn: PAN device serial number
        @param tags: list of tags

        @return: None
        """
        xml_api = xapi.PanXapi(**self._params)
        for tag in tags:
            self._add_device_tag(xml_api, device_sn, tag)

    def remove_device_tags(self, device_sn, tags):
        """Remove tags from device.

        @param device_sn: PAN device serial number
        @param tags: list of tags

        @return: None
        """
        xml_api = xapi.PanXapi(**self._params)
        for tag in tags:
            self._remove_device_tag(xml_api, device_sn, tag)

    def commit_configuration(self, device_sn=None):
        """Commit candidate configuration to Panorama or specified device.

        @param device_sn: PAN device serial number

        @return: None
        """
        c = commit.PanCommit()
        params = copy.deepcopy(self._params)
        params['use_get'] = True
        if device_sn:
            params['serial'] = device_sn
        xml_api = xapi.PanXapi(**params)
        xml_api.commit(cmd=c.cmd(), sync=True)

    def _add_device_tag(self, api, device_sn, tag):
        xpath = "/config/mgt-config/devices"
        element = (
            "<entry name='%(device_sn)s'><vsys><entry name='vsys1'>"
            "<tags><member>%(tag)s</member></tags></entry></vsys></entry>" %
            {'device_sn': device_sn,
             'tag': tag}
        )
        api.set(xpath, element)

    def _remove_device_tag(self, api, device_sn, tag):
        xpath = ("/config/mgt-config/devices/entry[@name='%(device_sn)s']"
                 "/vsys/entry[@name='vsys1']/tags/member[text()='%(tag)s']" %
                 {'device_sn': device_sn,
                  'tag': tag})
        api.delete(xpath)

    def _list_group_devices(self, api):
        xpath = ("/config/devices/entry[@name='localhost.localdomain']"
                 "/device-group/entry[@name='%s']/devices"
                 % cfg.CONF.pan_device_group)
        api.show(xpath)
        result = api.xml_python()

        return result['response']['result']['devices']['entry']

    def _get_device(self, api, device_sn):
        xpath = ("/config/mgt-config/devices/entry[@name='%s']" % device_sn)
        api.show(xpath)
        result = api.xml_python()
        return result['response']['result']['entry']

    def _list_vlan_interfaces(self, api):
        xpath = ("/config/devices/entry[@name='localhost.localdomain']"
                 "/network/interface/ethernet/entry[@name='ethernet1/2']"
                 "/layer3/units")
        try:
            api.show(xpath)
        except xapi.PanXapiError:
            LOG.warning(_("Node %s doesn't exist"), xpath)
            return []

        result = api.xml_python()
        if result['response']['result']['units']:
            return result['response']['result']['units']['entry']
        else:
            return []

    def _add_vlan_iface(self, api, iface_name, iface_dict):
        if cfg.CONF.pan_dev_interface_management_profile is None:
            mgmt_profile = ''
        else:
            mgmt_profile = ("<interface-management-profile>%s"
                            "</interface-management-profile>" %
                            cfg.CONF.pan_dev_interface_management_profile)
        ip = iface_dict['ip_address'] + '/' + iface_dict['cidr'].split('/')[1]
        xpath = ("/config/devices/entry[@name='localhost.localdomain']"
                 "/network/interface/ethernet/entry[@name='ethernet1/2']"
                 "/layer3/units/entry[@name='%s']" % iface_name)
        element = (
            "<ipv6><neighbor-discovery><router-advertisement>"
            " <enable>no</enable>"
            "</router-advertisement></neighbor-discovery></ipv6>"
            "<ip><entry name='%(ip)s'/></ip>"
            "%(mgmt_profile)s"
            "<tag>%(tag)s</tag>"
            "<comment>port_id=%(port_id)s</comment>" %
            {'ip': ip,
             'tag': iface_dict['segmentation_id'],
             'port_id': iface_dict['port_id'],
             'mgmt_profile': mgmt_profile}
        )
        api.set(xpath, element)

    def _remove_vlan_iface(self, api, iface_name):
        xpath = ("/config/devices/entry[@name='localhost.localdomain']"
                 "/network/interface/ethernet/entry[@name='ethernet1/2']"
                 "/layer3/units/entry[@name='%s']" % iface_name)
        api.delete(xpath)

    def _set_router_iface(self, api, iface_name):
        xpath = ("/config/devices/entry[@name='localhost.localdomain']"
                 "/network/virtual-router/entry[@name='%s']/"
                 "interface" % cfg.CONF.pan_dev_router)
        element = "<member>%s</member>" % iface_name
        api.set(xpath, element)

    def _clear_router_iface(self, api, iface_name):
        xpath = ("/config/devices/entry[@name='localhost.localdomain']"
                 "/network/virtual-router/entry[@name='%(router)s']/"
                 "interface/member[text()='%(iface)s']"
                 % {'router': cfg.CONF.pan_dev_router,
                    'iface': iface_name})
        api.delete(xpath)

    def _set_security_zone_iface(self, api, iface_name, zone_name):
        sz_xpath = ("/config/devices/entry[@name='localhost.localdomain']"
                    "/vsys/entry[@name='vsys1']/zone/entry[@name='%s']"
                    % zone_name)

        try:
            api.show(sz_xpath)
        except xapi.PanXapiError as e:
            if e.msg.lower() == 'no such node':
                element = "<network><layer3/></network>"
                api.set(sz_xpath, element)
            else:
                raise

        xpath = ("/config/devices/entry[@name='localhost.localdomain']"
                 "/vsys/entry[@name='vsys1']/zone/entry[@name='%s']"
                 "/network/layer3" % zone_name)
        element = "<member>%s</member>" % iface_name
        api.set(xpath, element)

    def _clear_security_zone_iface(self, api, iface_name, zone_name):
        xpath = ("/config/devices/entry[@name='localhost.localdomain']"
                 "/vsys/entry[@name='vsys1']/zone/entry[@name='%(zone)s']"
                 "/network/layer3/member[text()='%(iface)s']"
                 % {'zone': zone_name,
                    'iface': iface_name})
        api.delete(xpath)

    def _add_external_ip(self, api, ip_dict):
        ip = ip_dict['ip_address'] + '/' + ip_dict['cidr'].split('/')[1]
        xpath = ("/config/devices/entry[@name='localhost.localdomain']/"
                 "network/interface/ethernet/entry[@name='ethernet1/1']/"
                 "layer3/ip")
        element = "<entry name='%s'/>" % ip
        api.set(xpath, element)

    def _remove_external_ip(self, api):
        xpath = ("/config/devices/entry[@name='localhost.localdomain']/"
                 "network/interface/ethernet/entry[@name='ethernet1/1']/"
                 "layer3/ip/entry")
        api.delete(xpath)

    def _set_management_profile(self, api, iface_name):
        if cfg.CONF.pan_dev_interface_management_profile is None:
            return
        xpath = ("/config/devices/entry[@name='localhost.localdomain']/"
                 "network/interface/ethernet/entry[@name='%s']/layer3"
                 % iface_name)
        element = ("<interface-management-profile>"
                   "%s"
                   "</interface-management-profile>"
                   % cfg.CONF.pan_dev_interface_management_profile)
        api.set(xpath, element)

    def _clear_management_profile(self, api, iface_name):
        if cfg.CONF.pan_dev_interface_management_profile is None:
            return
        xpath = ("/config/devices/entry[@name='localhost.localdomain']/"
                 "network/interface/ethernet/entry[@name='%s']/layer3/"
                 "interface-management-profile" % iface_name)
        api.delete(xpath)

    def _set_default_route(self, api):
        xpath = ("/config/devices/entry[@name='localhost.localdomain']"
                 "/network/virtual-router/entry[@name='%s']"
                 "/routing-table/ip/static-route" % cfg.CONF.pan_dev_router)
        element = ("<entry name='default'>"
                   "<nexthop>"
                   "<ip-address>%s</ip-address>"
                   "</nexthop>"
                   "<metric>10</metric>"
                   "<destination>0.0.0.0/0</destination>"
                   "</entry>" % cfg.CONF.pan_dev_default_route_next_hop)
        api.set(xpath, element)

    def _clear_default_route(self, api):
        xpath = ("/config/devices/entry[@name='localhost.localdomain']"
                 "/network/virtual-router/entry[@name='%s']"
                 "/routing-table/ip/static-route/entry[@name='default']"
                 % cfg.CONF.pan_dev_router)
        api.delete(xpath)
