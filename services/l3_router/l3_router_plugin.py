# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (c) 2013 OpenStack Foundation.
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
# @author: Bob Melander, Cisco Systems, Inc.
# @author: Gary Duan, gduan@varmour.com, vArmour Networks

from oslo.config import cfg
from sqlalchemy.orm import exc

from neutron.api.rpc.agentnotifiers import l3_rpc_agent_api
from neutron.common import constants as q_const
from neutron.common import rpc as q_rpc
from neutron.common import topics
from neutron.db import api as qdbapi
from neutron.db import db_base_plugin_v2
from neutron.db import extraroute_db
from neutron.db import l3_agentschedulers_db
from neutron.db import l3_db
from neutron.db import l3_gwmode_db
from neutron.db import l3_rpc_base
from neutron.db import model_base
from neutron.db import models_v2
from neutron.openstack.common import importutils
from neutron.openstack.common import rpc
from neutron.plugins.common import constants

OPTS = [
    cfg.StrOpt(
        'l3_driver',
        default='neutron.services.l3_router.drivers.l3_agent_driver.'
                'L3AgentDriver',
        help=_("Driver for L3 service plugin")),
]

cfg.CONF.register_opts(OPTS)


class L3DriverContext(object):

    def __init__(self):
        # this is used to pass parameters from precommit() to postcommit()
        self._params = {}

    @property
    def params(self):
        return self._params

    @params.setter
    def params(self, value):
        self._params = value


class RouterContext(L3DriverContext):

    def __init__(self, router, old_router=None, router_update=None):
        self._router = router
        self._original_router = old_router
        self._router_update = router_update

    @property
    def current(self):
        return self._router

    @property
    def original(self):
        return self._original_router

    @property
    def update(self):
        return self._router_update


class RouterPortContext(L3DriverContext):

    def __init__(self, port, old_port=None):
        self._port = port
        self._original_port = old_port

    @property
    def current(self):
        return self._port

    @property
    def original(self):
        return self._original_port

    @property
    def current_router_id(self):
        return self._port.get('device_id')

    @property
    def original_router_id(self):
        return self._original_port.get('device_id')


class FloatingIPContext(L3DriverContext):

    def __init__(self, fip, old_fip=None):
        self._fip = fip
        self._original_fip = old_fip

    @property
    def current(self):
        return self._fip

    @property
    def original(self):
        return self._original_fip

    @property
    def current_router_id(self):
        return self._fip.get('router_id')

    @property
    def original_router_id(self):
        return self._original_fip.get('router_id')


class L3RouterPluginRpcCallbacks(l3_rpc_base.L3RpcCallbackMixin):

    RPC_API_VERSION = '1.1'

    def create_rpc_dispatcher(self):
        """Get the rpc dispatcher for this manager.

        If a manager would like to set an rpc API version, or support more than
        one class as the target of rpc messages, override this method.
        """
        return q_rpc.PluginRpcDispatcher([self])


