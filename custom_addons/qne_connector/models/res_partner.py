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

    qne_customer_id = fields.Char(
        string='QNE Customer ID',
        copy=False,
        index=True,
        help='ID assigned by QNE once this contact has been pushed as a '
             'customer. Left empty until the first successful push.',
    )
    qne_push_status = fields.Selection(
        [('ok', 'Pushed'), ('error', 'Error')],
        string='QNE Push Status',
        copy=False,
        readonly=True,
    )
    qne_push_message = fields.Char(string='QNE Push Message', copy=False, readonly=True)
    qne_last_push_date = fields.Datetime(string='QNE Last Push', copy=False, readonly=True)

    qne_company_code = fields.Char(
        string='QNE Company Code',
        copy=False,
        index=True,
        help='Unique company code coming from QNE. Used to match '
             'records on every sync so re-running the sync updates the '
             'same contact instead of duplicating it.',
    )

    _sql_constraints = [
        (
            'qne_supplier_id_uniq',
            'unique(qne_supplier_id, company_id)',
            'A contact with this QNE Supplier ID already exists for this company.',
        ),
        (
            'qne_customer_id_uniq',
            'unique(qne_customer_id, company_id)',
            'A contact with this QNE Customer ID already exists for this company.',
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
            'qne_supplier_id': record.get('id'),
            'name': record.get('name'),
            'street': record.get('address1'),
            'street2': record.get('address2'),
            'city': '',
            'zip': '',
            'phone': record.get('phoneNo1'),
            'mobile': record.get('phoneNo2'),
            'email': record.get('email'),
            'website': record.get('homepage'),
            'vat': record.get('gstRegNo'),
            'is_company': True,
            'supplier_rank': 1,
        }

    # ---------------------------------------------------------------------
    # Outbound: push Odoo contacts to QNE as suppliers / customers
    # ---------------------------------------------------------------------
    def action_qne_push_supplier(self):
        """Button entry point - push the selected contact(s) to QNE as
        suppliers (creates on first push, updates afterwards)."""
        return self._qne_push_partners(mode='supplier')

    def action_qne_push_customer(self):
        """Button entry point - push the selected contact(s) to QNE as
        customers (creates on first push, updates afterwards)."""
        return self._qne_push_partners(mode='customer')

    def _qne_push_partners(self, mode):
        assert mode in ('supplier', 'customer')
        try:
            client = self._get_qne_client()
        except QNEAPIError as exc:
            raise UserError(str(exc))

        pushed = errored = 0
        error_details = []

        for partner in self:
            try:
                partner._qne_push_one_partner(client, mode)
                pushed += 1
            except QNEAPIError as exc:
                errored += 1
                error_details.append(f"{partner.display_name}: {exc}")
                partner.write({
                    'qne_push_status': 'error',
                    'qne_push_message': str(exc)[:250],
                    'qne_last_push_date': fields.Datetime.now(),
                })
                _logger.exception("Failed to push partner %s to QNE as %s", partner.id, mode)

        message = f"Pushed {pushed}, failed {errored}."
        if error_details:
            message += " Details: " + " | ".join(error_details[:10])

        self.env['qne.sync.log'].sudo().create({
            'state': 'error' if errored and not pushed else 'done',
            'message': f"[Push {mode}] {message}",
            'created_count': pushed,
            'error_count': errored,
        })

        if errored and not pushed:
            raise UserError(message)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': f'QNE {mode.capitalize()} Push',
                'message': message,
                'sticky': False,
                'type': 'success' if not errored else 'warning',
            },
        }

    def _qne_push_one_partner(self, client, mode):
        """Create or update this single partner in QNE as a supplier or
        customer, and store back the QNE ID / push status."""
        self.ensure_one()
        id_field = 'qne_supplier_id' if mode == 'supplier' else 'qne_customer_id'
        payload = (
            self._qne_map_partner_to_supplier_payload()
            if mode == 'supplier'
            else self._qne_map_partner_to_customer_payload()
        )

        existing_id = self[id_field]
	existing_code = self['qne_company_code']
        if existing_id:
            response = (
                client.update_supplier(existing_id, payload)
                if mode == 'supplier'
                else client.update_customer(existing_id, payload)
            )
            new_id = existing_id
            new_code = existing_code
        else:
            response = (
                client.create_supplier(payload)
                if mode == 'supplier'
                else client.create_customer(payload)
            )
            # TODO: adjust to match the actual key QNE returns for the new ID
            new_id = (response or {}).get('id')
            new_code = (response or {}).get('companyCode')


        vals = {
            'qne_push_status': 'ok',
            'qne_push_message': False,
            'qne_last_push_date': fields.Datetime.now(),
        }
        if new_id:
            vals[id_field] = new_id
            vals['qne_company_code'] = new_code
        if mode == 'supplier':
            vals.setdefault('supplier_rank', 1)
        else:
            vals.setdefault('customer_rank', 1)
        self.write(vals)

    def _qne_map_partner_to_supplier_payload(self):
        """Build the JSON payload QNE expects to create/update a supplier.

        TODO: rename these keys to match your QNE API's actual supplier
        schema (check your API doc/Postman collection).
        """
        self.ensure_one()
        return {
            'companyName': self.name,
            'address1': self.street,
            'address2': self.street2,
            'phoneNo1': self.phone,
            'phoneNo2': self.mobile,
            'email': self.email,
            'homepage': self.website,
            'gstRegNo': self.vat,
            'currency': 'RM',
        }

    def _qne_map_partner_to_customer_payload(self):
        """Build the JSON payload QNE expects to create/update a customer.

        TODO: rename these keys to match your QNE API's actual customer
        schema (check your API doc/Postman collection).
        """
        self.ensure_one()
        return {
            'companyName': self.name,
            'address1': self.street,
            'address2': self.street2,
            'phoneNo1': self.phone,
            'phoneNo2': self.mobile,
            'email': self.email,
            'homepage': self.website,
            'gstRegNo': self.vat,
            'currency': 'RM',
        }
