# -*- coding: utf-8 -*-
import logging

from odoo import fields, models
from odoo.exceptions import UserError

from .qne_api_client import QNEAPIError

_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    qne_item_id = fields.Char(
        string='QNE Stock Item ID',
        copy=False,
        index=True,
        help='ID assigned by QNE once this product has been pushed as a '
             'stock item. Left empty until the first successful push.',
    )
    qne_push_status = fields.Selection(
        [('ok', 'Pushed'), ('error', 'Error')],
        string='QNE Push Status',
        copy=False,
        readonly=True,
    )
    qne_push_message = fields.Char(string='QNE Push Message', copy=False, readonly=True)
    qne_last_push_date = fields.Datetime(string='QNE Last Push', copy=False, readonly=True)

    _sql_constraints = [
        (
            'qne_item_id_uniq',
            'unique(qne_item_id)',
            'A product with this QNE Stock Item ID already exists.',
        ),
    ]

    # ---------------------------------------------------------------------
    # Button entry point
    # ---------------------------------------------------------------------
    def action_qne_push_product(self):
        try:
            client = self.env['res.partner']._get_qne_client()
        except QNEAPIError as exc:
            raise UserError(str(exc))

        pushed = errored = 0
        error_details = []

        for product in self:
            try:
                product._qne_push_one_product(client)
                pushed += 1
            except QNEAPIError as exc:
                errored += 1
                error_details.append(f"{product.display_name}: {exc}")
                product.write({
                    'qne_push_status': 'error',
                    'qne_push_message': str(exc)[:250],
                    'qne_last_push_date': fields.Datetime.now(),
                })
                _logger.exception("Failed to push product %s to QNE", product.id)

        message = f"Pushed {pushed}, failed {errored}."
        if error_details:
            message += " Details: " + " | ".join(error_details[:10])

        self.env['qne.sync.log'].sudo().create({
            'state': 'error' if errored and not pushed else 'done',
            'message': f"[Push stock item] {message}",
            'created_count': pushed,
            'error_count': errored,
        })

        if errored and not pushed:
            raise UserError(message)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'QNE Stock Item Push',
                'message': message,
                'sticky': False,
                'type': 'success' if not errored else 'warning',
            },
        }

    # ---------------------------------------------------------------------
    # Core push logic - also called from purchase order / delivery order
    # push flows to auto-create a missing item before the document itself
    # is pushed.
    # ---------------------------------------------------------------------
    def _qne_push_one_product(self, client):
        self.ensure_one()
        payload = self._qne_map_product_to_payload()

        if self.qne_item_id:
            response = client.update_stock_item(self.qne_item_id, payload)
            new_id = self.qne_item_id
        else:
            response = client.create_stock_item(payload)
            # TODO: adjust to match the actual key QNE returns for the new ID
            new_id = (response or {}).get('id')

        vals = {
            'qne_push_status': 'ok',
            'qne_push_message': False,
            'qne_last_push_date': fields.Datetime.now(),
        }
        if new_id:
            vals['qne_item_id'] = new_id
        self.write(vals)

    def _qne_map_product_to_payload(self):
        """Build the JSON payload QNE expects to create/update a stock item.

        TODO: rename these keys to match your QNE API's actual stock item
        schema (check your API doc/Postman collection).
        """
        self.ensure_one()
        return {
            'stockCode': self.default_code or False,
            'stockName': self.name,
            'barCode': self.barcode,
            'baseUOM': self.uom_id.name,
            'category': self.categ_id.name,
            'purchasePrice': self.standard_price,
            'minPrice': self.list_price,
        }