class L3RouterPlugin(db_base_plugin_v2.NeutronDbPluginV2,
                     extraroute_db.ExtraRoute_db_mixin,
                     l3_gwmode_db.L3_NAT_db_mixin,
                     l3_agentschedulers_db.L3AgentSchedulerDbMixin):

    """Implementation of the Neutron L3 Router Service Plugin.

    This class implements a L3 service plugin that provides
    router and floatingip resources and manages associated
    request/response.
    All DB related work is implemented in classes
    l3_db.L3_NAT_db_mixin and extraroute_db.ExtraRoute_db_mixin.
    """
    supported_extension_aliases = ["router", "ext-gw-mode",
                                   "extraroute", "l3_agent_scheduler"]

    def __init__(self):
        qdbapi.register_models(base=model_base.BASEV2)
        self.setup_rpc()
        self.router_scheduler = importutils.import_object(
            cfg.CONF.router_scheduler_driver)
        self.driver = importutils.import_object(cfg.CONF.l3_driver)

    def setup_rpc(self):
        # RPC support
        self.topic = topics.L3PLUGIN
        self.conn = rpc.create_connection(new=True)
        self.agent_notifiers.update(
            {q_const.AGENT_TYPE_L3: l3_rpc_agent_api.L3AgentNotify})
        self.callbacks = L3RouterPluginRpcCallbacks()
        self.dispatcher = self.callbacks.create_rpc_dispatcher()
        self.conn.create_consumer(self.topic, self.dispatcher,
                                  fanout=False)
        self.conn.consume_in_thread()

    def get_plugin_type(self):
        return constants.L3_ROUTER_NAT

    def get_plugin_description(self):
        """returns string description of the plugin."""
        return ("L3 Router Service Plugin for basic L3 forwarding"
                " between (L2) Neutron networks and access to external"
                " networks via a NAT gateway.")

    def create_floatingip(self, context, floatingip):
        """Create floating IP.

        :param context: Neutron request context
        :param floatingip: data fo the floating IP being created
        :returns: A floating IP object on success

        AS the l3 router plugin aysnchrounously creates floating IPs
        leveraging tehe l3 agent, the initial status fro the floating
        IP object will be DOWN.
        """
        return super(L3RouterPlugin, self).create_floatingip(
            context, floatingip,
            initial_status=q_const.FLOATINGIP_STATUS_DOWN)

    def create_router(self, context, router):
        """Create Neutron router.

        @param context: contain user information
        @param router: dict with router info given by the user
        @return: dict with router info
        """
        r_data = router['router']

        with context.session.begin(subtransactions=True):
            r = super(L3RouterPlugin, self).create_router(context,
                                                          {'router': r_data})

            r_ctx = RouterContext(r)
            self.driver.create_router_precommit(context, r_ctx)

        self.driver.create_router_postcommit(context, r_ctx)

        return r

    def update_router(self, context, id, router):
        """Update Neutron router data.

        @param context: contain user information
        @param id: id of the router to be updated
        @param router: dict with router info to update
        @return: dict with router info after update
        """
        update = dict(router['router'])
        with context.session.begin(subtransactions=True):
            old_r = self.get_router(context, id)
            r = super(L3RouterPlugin, self).update_router(context, id, router)
            r_ctx = RouterContext(r, old_r, update)
            self.driver.update_router_precommit(context, r_ctx)

        self.driver.update_router_postcommit(context, r_ctx)

        return r

    def delete_router(self, context, id):
        """Delete Neutron router.

        @param context: contain user information
        @param id: id of the router to be deleted
        @return: None
        """
        with context.session.begin(subtransactions=True):
            old_r = self.get_router(context, id)
            super(L3RouterPlugin, self).delete_router(context, id)
            r_ctx = RouterContext(None, old_r)
            self.driver.delete_router_precommit(context, r_ctx)

        self.driver.delete_router_postcommit(context, r_ctx)

    def add_router_interface(self, context, id, interface_info):
        """Add interface to Neutron router.

        @param context: contain user information
        @param id: id of the router to add interface to
        @param interface_info: dict with interface info
        @return: dict with Neutron port info
        """
        with context.session.begin(subtransactions=True):
            ret = super(L3RouterPlugin, self).add_router_interface(
                context, id, interface_info)
            p = self.get_port(context, ret['port_id'])
            rp_ctx = RouterPortContext(p)
            self.driver.add_router_interface_precommit(context, rp_ctx)

        self.driver.add_router_interface_postcommit(context, rp_ctx)

        return ret

    def remove_router_interface(self, context, id, interface_info):
        """Remove interface from Neutron router.

        @param context: contain user information
        @param id: id of the router to remove interface from
        @param interface_info: dict with interface info
        @return: dict with removed interface info
        """
        if 'port_id' in interface_info:
            old_p = self.get_port(context, interface_info['port_id'])
        elif 'subnet_id' in interface_info:
            subnet_id = interface_info['subnet_id']
            subnet = self._get_subnet(context, subnet_id)

            try:
                rport_qry = context.session.query(models_v2.Port)
                ports = rport_qry.filter_by(
                    device_id=id,
                    device_owner=q_const.DEVICE_OWNER_ROUTER_INTF,
                    network_id=subnet['network_id'])

                for p in ports:
                    if p['fixed_ips'][0]['subnet_id'] == subnet_id:
                        old_p = self.get_port(context, p['id'])
                        break
            except exc.NoResultFound:
                pass

        with context.session.begin(subtransactions=True):
            ret = super(L3RouterPlugin, self).remove_router_interface(
                context, id, interface_info)
            rp_ctx = RouterPortContext(None, old_p)
            self.driver.remove_router_interface_precommit(context, rp_ctx)

        self.driver.remove_router_interface_postcommit(context, rp_ctx)
        return ret

    def create_floatingip(self, context, floatingip):
        """Create floating ip.

        @param context: contain user information
        @param floatingip: dict with floating ip info given by the user
        @return: dict with removed interface info
        """
        fip = floatingip['floatingip']
        fixed_port = None
        if 'port_id' in fip and fip['port_id']:
            fixed_port = fip['port_id']
            del fip['port_id']

        fip = super(L3RouterPlugin, self).create_floatingip(context,
                                                            floatingip)

        if fixed_port:
            return self.update_floatingip(
                context, fip['id'], {'floatingip': {'port_id': fixed_port}})

        return fip

    def update_floatingip(self, context, id, floatingip):
        """Update floating ip.

        @param context: contain user information
        @param id: id of the floating ip to update
        @param floatingip: dict with update data
        @return: dict with updated floating ip info
        """
        old_fip = self.get_floatingip(context, id)
        fip = floatingip['floatingip']
        fip['tenant_id'] = old_fip['tenant_id']
        old_router_id = self._get_router_by_floatingip(context, old_fip)
        new_router_id = None
        if 'port_id' in fip and fip['port_id']:
            new_router_id = self._get_router_by_internal_port(
                context, fip, old_fip['floating_network_id'])

        if not old_router_id and not new_router_id:
            return super(L3RouterPlugin, self).update_floatingip(context, id,
                                                                 floatingip)

        if old_router_id and old_router_id == new_router_id:
            with context.session.begin(subtransactions=True):
                fip = super(L3RouterPlugin, self).update_floatingip(
                    context, id, floatingip)
                fip_ctx = FloatingIPContext(fip, old_fip)
                self.driver.update_floatingip_precommit(context, fip_ctx)

            self.driver.update_floatingip_postcommit(context, fip_ctx)
            return fip

        with context.session.begin(subtransactions=True):
            fip = super(L3RouterPlugin, self).update_floatingip(
                context, id, floatingip)

            if old_router_id and new_router_id:
                fip_ctx = FloatingIPContext(fip, old_fip)
            elif old_router_id:
                fip_ctx = FloatingIPContext(None, old_fip)
            elif new_router_id:
                fip_ctx = FloatingIPContext(fip)

            self.driver.update_floatingip_precommit(context, fip_ctx)

        self.driver.update_floatingip_postcommit(context, fip_ctx)

        return fip

    def delete_floatingip(self, context, id):
        """Delete floating ip.

        @param context: contain user information
        @param id: id of the floating ip to delete
        @return: None
        """
        old_fip = self.get_floatingip(context, id)
        router_id = self._get_router_by_floatingip(context, old_fip)
        if router_id:
            with context.session.begin(subtransactions=True):
                super(L3RouterPlugin, self).delete_floatingip(context, id)
                fip_ctx = FloatingIPContext(None, old_fip)
                self.driver.delete_floatingip_precommit(context, fip_ctx)

            self.driver.delete_floatingip_postcommit(context, fip_ctx)
        else:
            super(L3RouterPlugin, self).delete_floatingip(context, id)

    def disassociate_floatingips(self, context, port_id, do_notify=True):
        """Disassociate floating ip from Neutron port.

        @param context: contain user information
        @param port_id: id of the Neutron port to dissociate from
        @param do_notify: currently ignored
        @return: None
        """
        with context.session.begin(subtransactions=True):
            try:
                fip_qry = context.session.query(l3_db.FloatingIP)
                old_fip = fip_qry.filter_by(fixed_port_id=port_id).one()
                current_fip = super(L3RouterPlugin, self).delete_floatingip(
                    context, port_id)
                fip_ctx = FloatingIPContext(current_fip, old_fip)
                self.driver.disassociate_floatingip_precommit(context, fip_ctx)
            except exc.NoResultFound:
                return
            except exc.MultipleResultsFound:
                # should never happen
                raise Exception(_('Multiple floating IPs found for port %s')
                                % port_id)
        self.driver.disassociate_floatingip_postcommit(context, fip_ctx)

    def _get_router_by_floatingip(self, context, fip_db):
        return fip_db['router_id'] if 'router_id' in fip_db else None

    def _get_router_by_internal_port(self, context, fip, floating_network_id):
        (internal_port, internal_subnet_id,
         internal_ip_address) = self._internal_fip_assoc_data(context, fip)

        return self._get_router_for_floatingip(context,
                                               internal_port,
                                               internal_subnet_id,
                                               floating_network_id)
