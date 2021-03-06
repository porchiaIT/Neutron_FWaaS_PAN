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
# @author: Gary Duan, gduan@varmour.com, vArmour Networks
# @author: Aleks Chirko, Mirantis, Inc.

from neutron.services.l3_router.drivers import base as l3_base_driver


class L3AgentDriver(l3_base_driver.L3RouterBaseDriver):

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
