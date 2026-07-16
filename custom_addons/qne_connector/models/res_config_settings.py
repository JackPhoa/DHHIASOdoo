# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    qne_api_base_url = fields.Char(
        string='QNE API Base URL',
        config_parameter='qne_connector.api_base_url',
        help='e.g. https://your-tenant-api.qne.cloud',
    )
    qne_api_key = fields.Char(
        string='QNE API Key',
        config_parameter='qne_connector.api_key',
    )

    def action_qne_save_config(self):
        """Persist just the QNE API Base URL / API Key without running a
        sync, and confirm to the user that it was saved."""
        self.ensure_one()
        self.execute()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'QNE Connector',
                'message': 'Configuration saved.',
                'sticky': False,
                'type': 'success',
            },
        }    

    def action_qne_sync_now(self):
        self.ensure_one()
        # Persist any unsaved changes to the API URL/key before syncing.
        self.execute()
        result = self.env['res.partner'].qne_sync_suppliers_manual()
        message = result.get('message', 'Sync completed.')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'QNE Supplier Sync',
                'message': message,
                'sticky': False,
                'type': 'success' if not result.get('errored') else 'warning',
            },
        }
