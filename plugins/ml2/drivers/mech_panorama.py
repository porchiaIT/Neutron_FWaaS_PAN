# Copyright (c) 2014 OpenStack Foundation
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

from netaddr import IPNetwork
import sqlalchemy as sa

from neutron.common import constants
from neutron.db.l3_db import Router
from neutron.db import model_base
from neutron.db.models_v2 import HasId, Network, Port
from neutron.openstack.common import log
from neutron.plugins.ml2 import driver_api
from neutron.services.l3_router.drivers.pan.connector import pan_connector
from neutron.services.l3_router.drivers.pan import db as pan_db

from novaclient.v1_1 import client as nova_client
from oslo.config import cfg

LOG = log.getLogger(__name__)

nova_opts = [
    cfg.StrOpt('nova_admin_username',
               default=None,
               help='Nova admin username'),
    cfg.StrOpt('nova_admin_password',
               default=None,
               help=''),
    cfg.StrOpt('nova_admin_tenant_name',
               default=None,
               help=''),
    cfg.StrOpt('nova_admin_auth_url',
               default=None,
               help='')
]


class PortMetadata(model_base.BASEV2, HasId):
    """Represents a metadata for port on a Neutron v2 network."""
    __tablename__ = 'port_metadata'
    port_id = sa.Column(sa.String(36), sa.ForeignKey('ports.id',
                                                     ondelete="CASCADE"),
                        nullable=False)
    data = sa.Column(sa.String(1024))


class PanoramaMechanismDriver(driver_api.MechanismDriver):
    def __init__(self):
        super(PanoramaMechanismDriver, self).__init__()
        for nova_opt in nova_opts:
            try:
                cfg.CONF.register_opt(nova_opt)
            except cfg.DuplicateOptError:
                pass
        self.connector = pan_connector.PANConnector()
        self.pan_db = pan_db.PanDbApi()
        self.nova_client = nova_client.Client(
            cfg.CONF.nova_admin_username,
            cfg.CONF.nova_admin_password,
            cfg.CONF.nova_admin_tenant_name,
            cfg.CONF.nova_admin_auth_url,
            no_cache=True)
        self.nova_client.authenticate()
        self._params = None

    @property
    def params(self):
        return self._params

    @params.setter
    def params(self, value):
        self._params = value

    def initialize(self):
        pass

    def create_port_postcommit(self, context):
        if 'compute' in context._port['device_owner']:
            ip = self._get_port_ip(context, context._port)
            tags = self._collect_instance_tags(context)
            routers = self._get_routers(context)
            self._save_tags_to_db(context, tags)
            self._add_address_for_dynamic_group(context, ip, tags, routers)
        elif (constants.DEVICE_OWNER_ROUTER_INTF
              == context._port['device_owner']):

            network_filter = {'network_id': [context._port['network_id']]}
            ports = context._plugin.get_ports(context._plugin_context,
                                              filters=network_filter)
            routers = self._get_routers(context)
            for port in ports:
                tags = self._get_tags_from_db(context, port['id'])
                if tags:
                    ip = self._get_port_ip(context, port)
                    self._add_address_for_dynamic_group(
                        context, ip, tags, routers)

    def delete_port_precommit(self, context):
        if 'compute' in context._port['device_owner']:
            ip = self._get_port_ip(context, context._port)
            routers = self._get_routers(context)
            devices = self._remove_address_from_dynamic_group(
                context, ip, routers)
            self._params = devices
        elif (constants.DEVICE_OWNER_ROUTER_INTF
              == context._port['device_owner']):

            network_filter = {'network_id': [context._port['network_id']]}
            ports = context._plugin.get_ports(context._plugin_context,
                                              filters=network_filter)
            routers = self._get_routers(context)
            for port in ports:
                tags = self._get_tags_from_db(context, port['id'])
                if tags:
                    ip = self._get_port_ip(context, port)
                    devices = self._remove_address_from_dynamic_group(
                        context, ip, routers)
                    self._params = devices

    def delete_port_postcommit(self, context):
        if self._params:
            for device in self._params:
                self.connector.commit_configuration(device)
        self._params = None

    def _add_address_for_dynamic_group(self, context, ip, tags, routers):
        for router in routers:
            dev_res = self.pan_db.get_device_reservation(
                context._plugin_context, router['id'])
            self.connector.register_ip_address(dev_res['device_sn'],
                                               ip,
                                               tags)
            self.connector.commit_configuration(dev_res['device_sn'])

    def _remove_address_from_dynamic_group(self, context, ip, routers):
        devices = []
        for router in routers:
            dev_res = self.pan_db.get_device_reservation(
                context._plugin_context, router['id'])
            self.connector.unregister_ip_address(dev_res['device_sn'],
                                                 ip)
            devices.append(dev_res['device_sn'])
        return devices

    def _collect_instance_tags(self, context):
        tags = []

        ip = context._port['fixed_ips'][0]
        host = self.nova_client.servers.get(context._port['device_id'])

        tags.append("openstack_tenant-%s" % context._port['tenant_id'])

        tags.append("openstack_network-%s" % context._port['network_id'])

        tags.append("openstack_subnet-%s" % ip['subnet_id'])

        tags.append("openstack_port-%s" % context._port['id'])

        tags.append("openstack_port_device_owner-%s"
                    % context._port['device_owner'])

        tags.append("openstack_vm-%s" % context._port['device_id'])

        tags.append("openstack_vm_image-%s" % host.image['id'])

        tags.append("openstack_vm_flavor-%s" % host.flavor['id'])

        tags.append("openstack_vm_host-%s"
                    % host.__getattr__('OS-EXT-SRV-ATTR:host'))

        tags.append("openstack_vm_user-%s" % host.user_id)

        for sg in context._port['security_groups']:
            tags.append("openstack_security_group-%s" % sg)

        return tags

    def _get_port_ip(self, context, port):
        ip = port['fixed_ips'][0]
        subnet = context._plugin.get_subnet(context._plugin_context,
                                            ip['subnet_id'])
        return "%s/%s" % (ip['ip_address'],
                          IPNetwork(subnet['cidr']).prefixlen)

    def _get_routers(self, context):
        query = context._plugin_context.session.query(Router)
        query = query.join(pan_db.PanDeviceReservation,
                           Router.id == pan_db.PanDeviceReservation.router_id)
        query = query.join(Port, Router.id == Port.device_id)
        query = query.join(Network, Port.network_id == Network.id)
        query = query.filter(Network.id == context._port['network_id'])

        routers = query.all()
        return routers

    def _save_tags_to_db(self, context, tags):
        with context._plugin_context.session.begin(subtransactions=True):
            for tag in tags:
                ref = PortMetadata(port_id=context._port['id'],
                                   data=tag)
                context._plugin_context.session.add(ref)

    def _get_tags_from_db(self, context, port_id):
        result = context._plugin_context.session.query(PortMetadata).\
            filter(PortMetadata.port_id == port_id).all()
        return [item['data'] for item in result]
