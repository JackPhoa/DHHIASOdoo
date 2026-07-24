# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

from .qne_api_client import QNEAPIError

_logger = logging.getLogger(__name__)

# Odoo move types that represent a "sales" document in QNE terms.
SALE_MOVE_TYPES = ('out_invoice', 'out_refund')
# Odoo move types that represent a "purchase" document in QNE terms.
PURCHASE_MOVE_TYPES = ('in_invoice', 'in_refund')


class AccountMove(models.Model):
    _inherit = 'account.move'

    qne_invoice_id = fields.Char(
        string='QNE Invoice ID',
        copy=False,
        index=True,
        help='ID assigned by QNE once this invoice/bill has been pushed. '
             'Left empty until the first successful push.',
    )
    qne_push_status = fields.Selection(
        [('ok', 'Pushed'), ('error', 'Error')],
        string='QNE Push Status',
        copy=False,
        readonly=True,
    )
    qne_push_message = fields.Char(string='QNE Push Message', copy=False, readonly=True)
    qne_last_push_date = fields.Datetime(string='QNE Last Push', copy=False, readonly=True)

    # ---------------------------------------------------------------------
    # Button entry point
    # ---------------------------------------------------------------------
    def action_qne_push_invoice(self):
        pushable = self.filtered(
            lambda m: m.move_type in SALE_MOVE_TYPES + PURCHASE_MOVE_TYPES
        )
        if not pushable:
            raise UserError('Only customer invoices/credit notes or vendor '
                             'bills/refunds can be pushed to QNE.')

        try:
            client = self.env['res.partner']._get_qne_client()
        except QNEAPIError as exc:
            raise UserError(str(exc))

        pushed = errored = 0
        error_details = []

        for move in pushable:
            try:
                move._qne_push_one_invoice(client)
                pushed += 1
            except QNEAPIError as exc:
                errored += 1
                error_details.append(f"{move.name or move.id}: {exc}")
                move.write({
                    'qne_push_status': 'error',
                    'qne_push_message': str(exc)[:250],
                    'qne_last_push_date': fields.Datetime.now(),
                })
                _logger.exception("Failed to push invoice %s to QNE", move.id)

        message = f"Pushed {pushed}, failed {errored}."
        if error_details:
            message += " Details: " + " | ".join(error_details[:10])

        self.env['qne.sync.log'].sudo().create({
            'state': 'error' if errored and not pushed else 'done',
            'message': f"[Push invoice] {message}",
            'created_count': pushed,
            'error_count': errored,
        })

        if errored and not pushed:
            raise UserError(message)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'QNE Invoice Push',
                'message': message,
                'sticky': False,
                'type': 'success' if not errored else 'warning',
            },
        }

    # ---------------------------------------------------------------------
    # Core push logic
    # ---------------------------------------------------------------------
    def _qne_push_one_invoice(self, client):
        self.ensure_one()
        is_sale = self.move_type in SALE_MOVE_TYPES

        # Make sure the related contact exists in QNE first - the invoice
        # payload needs a QNE customer/supplier ID to link to.
        partner_id_field = 'qne_customer_id' if is_sale else 'qne_supplier_id'
        if not self.partner_id[partner_id_field]:
            partner_mode = 'customer' if is_sale else 'supplier'
            self.partner_id._qne_push_one_partner(client, partner_mode)

        payload = self._qne_map_invoice_to_payload()

        if self.qne_invoice_id:
            response = (
                client.update_sales_invoice(self.qne_invoice_id, payload)
                if is_sale
                else client.update_purchase_invoice(self.qne_invoice_id, payload)
            )
            new_id = self.qne_invoice_id
        else:
            response = (
                client.create_sales_invoice(payload)
                if is_sale
                else client.create_purchase_invoice(payload)
            )
            # TODO: adjust to match the actual key QNE returns for the new ID
            new_id = (response or {}).get('id')

        vals = {
            'qne_push_status': 'ok',
            'qne_push_message': False,
            'qne_last_push_date': fields.Datetime.now(),
        }
        if new_id:
            vals['qne_invoice_id'] = new_id
        self.write(vals)

    def _qne_map_invoice_to_payload(self):
        """Build the JSON payload QNE expects for a sales invoice / purchase
        bill, including line items.

        TODO: rename these keys to match your QNE API's actual invoice
        schema (check your API doc/Postman collection) - in particular
        QNE typically expects an internal Item Code per line rather than a
        free-text description, so you'll likely need to map
        `line.product_id` to a QNE item code (e.g. via product_id.default_code
        or a dedicated mapping field).
        """
        self.ensure_one()
        is_sale = self.move_type in SALE_MOVE_TYPES
        party_id_field = 'qne_customer_id' if is_sale else 'qne_supplier_id'

        lines = self.invoice_line_ids.filtered(lambda l: not l.display_type)
        payload_lines = []
        for line in lines:
            payload_lines.append({
                'ItemCode': line.product_id.default_code or line.product_id.name,
                'Description': line.name,
                'Quantity': line.quantity,
                'UnitPrice': line.price_unit,
                'DiscountPercent': line.discount,
                'Amount': line.price_subtotal,
            })

        return {
            'invoiceCode': self.name if self.name != '/' else False,
            'invoiceDate': fields.Date.to_string(self.invoice_date) if self.invoice_date else False,
            ('customer' if is_sale else 'supplier'): self.partner_id['qne_company_code'],
            'referenceNo': self.ref,
            'details': payload_lines,
        }
