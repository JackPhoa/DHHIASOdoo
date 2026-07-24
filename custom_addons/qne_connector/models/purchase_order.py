# -*- coding: utf-8 -*-
import logging

from odoo import fields, models
from odoo.exceptions import UserError

from .qne_api_client import QNEAPIError

_logger = logging.getLogger(__name__)


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    qne_po_id = fields.Char(
        string='QNE Purchase Order ID',
        copy=False,
        index=True,
        help='ID assigned by QNE once this purchase order has been pushed. '
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
    def action_qne_push_purchase_order(self):
        try:
            client = self.env['res.partner']._get_qne_client()
        except QNEAPIError as exc:
            raise UserError(str(exc))

        pushed = errored = 0
        error_details = []

        for order in self:
            try:
                order._qne_push_one_purchase_order(client)
                pushed += 1
            except QNEAPIError as exc:
                errored += 1
                error_details.append(f"{order.name}: {exc}")
                order.write({
                    'qne_push_status': 'error',
                    'qne_push_message': str(exc)[:250],
                    'qne_last_push_date': fields.Datetime.now(),
                })
                _logger.exception("Failed to push purchase order %s to QNE", order.id)

        message = f"Pushed {pushed}, failed {errored}."
        if error_details:
            message += " Details: " + " | ".join(error_details[:10])

        self.env['qne.sync.log'].sudo().create({
            'state': 'error' if errored and not pushed else 'done',
            'message': f"[Push purchase order] {message}",
            'created_count': pushed,
            'error_count': errored,
        })

        if errored and not pushed:
            raise UserError(message)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'QNE Purchase Order Push',
                'message': message,
                'sticky': False,
                'type': 'success' if not errored else 'warning',
            },
        }

    # ---------------------------------------------------------------------
    # Core push logic
    # ---------------------------------------------------------------------
    def _qne_push_one_purchase_order(self, client):
        self.ensure_one()

        # Make sure the vendor exists in QNE first.
        if not self.partner_id.qne_supplier_id:
            self.partner_id._qne_push_one_partner(client, 'supplier')

        # Make sure every ordered product exists in QNE as a stock item first.
        for line in self.order_line:
            product_tmpl = line.product_id.product_tmpl_id
            if not product_tmpl.qne_item_id:
                product_tmpl._qne_push_one_product(client)

        payload = self._qne_map_purchase_order_to_payload()

        if self.qne_po_id:
            response = client.update_purchase_order(self.qne_po_id, payload)
            new_id = self.qne_po_id
        else:
            response = client.create_purchase_order(payload)
            # TODO: adjust to match the actual key QNE returns for the new ID
            new_id = (response or {}).get('id')

        vals = {
            'qne_push_status': 'ok',
            'qne_push_message': False,
            'qne_last_push_date': fields.Datetime.now(),
        }
        if new_id:
            vals['qne_po_id'] = new_id
        self.write(vals)

    def _qne_map_purchase_order_to_payload(self):
        """Build the JSON payload QNE expects for a purchase order.

        TODO: rename these keys to match your QNE API's actual purchase
        order schema (check your API doc/Postman collection).
        """
        self.ensure_one()
        payload_lines = []
        for line in self.order_line:
            payload_lines.append({
                'stock': line.product_id.default_code,
                'description': line.name,
                'qty': line.product_qty,
                'uom': line.product_uom_id,
                'unitPrice': line.price_unit,
            })

        return {
            'purchaseOrderCode': self.name if self.name != '/' else False,
            'purchaseOrderDate': fields.Date.to_string(self.date_order.date()) if self.date_order else False,
            'supplier': self.partner_id.qne_company_code,
            'supplierName': self.partner_id.name,
            'referenceNo': self.partner_ref,
            'requireDate': fields.Date.to_string(self.date_planned.date()) if self.date_planned else False,
            'details': payload_lines,
        }
