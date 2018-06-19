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

from neutron.extensions import l3
from neutron.plugins.ml2 import db as ml2_db
from neutron.services.l3_router.drivers import base as l3_base_driver
from neutron.services.l3_router.drivers.pan.connector import pan_connector
from neutron.services.l3_router.drivers.pan import db as pan_db

NETWORK_TYPE = 'vlan'


class L3RouterPANDriver(l3_base_driver.L3RouterBaseDriver):

    def __init__(self):
        self._connector = pan_connector.PANConnector()
        self._db = pan_db.PanDbApi()

    def create_router_precommit(self, context, r_ctx):
        devices = self._connector.list_devices()
        reserved_devices = [item['device_sn'] for item
                            in self._db.get_device_reservations(context)]
        free_devices = list(set(devices) - set(reserved_devices))
        if not free_devices:
            raise Exception("No more free PAN devices")
        device_sn = free_devices[0]

        self._db.reserve_pan_device(context, device_sn, r_ctx.current['id'])
        tags = self._generate_device_tags(r_ctx.current)
        self._connector.add_device_tags(device_sn, tags)

    def create_router_postcommit(self, context, r_ctx):
        self._connector.commit_configuration()

    def update_router_precommit(self, context, r_ctx):
        if l3.EXTERNAL_GW_INFO in r_ctx.update:
            info = r_ctx.update[l3.EXTERNAL_GW_INFO]
            network_id = info['network_id'] if info else None
            dev_res = self._db.get_device_reservation(context,
                                                      r_ctx.current['id'])

            if network_id:
                gw_port = self._db.get_port(context,
                                            r_ctx.current['gw_port_id'])
                ip = gw_port['fixed_ips'][0]
                subnet = self._db.get_subnet(context, ip['subnet_id'])
                ip_dict = {'ip_address': ip['ip_address'],
                           'cidr': subnet['cidr']}
                self._connector.add_external_ip(dev_res['device_sn'], ip_dict)
                self._connector.add_external_nat(dev_res['device_sn'], ip_dict)
            else:
                self._connector.remove_external_nat(dev_res['device_sn'])
                self._connector.remove_external_ip(dev_res['device_sn'])

            r_ctx.params = {'device_sn': dev_res['device_sn']}

    def update_router_postcommit(self, context, r_ctx):
        if r_ctx.params.get('device_sn'):
            self._connector.commit_configuration(r_ctx.params['device_sn'])

    def delete_router_precommit(self, context, r_ctx):
        dev_res = self._db.get_device_reservation(context,
                                                  r_ctx.original['id'])
        self._db.release_pan_device(context, r_ctx.original['id'])

        tags = self._generate_device_tags(r_ctx.original)
        self._connector.remove_device_tags(dev_res['device_sn'], tags)

    def delete_router_postcommit(self, context, r_ctx):
        self._connector.commit_configuration()

    def add_router_interface_precommit(self, context, rp_ctx):
        dev_res = self._db.get_device_reservation(context,
                                                  rp_ctx.current_router_id)
        segmentation_id = self._get_network_segmentation_id(
            context, rp_ctx.current['network_id'])
        ip = rp_ctx.current['fixed_ips'][0]
        subnet = self._db.get_subnet(context, ip['subnet_id'])
        iface_dict = {'port_id': rp_ctx.current['id'],
                      'segmentation_id': segmentation_id,
                      'ip_address': ip['ip_address'],
                      'cidr': subnet['cidr']}
        self._connector.add_vlan_iface(dev_res['device_sn'], iface_dict)
        rp_ctx.params = {'device_sn': dev_res['device_sn']}

    def add_router_interface_postcommit(self, context, rp_ctx):
        self._connector.commit_configuration(rp_ctx.params['device_sn'])

    def remove_router_interface_precommit(self, context, rp_ctx):
        dev_res = self._db.get_device_reservation(context,
                                                  rp_ctx.original_router_id)
        iface_dict = {'port_id': rp_ctx.original['id']}
        self._connector.remove_vlan_iface(dev_res['device_sn'], iface_dict)
        rp_ctx.params = {'device_sn': dev_res['device_sn']}

    def remove_router_interface_postcommit(self, context, rp_ctx):
        self._connector.commit_configuration(rp_ctx.params['device_sn'])

    def create_floatingip_precommit(self, context, fip_ctx):
        pass

    def create_floatingip_postcommit(self, context, fip_ctx):
        pass

    def update_floatingip_precommit(self, context, fip_ctx):
        pass

    def update_floatingip_postcommit(self, context, fip_ctx):
        pass

    def delete_floatingip_precommit(self, context, fip_ctx):
        pass

    def delete_floatingip_postcommit(self, context, fip_ctx):
        pass

    def disassociate_floatingip_precommit(self, context, fip_ctx):
        pass

    def disassociate_floatingip_postcommit(self, context, fip_ctx):
        pass

    def _get_network_segmentation_id(self, context, network_id,
                                     network_type=NETWORK_TYPE):
        nw_segments = ml2_db.get_network_segments(context.session, network_id)
        result = [item for item in nw_segments
                  if item['network_type'] == network_type]
        if not result:
            raise Exception(_("No %(network_type)s segment for network"
                              " %(network_id)s")
                            % {'network_id': network_id,
                               'network_type': network_type})

        return result[0]['segmentation_id']

    def _generate_device_tags(self, router):
        return ['tenant_' + (router['tenant_id'][:8]),
                'router_' + (router['name'])]
