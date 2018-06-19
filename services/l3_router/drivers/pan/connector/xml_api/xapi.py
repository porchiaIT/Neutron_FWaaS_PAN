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

"""Interface to the PAN-OS XML API

The pan.xapi module implements the PanXapi class.  It provides an
interface to the XML API on Palo Alto Networks' Next-Generation
Firewalls.
"""

from __future__ import print_function
import re
import sys
import time

from urllib2 import Request, urlopen, URLError
from urllib import urlencode

import xml.etree.ElementTree as etree

from neutron.openstack.common import log as logging
from neutron.services.l3_router.drivers.pan.connector.xml_api \
    import __version__
from neutron.services.l3_router.drivers.pan.connector.xml_api \
    import config as pan_config

LOG = logging.getLogger(__name__)
_encoding = 'utf-8'
_job_query_interval = 0.5


class PanXapiError(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        if self.msg is None:
            return ''
        return self.msg


class PanXapi:
    def __init__(self,
                 tag=None,
                 api_username=None,
                 api_password=None,
                 api_key=None,
                 hostname=None,
                 port=None,
                 serial=None,
                 use_http=False,
                 use_get=False,
                 timeout=None,
                 cafile=None,
                 capath=None):
        self.tag = tag
        self.api_username = api_username
        self.api_password = api_password
        self.api_key = api_key
        self.hostname = hostname
        self.port = port
        self.serial = serial
        self.use_get = use_get
        self.timeout = timeout
        self.cafile = cafile
        self.capath = capath

        LOG.debug(_('Python version: %s'), sys.version)
        LOG.debug(_('xml.etree.ElementTree version: %s'), etree.VERSION)
        LOG.debug(_('pan-python version: %s'), __version__)

        if self.port is not None:
            try:
                self.port = int(self.port)
                if self.port < 1 or self.port > 65535:
                    raise ValueError
            except ValueError:
                raise PanXapiError('Invalid port: %s' % self.port)

        if self.timeout is not None:
            try:
                self.timeout = int(self.timeout)
                if not self.timeout > 0:
                    raise ValueError
            except ValueError:
                raise PanXapiError('Invalid timeout: %s' % self.timeout)

        if self.hostname is None:
            raise PanXapiError('hostname argument required')
        if self.api_key is None and (self.api_username is None or
                                     self.api_password is None):
            raise PanXapiError('api_key or api_username and ' +
                               'api_password arguments required')

        if use_http:
            scheme = 'http'
        else:
            scheme = 'https'

        self.uri = '%s://%s' % (scheme, self.hostname)
        if self.port is not None:
            self.uri += ':%s' % self.port
        self.uri += '/api/'

    def __str__(self):
        return '\n'.join((': '.join((k, str(self.__dict__[k]))))
                         for k in sorted(self.__dict__))

    def __clear_response(self):
        # XXX naming
        self.status = None
        self.status_code = None
        self.status_detail = None
        self.xml_document = None
        self.element_root = None
        self.element_result = None
        self.export_result = None

    def __get_header(self, response, name):
        """use getheader() method depending or urllib in use."""

        s = None
        types = set()

        if hasattr(response, 'getheader'):
            # 3.2, http.client.HTTPResponse
            s = response.getheader(name)
        elif hasattr(response.info(), 'getheader'):
            # 2.7, httplib.HTTPResponse
            s = response.info().getheader(name)
        else:
            raise PanXapiError('no getheader() method found in ' +
                               'urllib response')

        if s is not None:
            types = [type.lower() for type in s.split(';')]
            types = [type.lstrip() for type in types]
            types = [type.rstrip() for type in types]
            types = set(types)

        LOG.debug(_('__get_header(%(header)s): %(result)s'),
                  {'header': name,
                   'result': s})
        LOG.debug(_('__get_header: %s'), types)

        return types

    def __set_response(self, response):
        message_body = response.read()

        content_type = self.__get_header(response, 'content-type')
        if not content_type:
            self.status_detail = 'no content-type response header'
            return False

        if 'application/octet-stream' in content_type:
            return self.__set_stream_response(response, message_body)

        elif ('application/xml' in content_type and
              'charset=utf-8' in content_type):
            return self.__set_xml_response(message_body)
        else:
            msg = 'no handler for content-type: %s' % content_type
            self.status_detail = msg
            return False

    def __set_stream_response(self, response, message_body):
        content_disposition = self.__get_header(response,
                                                'content-disposition')
        if not content_disposition:
            self.status_detail = 'no content-disposition response header'
            return False

        if 'attachment' not in content_disposition:
            msg = 'no handler for content-disposition: %s' % \
                content_disposition
            self.status_detail = msg
            return False

        filename = None
        for type in content_disposition:
            result = re.search(r'^filename=([-\w]+)$', type)
            if result:
                filename = result.group(1)
                break

        export_result = {}
        export_result['file'] = filename
        export_result['content'] = message_body
        self.export_result = export_result
        self.status = 'success'
        return True

    def __set_xml_response(self, message_body):
        self.xml_document = message_body.decode(_encoding)

        try:
            element = etree.fromstring(message_body)
        except etree.ParseError as msg:
            self.status_detail = 'ElementTree.fromstring ParseError: %s' % msg
            return False
        # we probably won't see MemoryError when it happens but try to catch
        except MemoryError as msg:
            self.status_detail = 'ElementTree.fromstring MemoryError: %s' % msg
            return False
        except Exception as msg:
            self.status_detail = '%s: %s' % (sys.exc_info()[0].__name__, msg)
            return False

        self.element_root = element
        self.element_result = self.element_root.find('result')  # can be None

        LOG.debug(_('xml_document: %s'), self.xml_document)
        LOG.debug(_('message_body: %s'), type(message_body))
        LOG.debug(_('message_body.decode(): %s'), type(self.xml_document))

        response_attrib = self.element_root.attrib
        if not response_attrib:
            # XXX error?
            self.status_detail = 'no response element status attribute'
            return False

        if 'status' in response_attrib:
            self.status = response_attrib['status']
        if 'code' in response_attrib:
            self.status_code = response_attrib['code']

        self.status_detail = self.__get_response_msg()

        if self.status == 'success':
            return True
        else:
            return False

    def __get_response_msg(self):
        lines = []

        # XML API response message formats are not documented

        # type=user-id register and unregister
        path = './msg/line/uid-response/payload/*/entry'
        elem = self.element_root.findall(path)
        if len(elem) > 0:
            LOG.debug(_('path: %(path)s, element: %(elem)s'),
                      {'path': path,
                       'elem': elem})
            for line in elem:
                msg = ''
                for key in line.keys():
                    msg += '%s: %s ' % (key, line.get(key))
                if msg:
                    lines.append(msg.rstrip())
            return '\n'.join(lines) if lines else None

        path = './msg/line'
        elem = self.element_root.findall(path)
        if len(elem) > 0:
            LOG.debug(_('path: %(path)s, element: %(elem)s'),
                      {'path': path,
                       'elem': elem})
            for line in elem:
                if line.text is not None:
                    lines.append(line.text)
                else:
                    # <line><line>xxx</line></line>...
                    elem = line.find('line')
                    if elem is not None and elem.text is not None:
                        lines.append(elem.text)
            return '\n'.join(lines) if lines else None

        path = './result/msg/line'
        elem = self.element_root.findall(path)
        if len(elem) > 0:
            LOG.debug(_('path: %(path)s, element: %(elem)s'),
                      {'path': path,
                       'elem': elem})
            for line in elem:
                if line.text is not None:
                    lines.append(line.text)
            return '\n'.join(lines) if lines else None

        path = './result/msg'
        elem = self.element_root.find(path)
        if elem is not None:
            LOG.debug(_('path: %(path)s, element: %(elem)s'),
                      {'path': path,
                       'elem': elem})
            if elem.text is not None:
                lines.append(elem.text)
            return lines[0] if lines else None

        path = './msg'
        elem = self.element_root.find(path)
        if elem is not None:
            LOG.debug(_('path: %(path)s, element: %(elem)s'),
                      {'path': path,
                       'elem': elem})
            if elem.text is not None:
                lines.append(elem.text)
            return lines[0] if lines else None

        # 'show jobs id nn' and 'show jobs all' responses
        path = './result/job/details/line'
        elem = self.element_root.findall(path)
        if len(elem) > 0:
            LOG.debug(_('path: %(path)s, element: %(elem)s'),
                      {'path': path,
                       'elem': elem})
            for line in elem:
                if line.text is not None:
                    lines.append(line.text)
                else:
                    path = './newjob/newmsg'
                    elem2 = line.find(path)
                    if elem2 is not None and elem2.text is not None:
                        lines.append(elem2.text)
            return '\n'.join(lines) if lines else None

        return None

    # XXX store tostring() results?
    # XXX rework this
    def xml_root(self):
        if self.element_root is None:
            # May not be set due to ParseError, so return response
            return self.xml_document

        s = etree.tostring(self.element_root, encoding=_encoding)

        if not s:
            return None

        LOG.debug(_('xml_root: %s'), type(s))
        LOG.debug(_('xml_root.decode(): %s'), type(s.decode(_encoding)))
        return s.decode(_encoding)

    def xml_result(self):
        if self.element_result is None:
            return None

        s = ''.encode()
        for elem in self.element_result:
            s += etree.tostring(elem, encoding=_encoding)

        if not s:
            return None

        LOG.debug(_('xml_root: %s'), type(s))
        LOG.debug(_('xml_root.decode(): %s'), type(s.decode(_encoding)))
        return s.decode(_encoding)

    # XXX xml_python() is not documented
    # XXX not sure this should be here
    def xml_python(self, result=False):
        if result:
            if (self.element_result is None or
                    not len(self.element_result)):
                return None
            elem = list(self.element_result)[0]  # XXX
        else:
            if self.element_root is None:
                return None
            elem = self.element_root

        try:
            conf = pan_config.PanConfig(config=elem)
        except pan_config.PanConfigError as msg:
            raise PanXapiError('pan.config.PanConfigError: %s' % msg)

        return conf.python()

    def __api_request(self, query):
        # type=keygen request will urlencode key if needed so don't
        # double encode
        if 'key' in query:
            query2 = query.copy()
            key = query2['key']
            del query2['key']
            data = urlencode(query2)
            data += '&' + 'key=' + key
        else:
            data = urlencode(query)

        LOG.debug(_('query: %s'), query)
        LOG.debug(_('data: %s'), type(data))
        LOG.debug(_('data.encode(): %s'), type(data.encode()))

        url = self.uri
        if self.use_get:
            url += '?' + data
            request = Request(url)
        else:
            # data must by type 'bytes' for 3.x
            request = Request(url, data.encode())

        LOG.debug(_('URL: %s'), url)
        LOG.debug(_('method: %s'), request.get_method())
        LOG.debug(_('data: %s'), data)

        kwargs = {'url': request}
        # Changed in version 3.2: cafile and capath were added.
        if sys.hexversion >= 0x03020000:
            kwargs['cafile'] = self.cafile
            kwargs['capath'] = self.capath

        if self.timeout is not None:
            kwargs['timeout'] = self.timeout

        try:
            response = urlopen(**kwargs)

        # XXX handle httplib.BadStatusLine when http to port 443
        except URLError as error:
            msg = 'URLError:'
            if hasattr(error, 'code'):
                msg += ' code: %s' % error.code
            if hasattr(error, 'reason'):
                msg += ' reason: %s' % error.reason
            if not (hasattr(error, 'code') or hasattr(error, 'reason')):
                msg += ' unknown error (Kevin heart Python)'
            self.status_detail = msg
            return False

        LOG.debug(_('HTTP response headers:'))
        LOG.debug(_('%s'), response.info())

        return response

    def __set_api_key(self):
        if self.api_key is None:
            self.keygen()
            LOG.debug(_('autoset api_key: "%s"'), self.api_key)

    def cmd_xml(self, cmd):
        xml = ''
        args = cmd.split()
        for arg in args:
            result = re.search(r'^"(.*)"$', arg)
            if result:
                xml += result.group(1)
            else:
                xml += '<%s>' % arg
        args.reverse()
        for arg in args:
            if re.search(r'^".*"$', arg) is None:
                xml += '</%s>' % arg

        LOG.debug(_('cmd_xml: "%s"'), xml)

        return xml

    def keygen(self):
        self.__clear_response()

        if (self.api_username is None or
                self.api_password is None):
            raise PanXapiError('api_username and api_password ' +
                               'arguments required')

        query = {'type': 'keygen',
                 'user': self.api_username,
                 'password': self.api_password}
        if self.serial is not None:
            query['target'] = self.serial

        response = self.__api_request(query)
        if not response:
            raise PanXapiError(self.status_detail)

        if not self.__set_response(response):
            raise PanXapiError(self.status_detail)

        if self.element_result is None:
            raise PanXapiError('keygen(): result element not found')
        element = self.element_result.find('key')
        if element is None:
            raise PanXapiError('keygen(): key element not found')

        self.api_key = element.text
        return self.api_key

    def ad_hoc(self, qs=None, xpath=None, modify_qs=False):
        self.__set_api_key()
        self.__clear_response()

        query = {}
        if qs is not None:
            try:
                pairs = qs.split('&')
                for pair in pairs:
                    key, value = pair.split('=', 1)
                    query[key] = value
            except ValueError:
                raise PanXapiError('Invalid ad_hoc query: %s: %s' %
                                   (qs, query))

        if modify_qs:
            if xpath is not None:
                query['xpath'] = xpath
            if self.api_key is not None:
                query['key'] = self.api_key
            if self.api_username is not None:
                query['user'] = self.api_username
            if self.api_password is not None:
                query['password'] = self.api_password
            if self.serial is not None:
                query['target'] = self.serial

        LOG.debug(_('Query: %s'), query)

        response = self.__api_request(query)
        if not response:
            raise PanXapiError(self.status_detail)

        if not self.__set_response(response):
            raise PanXapiError(self.status_detail)

    def show(self, xpath=None):
        query = {}
        if xpath is not None:
            query['xpath'] = xpath
        self.__type_config('show', query)

    def get(self, xpath=None):
        query = {}
        if xpath is not None:
            query['xpath'] = xpath
        self.__type_config('get', query)

    def delete(self, xpath=None):
        query = {}
        if xpath is not None:
            query['xpath'] = xpath
        self.__type_config('delete', query)

    def set(self, xpath=None, element=None):
        query = {}
        if xpath is not None:
            query['xpath'] = xpath
        if element is not None:
            query['element'] = element
        self.__type_config('set', query)

    def edit(self, xpath=None, element=None):
        query = {}
        if xpath is not None:
            query['xpath'] = xpath
        if element is not None:
            query['element'] = element
        self.__type_config('edit', query)

    def move(self, xpath=None, where=None, dst=None):
        query = {}
        if xpath is not None:
            query['xpath'] = xpath
        if where is not None:
            query['where'] = where
        if dst is not None:
            query['dst'] = dst
        self.__type_config('move', query)

    def rename(self, xpath=None, newname=None):
        query = {}
        if xpath is not None:
            query['xpath'] = xpath
        if newname is not None:
            query['newname'] = newname
        self.__type_config('rename', query)

    def clone(self, xpath=None, xpath_from=None, newname=None):
        query = {}
        if xpath is not None:
            query['xpath'] = xpath
        if xpath_from is not None:
            query['from'] = xpath_from
        if newname is not None:
            query['newname'] = newname
        self.__type_config('clone', query)

    def __type_config(self, action, query):
        self.__set_api_key()
        self.__clear_response()

        query['type'] = 'config'
        query['action'] = action
        query['key'] = self.api_key
        if self.serial is not None:
            query['target'] = self.serial

        response = self.__api_request(query)
        if not response:
            raise PanXapiError(self.status_detail)

        if not self.__set_response(response):
            raise PanXapiError(self.status_detail)

    def user_id(self, cmd=None, vsys=None):
        self.__set_api_key()
        self.__clear_response()

        query = {}
        query['type'] = 'user-id'
        query['key'] = self.api_key
        if cmd is not None:
            query['cmd'] = cmd
        if vsys is not None:
            query['vsys'] = vsys
        if self.serial is not None:
            query['target'] = self.serial

        response = self.__api_request(query)
        if not response:
            raise PanXapiError(self.status_detail)

        if not self.__set_response(response):
            raise PanXapiError(self.status_detail)

    def commit(self, cmd=None, action=None, sync=False,
               interval=None, timeout=None):
        self.__set_api_key()
        self.__clear_response()

        if interval is not None:
            try:
                interval = float(interval)
                if interval < 0:
                    raise ValueError
            except ValueError:
                raise PanXapiError('Invalid interval: %s' % interval)
        else:
            interval = _job_query_interval

        if timeout is not None:
            try:
                timeout = int(timeout)
                if timeout < 0:
                    raise ValueError
            except ValueError:
                raise PanXapiError('Invalid timeout: %s' % timeout)

        query = {}
        query['type'] = 'commit'
        query['key'] = self.api_key
        if self.serial is not None:
            query['target'] = self.serial
        if cmd is not None:
            query['cmd'] = cmd
        if action is not None:
            query['action'] = action

        response = self.__api_request(query)
        if not response:
            raise PanXapiError(self.status_detail)

        if not self.__set_response(response):
            raise PanXapiError(self.status_detail)

        if sync is not True:
            return

        job = self.element_root.find('./result/job')
        if job is None:
            return

        LOG.debug(_('commit job: %s'), job.text)

        cmd = 'show jobs id "%s"' % job.text
        start_time = time.time()

        while True:
            try:
                self.op(cmd=cmd, cmd_xml=True)
            except PanXapiError as msg:
                raise PanXapiError('commit %s: %s' % (cmd, msg))

            path = './result/job/status'
            status = self.element_root.find(path)
            if status is None:
                raise PanXapiError('no status element in ' +
                                   "'%s' response" % cmd)
            if status.text == 'FIN':
                # XXX commit vs. commit-all job status
                return

            LOG.debug(_('job %(job)s, status %(status)s'),
                      {'job': job.text,
                       'status': status.text})

            if (timeout is not None and timeout != 0 and
                    time.time() > start_time + timeout):
                raise PanXapiError('timeout waiting for ' +
                                   'job %s completion' % job.text)

            LOG.debug(_('sleep %.2f seconds'), interval)
            time.sleep(interval)

    def op(self, cmd=None, vsys=None, cmd_xml=False):
        if cmd is not None and cmd_xml:
            cmd = self.cmd_xml(cmd)
        self.__type_op(cmd, vsys)

    def __type_op(self, cmd, vsys):
        self.__set_api_key()
        self.__clear_response()

        query = {}
        query['type'] = 'op'
        if cmd is not None:
            query['cmd'] = cmd
        if vsys is not None:
            query['vsys'] = vsys
        query['key'] = self.api_key
        if self.serial is not None:
            query['target'] = self.serial

        response = self.__api_request(query)
        if not response:
            raise PanXapiError(self.status_detail)

        if not self.__set_response(response):
            raise PanXapiError(self.status_detail)

    def export(self, category=None, from_name=None, to_name=None):
        self.__set_api_key()
        self.__clear_response()

        query = {}
        query['type'] = 'export'
        query['key'] = self.api_key
        if category is not None:
            query['category'] = category
        if from_name is not None:
            query['from'] = from_name
        if to_name is not None:
            query['to'] = to_name

        response = self.__api_request(query)
        if not response:
            raise PanXapiError(self.status_detail)

        if not self.__set_response(response):
            raise PanXapiError(self.status_detail)

        if self.export_result:
            self.export_result['category'] = category

    def log(self, log_type=None, nlogs=None, skip=None, filter=None,
            interval=None, timeout=None):
        self.__set_api_key()
        self.__clear_response()

        if interval is None:
            interval = _job_query_interval

        try:
            interval = float(interval)
            if interval < 0:
                raise ValueError
        except ValueError:
            raise PanXapiError('Invalid interval: %s' % interval)

        if timeout is not None:
            try:
                timeout = int(timeout)
                if timeout < 0:
                    raise ValueError
            except ValueError:
                raise PanXapiError('Invalid timeout: %s' % timeout)

        query = {}
        query['type'] = 'log'
        query['key'] = self.api_key
        if log_type is not None:
            query['log-type'] = log_type
        if nlogs is not None:
            query['nlogs'] = nlogs
        if skip is not None:
            query['skip'] = skip
        if filter is not None:
            query['query'] = filter

        response = self.__api_request(query)
        if not response:
            raise PanXapiError(self.status_detail)

        if not self.__set_response(response):
            raise PanXapiError(self.status_detail)

        job = self.element_root.find('./result/job')
        if job is None:
            raise PanXapiError('no job element in type=log response')

        query = {}
        query['type'] = 'log'
        query['action'] = 'get'
        query['key'] = self.api_key
        query['job-id'] = job.text
        LOG.debug(_('log job: %s'), job.text)

        start_time = time.time()

        while True:
            response = self.__api_request(query)
            if not response:
                raise PanXapiError(self.status_detail)

            if not self.__set_response(response):
                raise PanXapiError(self.status_detail)

            status = self.element_root.find('./result/job/status')
            if status is None:
                raise PanXapiError('no status element in ' +
                                   'type=log&action=get response')
            if status.text == 'FIN':
                return

            LOG.debug(_('job %(job)s, status %(status)s'),
                      {'job': job.text,
                       'status': status.text})

            if (timeout is not None and timeout != 0 and
                    time.time() > start_time + timeout):
                raise PanXapiError('timeout waiting for ' +
                                   'job %s completion' % job.text)

            LOG.debug(_('sleep %.2f seconds'), interval)
            time.sleep(interval)
