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
import sys
import xml.etree.ElementTree as etree
#import lxml.etree as etree

from neutron.openstack.common import log as logging
from neutron.services.l3_router.drivers.pan.connector.xml_api \
    import __version__

LOG = logging.getLogger(__name__)

_encoding = 'utf-8'
_tags_forcelist = set(['entry', 'member'])


class PanConfigError(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return self.msg


class PanConfig:
    def __init__(self,
                 config=None,
                 tags_forcelist=_tags_forcelist):
        self._config_version = 0  # 0 indicates not yet set
        self._config_panorama = None
        self._config_multi_vsys = None

        LOG.debug(_('Python version: %s'), sys.version)
        LOG.debug(_('xml.etree.ElementTree version: %s'), etree.VERSION)
        LOG.debug(_('pan-python version: %s'), __version__)

        if config is None:
            raise PanConfigError('no config')
        LOG.debug(_('Config type: %s'), type(config))

        if hasattr(config, 'tag'):
            self.config_root = config
        else:
            try:
                self.config_root = etree.fromstring(config)
            except etree.ParseError as msg:
                raise PanConfigError('ElementTree.fromstring ParseError: %s'
                                     % msg)
        LOG.debug(_('config_root: %s'), self.config_root)

    def __find_xpath(self, xpath=None):
# Not a true Xpath
# http://docs.python.org/dev/library/xml.etree.elementtree.html#xpath-support
        LOG.debug(_('xpath: %s'), xpath)
        if xpath:
            try:
                nodes = self.config_root.findall(xpath)
            except SyntaxError as msg:
                raise PanConfigError('ElementTree.find SyntaxError: %s' % msg)
        else:
            nodes = [self.config_root]

        LOG.debug(_('xpath nodes: %s'), nodes)

        return nodes

    def config_version(self):
        if self._config_version != 0:
            return self._config_version

        self._config_version = None
        if self.config_root.tag == 'config':
            self._config_version = \
                self.config_root.get('version', default=None)

        return self._config_version

    def config_panorama(self):
        if self._config_panorama is not None:
            return self._config_panorama

        xpaths = [
            "./panorama",
            "./devices/entry[@name='localhost.localdomain']/device-group",
        ]
        if self.config_root.tag == 'config':
            for xpath in xpaths:
                elem = self.config_root.find(xpath)
                if elem is not None:
                    self._config_panorama = True
                    break
            else:
                self._config_panorama = False

        return self._config_panorama

    def config_multi_vsys(self):
        if self._config_multi_vsys is not None:
            return self._config_multi_vsys

        path = "./devices/entry[@name='localhost.localdomain']/vsys/entry"
        if self.config_root.tag == 'config':
            nodes = self.config_root.findall(path)
            if len(nodes) > 1:
                self._config_multi_vsys = True
            else:
                self._config_multi_vsys = False

        return self._config_multi_vsys

    def xml(self, xpath=None):
        nodes = self.__find_xpath(xpath)
        if not nodes:
            return None

        s = ''.encode()
        for elem in nodes:
            s += etree.tostring(elem, encoding=_encoding)

        if not s:
            return None

        LOG.debug(_('xml: %s'), type(s))
        LOG.debug(_('xml.decode(): %s'), type(s.decode(_encoding)))
        return s.decode(_encoding)

    def python(self, xpath=None):
        nodes = self.__find_xpath(xpath)
        if not nodes:
            return None

        d = {}
        if len(nodes) > 1:
            for elem in nodes:
                d[elem.tag] = {}
                self.__serialize_py(elem, d[elem.tag])
        else:
            self.__serialize_py(nodes[0], d)

        return d

    def __serialize_py(self, elem, obj, forcelist=False):
        tag = elem.tag
        text = elem.text
        text_strip = None
        if text:
            text_strip = text.strip()
        attrs = elem.items()

        LOG.debug(_('TAG(forcelist=%(forcelist)s): "%(tag)s"'),
                  {'forcelist': forcelist,
                   'tag': tag})

        if forcelist:
            if tag not in obj:
                obj[tag] = []
            if not len(elem) and not text_strip and not attrs:
                obj[tag].append(None)
                return
            if not len(elem) and text_strip and not attrs:
                obj[tag].append(text)
                return

            obj[tag].append({})
            o = obj[tag][-1]

        else:
            if not len(elem) and not text_strip and not attrs:
                obj[tag] = None
                return
            if not len(elem) and text_strip and not attrs:
                if text_strip == 'yes':
                    obj[tag] = True
                elif text_strip == 'no':
                    obj[tag] = False
                else:
                    obj[tag] = text
                return

            obj[tag] = {}
            o = obj[tag]

        for k, v in attrs:
#            o['@' + k] = v
            o[k] = v

        if text_strip:
            o[tag] = text

        if len(elem):
            tags = {}
            for e in elem:
                if e.tag in tags:
                    tags[e.tag] += 1
                else:
                    tags[e.tag] = 1
            for e in elem:
                forcelist = False
                if e.tag in _tags_forcelist or tags[e.tag] > 1:
                    forcelist = True
                self.__serialize_py(e, o, forcelist)

    def flat(self, path, xpath=None):
        nodes = self.__find_xpath(xpath)
        if not nodes:
            return None

        obj = []
        for elem in nodes:
            self.__serialize_flat(elem, path + elem.tag, obj)

        return obj

    def __serialize_flat(self, elem, path, obj):
        tag = elem.tag
        text = elem.text
        text_strip = None
        if text:
            text_strip = text.strip()
        attrs = elem.items()

        LOG.debug(_('TAG(elem=%(index)d): "%(tag)s"'),
                  {'index': len(elem),
                   'tag': tag})
        LOG.debug(_('text_strip: "%s"'), text_strip)
        LOG.debug(_('attrs: %s'), attrs)
        LOG.debug(_('path: "%s"'), path)
        LOG.debug(_('obj: %s'), obj)

        if not text_strip:
            obj.append(path)
        elif text_strip:
            lines = text.splitlines()
            if len(lines) > 1:
                n = 1
                for line in lines:
                    s = path + '[%d]="%s"' % (n, line)
                    obj.append(s)
                    n += 1
            else:
                s = path + '="%s"' % text
                obj.append(s)

        for k, v in attrs:
            path += "[@%s='%s']" % (k, v)
            obj.append(path)

        for e in elem:
            self.__serialize_flat(e, path + '/' + e.tag, obj)

    def __quote_space(self, s):
        # XXX string with " etc.
        if ' ' in s:
            return '"%s"' % s
        return s

    def set_cli(self, path, xpath=None, member_list=False):
        nodes = self.__find_xpath(xpath)
        if not nodes:
            return None

        obj = []
        for elem in nodes:
            self.__serialize_set_cli(elem, path + elem.tag, obj,
                                     member_list)

        return obj

    def __serialize_set_cli(self, elem, path, obj, member_list=False):
        tag = elem.tag
        text = elem.text
        text_strip = None
        if text:
            text_strip = text.strip()
        attrs = elem.items()

        LOG.debug(_('TAG(elem=%(index)d member_list=%(member_list)s): '
                    '"%(tag)s"'),
                  {'index': len(elem),
                   'member_list': member_list,
                   'tag': tag})
        LOG.debug(_('text_strip: "%s"'), text_strip)
        LOG.debug(_('attrs: %s'), attrs)
        LOG.debug(_('path: "%s"'), path)
        LOG.debug(_('obj: %s'), obj)

        for k, v in attrs:
            if k == 'name':
                path += ' ' + self.__quote_space(v)

        if member_list:
            nodes = elem.findall('./member')
            LOG.debug(_('TAG(members=%(num)d): "%(tag)s"'),
                      {'num': len(nodes),
                       'tag': tag})
            if len(nodes) > 1:
                members = []
                for e in nodes:
                    members.append(self.__quote_space(e.text))
                path += ' [ ' + ' '.join(members) + ' ]'
                obj.append(path)
                return

        if not len(elem):
            if text_strip:
                path += ' ' + self.__quote_space(text)
            obj.append(path)

        for e in elem:
            tpath = path
            if e.tag not in ['entry', 'member']:
                tpath += ' ' + e.tag
            self.__serialize_set_cli(e, tpath, obj, member_list)
