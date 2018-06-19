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

import sqlalchemy as sa

from neutron.common import exceptions as neutron_exc
from neutron.db import db_base_plugin_v2
from neutron.db import model_base


class PanDeviceReservationNotFound(neutron_exc.NotFound):
    message = _('PAN device reservation for router %(router_id)s could not be'
                ' found')


class PanDeviceReservation(model_base.BASEV2):
    """Represents a PAN device reservation for Neutron router."""
    __tablename__ = 'pan_device_reservations'
    router_id = sa.Column(sa.String(36), nullable=False)
    device_sn = sa.Column(sa.String(16), nullable=False, primary_key=True)


class PanDbApi(db_base_plugin_v2.NeutronDbPluginV2):

    def reserve_pan_device(self, context, device_sn, router_id):
        """Create PAN device reservation DB record.

        @param context: contain user information
        @param device_sn: Panorama device serial number
        @param router_id: Neutron router id
        @return: None
        """
        with context.session.begin(subtransactions=True):
            reservation_ref = PanDeviceReservation(router_id=router_id,
                                                   device_sn=device_sn)
            context.session.add(reservation_ref)

    def release_pan_device(self, context, router_id):
        """Delete PAN device reservation DB record.

        @param context: contain user information
        @param router_id: Neutron router id
        @return: None
        """
        with context.session.begin(subtransactions=True):
            reservation = self._get_reservation_by_router(context, router_id)
            context.session.delete(reservation)

    def get_device_reservation(self, context, router_id):
        """Get PAN device reservation DB record.

        @param context: contain user information
        @param router_id: Neutron router id
        @return: dict with reservation info
        """
        dev_res = self._get_reservation_by_router(context, router_id)
        return self._make_device_reservation_dict(dev_res)

    def get_device_reservations(self, context):
        """Get list of PAN device reservation DB records.

        @param context: contain user information
        @return: list of dict with reservation info
        """
        return self._get_collection(context, PanDeviceReservation,
                                    self._make_device_reservation_dict)

    def _make_device_reservation_dict(self, dev_res, fields=None):
            res = {
                'router_id': dev_res['router_id'],
                'device_sn': dev_res['device_sn'],
            }
            return res

    def _get_reservation_by_router(self, context, router_id):
        reservation = self._model_query(context, PanDeviceReservation).\
            filter_by(router_id=router_id).first()
        if not reservation:
            raise PanDeviceReservationNotFound(router_id=router_id)
        return reservation
