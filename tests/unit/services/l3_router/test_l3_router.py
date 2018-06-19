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

import __builtin__
import mock

from neutron.extensions import l3
from neutron.services.l3_router.drivers import base as l3_router_driver_base
from neutron.services.l3_router import l3_router_plugin
from neutron.tests import base


class FakeL3Db(l3.RouterPluginBase):

    def create_router(self, context, router):
        pass

    def update_router(self, context, id, router):
        pass

    def get_router(self, context, id, fields=None):
        pass

    def delete_router(self, context, id):
        pass

    def get_routers(self, context, filters=None, fields=None,
                    sorts=None, limit=None, marker=None, page_reverse=False):
        pass

    def add_router_interface(self, context, router_id, interface_info):
        pass

    def remove_router_interface(self, context, router_id, interface_info):
        pass

    def create_floatingip(self, context, floatingip):
        pass

    def update_floatingip(self, context, id, floatingip):
        pass

    def get_floatingip(self, context, id, fields=None):
        pass

    def delete_floatingip(self, context, id):
        pass

    def get_floatingips(self, context, filters=None, fields=None,
                        sorts=None, limit=None, marker=None,
                        page_reverse=False):
        pass


class FakeL3RouterDriver(l3_router_driver_base.L3RouterBaseDriver):

    def create_router_precommit(self, context, r_ctx):
        pass

    def create_router_postcommit(self, context, r_ctx):
        pass

    def update_router_precommit(self, context, r_ctx):
        pass

    def update_router_postcommit(self, context, r_ctx):
        pass

    def delete_router_precommit(self, context, r_ctx):
        pass

    def delete_router_postcommit(self, context, r_ctx):
        pass

    def add_router_interface_precommit(self, context, rp_ctx):
        pass

    def add_router_interface_postcommit(self, context, rp_ctx):
        pass

    def remove_router_interface_precommit(self, context, rp_ctx):
        pass

    def remove_router_interface_postcommit(self, context, rp_ctx):
        pass

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


class FakeRouterContext(object):

    def __init__(self, router, old_router=None, update=None):
        self._router = router
        self._original_router = old_router
        self._router_update = update

    def __eq__(self, other):
        return (self._router == other._router and
                self._original_router == other._original_router and
                self._router_update == other._router_update)


class FakeRouterPortContext(object):

    def __init__(self, port, old_port=None):
        self._port = port
        self._original_port = old_port

    def __eq__(self, other):
        return (self._port == other._port and
                self._original_port == other._original_port)


class FakeContext(object):
    @property
    def session(self):
        return FakeDbSession()


class FakeDbSession(object):
    def begin(self, subtransactions=False, nested=False):
        return FakeDbTransaction()


class FakeDbTransaction(object):
    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        pass

fake_user_router = {'router': {'name': 'fake router'}}

fake_db_router = {'id': 'fake router id',
                  'tenant_id': 'fake tenant id',
                  'name': 'fake router'}

fake_router_interface = {'port_id': 'fake port id'}

fake_db_port = {'id': 'fake port id',
                'name': 'fake port'}


@mock.patch.object(l3_router_plugin, "RouterContext", FakeRouterContext)
@mock.patch.object(l3_router_plugin, "RouterPortContext",
                   FakeRouterPortContext)
@mock.patch.object(FakeDbTransaction, "__exit__", mock.Mock())
@mock.patch.object(FakeDbTransaction, "__enter__",
                   mock.Mock(return_value=FakeDbTransaction()))
