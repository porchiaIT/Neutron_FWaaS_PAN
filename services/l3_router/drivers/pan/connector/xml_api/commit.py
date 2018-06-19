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
# @author: Kevin Steves, kevin.steves@pobox.com

from __future__ import print_function

from neutron.openstack.common import log as logging

LOG = logging.getLogger(__name__)

_valid_part = set([
    'device-and-network-excluded',
    'policy-and-objects-excluded',
    'shared-object-excluded',
    'no-vsys',
    'vsys'])

_part_xml = {
    'device-and-network-excluded':
    '<device-and-network>excluded</device-and-network>',
    'policy-and-objects-excluded':
    '<policy-and-objects>excluded</policy-and-objects>',
    'shared-object-excluded':
    '<shared-object>excluded</shared-object>',
    'no-vsys':
    '<no-vsys></no-vsys>',
    'vsys':
    '<member>%s</member>'}


def valid_part(part):
    return part in _valid_part


class PanCommit:
    def __init__(self,
                 force=False,
                 commit_all=False,
                 merge_with_candidate=False):
        self._force = force
        self._commit_all = commit_all
        self._merge_with_candidate = merge_with_candidate
        self.partial = set()
        self._vsys = set()
        self._device = None
        self._device_group = None

    def force(self):
        self._force = True

    def commit_all(self):
        self._commit_all = True

    def merge_with_candidate(self):
        self._merge_with_candidate = True

    def device_and_network_excluded(self):
        part = 'device-and-network-excluded'
        self.partial.add(part)

    def policy_and_objects_excluded(self):
        part = 'policy-and-objects-excluded'
        self.partial.add(part)

    def shared_object_excluded(self):
        part = 'shared-object-excluded'
        self.partial.add(part)

    def no_vsys(self):
        part = 'no-vsys'
        self.partial.add(part)

    def vsys(self, vsys):
        if not self._commit_all:
            part = 'vsys'
            self.partial.add(part)

        if isinstance(vsys, str):
            vsys = [vsys]
        for name in vsys:
            self._vsys.add(name)

    def device(self, serial):
        self._device = serial

    def device_group(self, device_group):
        self._device_group = device_group

    def cmd(self):
        if self._commit_all:
            return self.__commit_all()
        else:
            return self.__commit()

    def __commit_all(self):
        s = '<commit-all><shared-policy>'

        if self._device:
            s += '<device>%s</device>' % self._device

        if self._device_group:
            s += '<device-group>%s</device-group>' % self._device_group

        # default when no <merge-with-candidate-cfg/> is 'yes'
        # we default to 'no' like the Web UI
        merge_xml = '<merge-with-candidate-cfg>%s</merge-with-candidate-cfg>'
        if self._merge_with_candidate:
            merge = 'yes'
        else:
            merge = 'no'
        s += merge_xml % merge

        if self._vsys:
            s += '<vsys>%s</vsys>' % self._vsys.pop()

        s += '</shared-policy></commit-all>'

        LOG.debug(_('commit-all cmd:'), s)

        return s

    def __commit(self):
        s = '<commit>'

        if self._force:
            s += '<force>'

        if self.partial:
            s += '<partial>'
        for part in self.partial:
            if part in _part_xml:
                if part == 'vsys':
                    s += '<vsys>'
                    for name in self._vsys:
                        xml_vsys = _part_xml[part] % name
                        s += xml_vsys
                    s += '</vsys>'
                else:
                    s += _part_xml[part]
        if self.partial:
            s += '</partial>'

        if self._force:
            s += '</force>'

        s += '</commit>'

        LOG.debug(_('commit cmd:'), s)

        return s
