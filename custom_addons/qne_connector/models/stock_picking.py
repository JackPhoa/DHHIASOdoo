# -*- coding: utf-8 -*-
import logging

from odoo import fields, models
from odoo.exceptions import UserError

from .qne_api_client import QNEAPIError

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    qne_delivery_id = fields.Char(
        string='QNE Delivery Order ID',
        copy=False,
        index=True,
        help='ID assigned by QNE once this delivery order has been pushed. '
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
    def action_qne_push_delivery_order(self):
        pushable = self.filtered(lambda p: p.picking_type_code == 'outgoing')
        if not pushable:
            raise UserError('Only outgoing transfers (delivery orders to a '
                             'customer) can be pushed to QNE.')

        try:
            client = self.env['res.partner']._get_qne_client()
        except QNEAPIError as exc:
            raise UserError(str(exc))

        pushed = errored = 0
        error_details = []

        for picking in pushable:
            try:
                picking._qne_push_one_delivery_order(client)
                pushed += 1
            except QNEAPIError as exc:
                errored += 1
                error_details.append(f"{picking.name}: {exc}")
                picking.write({
                    'qne_push_status': 'error',
                    'qne_push_message': str(exc)[:250],
                    'qne_last_push_date': fields.Datetime.now(),
                })
                _logger.exception("Failed to push delivery order %s to QNE", picking.id)

        message = f"Pushed {pushed}, failed {errored}."
        if error_details:
            message += " Details: " + " | ".join(error_details[:10])

        self.env['qne.sync.log'].sudo().create({
            'state': 'error' if errored and not pushed else 'done',
            'message': f"[Push delivery order] {message}",
            'created_count': pushed,
            'error_count': errored,
        })

        if errored and not pushed:
            raise UserError(message)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'QNE Delivery Order Push',
                'message': message,
                'sticky': False,
                'type': 'success' if not errored else 'warning',
            },
        }

    # ---------------------------------------------------------------------
    # Core push logic
    # ---------------------------------------------------------------------
    def _qne_push_one_delivery_order(self, client):
        self.ensure_one()

        # Make sure the customer exists in QNE first.
        if self.partner_id and not self.partner_id.qne_customer_id:
            self.partner_id._qne_push_one_partner(client, 'customer')

        # Make sure every delivered product exists in QNE as a stock item first.
        for move in self.move_ids:
            product_tmpl = move.product_id.product_tmpl_id
            if not product_tmpl.qne_item_id:
                product_tmpl._qne_push_one_product(client)

        payload = self._qne_map_delivery_order_to_payload()

        if self.qne_delivery_id:
            response = client.update_delivery_order(self.qne_delivery_id, payload)
            new_id = self.qne_delivery_id
        else:
            response = client.create_delivery_order(payload)
            # TODO: adjust to match the actual key QNE returns for the new ID
            new_id = (response or {}).get('id')

        vals = {
            'qne_push_status': 'ok',
            'qne_push_message': False,
            'qne_last_push_date': fields.Datetime.now(),
        }
        if new_id:
            vals['qne_delivery_id'] = new_id
        self.write(vals)

    def _qne_map_delivery_order_to_payload(self):
        """Build the JSON payload QNE expects for a delivery order.

        TODO: rename these keys to match your QNE API's actual delivery
        order schema (check your API doc/Postman collection).
        """
        self.ensure_one()
        payload_lines = []
        for move in self.move_ids:
            qty = move.quantity if 'quantity' in move._fields else move.product_uom_qty
            payload_lines.append({
                'stock': move.product_id.default_code or move.product_id.name,
                'description': move.description_picking or move.product_id.name,
                'qty': qty,
                'uom': move.product_uom.name,
            })

        return {
            'doCode': self.name if self.name != '/' else False,
            'doDate': fields.Date.to_string(self.scheduled_date.date()) if self.scheduled_date else False,
            'customer': self.partner_id.qne_company_code if self.partner_id else False,
            'referenceNo': self.origin,
            'Lines': payload_lines,
        }