class TestL3RouterWithDriver(base.BaseTestCase):

    @mock.patch.object(l3_router_plugin.L3RouterPlugin, "setup_rpc",
                       mock.Mock(return_value=None))
    def setUp(self):
        super(TestL3RouterWithDriver, self).setUp()
        self.router_plugin = l3_router_plugin.L3RouterPlugin()
        self.router_plugin
        self.router_plugin.driver = FakeL3RouterDriver()
        self.fake_context = FakeContext()

    @mock.patch.object(FakeL3RouterDriver, "create_router_precommit",
                       mock.Mock())
    @mock.patch.object(FakeL3RouterDriver, "create_router_postcommit",
                       mock.Mock())
    @mock.patch.object(FakeL3Db, "create_router",
                       mock.Mock(return_value=fake_db_router))
    def test_create_router(self):
        router_context = FakeRouterContext(fake_db_router)

        with mock.patch.object(__builtin__, 'super',
                               mock.Mock(return_value=FakeL3Db())):
            self.router_plugin.create_router(self.fake_context,
                                             fake_user_router)

            __builtin__.super.assert_called_once_with(
                l3_router_plugin.L3RouterPlugin,
                self.router_plugin)
            FakeL3Db.create_router.assert_called_once_with(self.fake_context,
                                                           fake_user_router)
            self.router_plugin.driver.create_router_precommit.\
                assert_called_once_with(self.fake_context, router_context)
            self.router_plugin.driver.create_router_postcommit.\
                assert_called_once_with(self.fake_context, router_context)

    @mock.patch.object(FakeL3RouterDriver, "update_router_precommit",
                       mock.Mock())
    @mock.patch.object(FakeL3RouterDriver, "update_router_postcommit",
                       mock.Mock())
    def test_update_router(self):
        router_id = fake_db_router['id']
        update_dict = {'router': {'name': 'new name'}}
        old_db_router = dict(fake_db_router)
        updated_db_router = dict(fake_db_router)
        updated_db_router.update(update_dict)
        router_context = FakeRouterContext(updated_db_router,
                                           old_db_router,
                                           update_dict['router'])

        with mock.patch.object(FakeL3Db, 'update_router',
                               mock.Mock(return_value=updated_db_router)):
            with mock.patch.object(self.router_plugin, 'get_router',
                                   mock.Mock(return_value=old_db_router)):
                with mock.patch.object(__builtin__, 'super',
                                       mock.Mock(return_value=FakeL3Db())):
                    self.router_plugin.update_router(self.fake_context,
                                                     router_id,
                                                     update_dict)

                    __builtin__.super.assert_called_once_with(
                        l3_router_plugin.L3RouterPlugin,
                        self.router_plugin)
                    FakeL3Db.update_router.assert_called_once_with(
                        self.fake_context, router_id, update_dict)
                    self.router_plugin.driver.update_router_precommit.\
                        assert_called_once_with(self.fake_context,
                                                router_context)
                    self.router_plugin.driver.update_router_postcommit.\
                        assert_called_once_with(self.fake_context,
                                                router_context)

    @mock.patch.object(FakeL3RouterDriver, "delete_router_precommit",
                       mock.Mock())
    @mock.patch.object(FakeL3RouterDriver, "delete_router_postcommit",
                       mock.Mock())
    @mock.patch.object(FakeL3Db, "delete_router", mock.Mock())
    def test_delete_router(self):
        router_id = fake_db_router['id']
        router_context = FakeRouterContext(None, fake_db_router)

        with mock.patch.object(self.router_plugin, 'get_router',
                               mock.Mock(return_value=fake_db_router)):
            with mock.patch.object(__builtin__, 'super',
                                   mock.Mock(return_value=FakeL3Db())):
                self.router_plugin.delete_router(self.fake_context,
                                                 router_id)

                __builtin__.super.assert_called_once_with(
                    l3_router_plugin.L3RouterPlugin,
                    self.router_plugin)
                FakeL3Db.delete_router.assert_called_once_with(
                    self.fake_context, router_id)
                self.router_plugin.driver.delete_router_precommit.\
                    assert_called_once_with(self.fake_context,
                                            router_context)
                self.router_plugin.driver.delete_router_postcommit.\
                    assert_called_once_with(self.fake_context,
                                            router_context)

    @mock.patch.object(FakeL3RouterDriver, "add_router_interface_precommit",
                       mock.Mock())
    @mock.patch.object(FakeL3RouterDriver, "add_router_interface_postcommit",
                       mock.Mock())
    @mock.patch.object(FakeL3Db, "add_router_interface",
                       mock.Mock(return_value=fake_router_interface))
    def test_add_router_interface(self):
        router_id = fake_db_router['id']
        iface_context = FakeRouterPortContext(fake_db_port)

        with mock.patch.object(self.router_plugin, 'get_port',
                               mock.Mock(return_value=fake_db_port)):
            with mock.patch.object(__builtin__, 'super',
                                   mock.Mock(return_value=FakeL3Db())):
                self.router_plugin.add_router_interface(self.fake_context,
                                                        router_id,
                                                        fake_router_interface)

                __builtin__.super.assert_called_once_with(
                    l3_router_plugin.L3RouterPlugin,
                    self.router_plugin)
                FakeL3Db.add_router_interface.assert_called_once_with(
                    self.fake_context, router_id, fake_router_interface)
                self.router_plugin.driver.add_router_interface_precommit.\
                    assert_called_once_with(self.fake_context,
                                            iface_context)
                self.router_plugin.driver.add_router_interface_postcommit.\
                    assert_called_once_with(self.fake_context,
                                            iface_context)

    @mock.patch.object(FakeL3RouterDriver, "remove_router_interface_precommit",
                       mock.Mock())
    @mock.patch.object(FakeL3RouterDriver,
                       "remove_router_interface_postcommit",
                       mock.Mock())
    @mock.patch.object(FakeL3Db, "remove_router_interface",
                       mock.Mock(return_value=fake_router_interface))
    def test_remove_router_interface_with_port_id(self):
        router_id = fake_db_router['id']
        iface_context = FakeRouterPortContext(None, fake_db_port)

        with mock.patch.object(self.router_plugin, 'get_port',
                               mock.Mock(return_value=fake_db_port)):
            with mock.patch.object(__builtin__, 'super',
                                   mock.Mock(return_value=FakeL3Db())):
                self.router_plugin.remove_router_interface(
                    self.fake_context, router_id, fake_router_interface)

                __builtin__.super.assert_called_once_with(
                    l3_router_plugin.L3RouterPlugin,
                    self.router_plugin)
                FakeL3Db.remove_router_interface.assert_called_once_with(
                    self.fake_context, router_id, fake_router_interface)
                self.router_plugin.driver.remove_router_interface_precommit.\
                    assert_called_once_with(self.fake_context,
                                            iface_context)
                self.router_plugin.driver.remove_router_interface_postcommit.\
                    assert_called_once_with(self.fake_context,
                                            iface_context)
