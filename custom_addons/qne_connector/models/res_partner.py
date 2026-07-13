# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

from .qne_api_client import QNEAPIClient, QNEAPIError

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    qne_supplier_id = fields.Char(
        string='QNE Supplier ID',
        copy=False,
        index=True,
        help='Unique supplier identifier coming from QNE. Used to match '
             'records on every sync so re-running the sync updates the '
             'same contact instead of duplicating it.',
    )
    qne_last_sync_date = fields.Datetime(string='QNE Last Sync', copy=False, readonly=True)
    qne_sync_status = fields.Selection(
        [('ok', 'Synced'), ('error', 'Error')],
        string='QNE Sync Status',
        copy=False,
        readonly=True,
    )
    qne_sync_message = fields.Char(string='QNE Sync Message', copy=False, readonly=True)

    _sql_constraints = [
        (
            'qne_supplier_id_uniq',
            'unique(qne_supplier_id, company_id)',
            'A contact with this QNE Supplier ID already exists for this company.',
        ),
    ]

    # ---------------------------------------------------------------------
    # Sync entry points
    # ---------------------------------------------------------------------
    @api.model
    def qne_sync_suppliers_cron(self):
        """Entry point for the scheduled action."""
        self._qne_sync_suppliers()

    @api.model
    def qne_sync_suppliers_manual(self):
        """Entry point for the 'Sync Now' button. Raises on hard failure so
        the user gets immediate feedback instead of a silent cron failure."""
        result = self._qne_sync_suppliers()
        if result.get('fatal_error'):
            raise UserError(result['fatal_error'])
        return result

    @api.model
    def _get_qne_client(self):
        icp = self.env['ir.config_parameter'].sudo()
        base_url = icp.get_param('qne_connector.api_base_url')
        api_key = icp.get_param('qne_connector.api_key')
        return QNEAPIClient(base_url=base_url, api_key=api_key)

    # ---------------------------------------------------------------------
    # Core sync logic
    # ---------------------------------------------------------------------
    @api.model
    def _qne_sync_suppliers(self):
        """Pull suppliers from QNE and create/update matching res.partner
        records. Returns a summary dict and writes a qne.sync.log entry."""
        SyncLog = self.env['qne.sync.log'].sudo()
        created = updated = errored = 0
        error_details = []

        try:
            client = self._get_qne_client()
        except QNEAPIError as exc:
            SyncLog.create({
                'state': 'error',
                'message': str(exc),
            })
            return {'fatal_error': str(exc)}

        try:
            for record in client.fetch_suppliers():
                try:
                    vals = self._qne_map_supplier_to_partner_vals(record)
                    if not vals.get('qne_supplier_id'):
                        errored += 1
                        error_details.append('Skipped a record with no supplier ID.')
                        continue

                    partner = self.sudo().search(
                        [('qne_supplier_id', '=', vals['qne_supplier_id'])], limit=1
                    )
                    vals.update({
                        'qne_last_sync_date': fields.Datetime.now(),
                        'qne_sync_status': 'ok',
                        'qne_sync_message': False,
                    })
                    if partner:
                        partner.write(vals)
                        updated += 1
                    else:
                        vals.setdefault('supplier_rank', 1)
                        self.sudo().create(vals)
                        created += 1
                except Exception as exc:  # noqa: BLE001 - keep looping across records
                    errored += 1
                    error_details.append(
                        f"{record.get('SupplierID', record.get('id', '?'))}: {exc}"
                    )
                    _logger.exception("Failed to sync one QNE supplier record")
        except QNEAPIError as exc:
            SyncLog.create({
                'state': 'error',
                'message': str(exc),
                'created_count': created,
                'updated_count': updated,
                'error_count': errored,
            })
            return {'fatal_error': str(exc)}

        message = f"Created {created}, updated {updated}, failed {errored}."
        if error_details:
            message += " Details: " + " | ".join(error_details[:20])

        SyncLog.create({
            'state': 'error' if errored and not (created or updated) else 'done',
            'message': message,
            'created_count': created,
            'updated_count': updated,
            'error_count': errored,
        })

        return {
            'created': created,
            'updated': updated,
            'errored': errored,
            'message': message,
        }

    @api.model
    def _qne_map_supplier_to_partner_vals(self, record):
        """Translate one QNE supplier JSON record into res.partner field
        values.

        TODO: the keys on the left-hand side of `record.get(...)` below are
        placeholders - replace them with the real field names returned by
        your QNE API (check a sample response in your QNE API docs/Postman
        collection and adjust here).
        """
        return {
            'qne_supplier_id': record.get('SupplierID') or record.get('id'),
            'name': record.get('SupplierName') or record.get('name'),
            'street': record.get('Address1') or record.get('address'),
            'street2': record.get('Address2'),
            'city': record.get('City'),
            'zip': record.get('PostCode') or record.get('zip'),
            'phone': record.get('Phone') or record.get('PhoneNo'),
            'mobile': record.get('Mobile'),
            'email': record.get('Email'),
            'website': record.get('Website'),
            'vat': record.get('RegistrationNo') or record.get('TaxNo'),
            'is_company': True,
            'supplier_rank': 1,
        }
