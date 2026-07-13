# -*- coding: utf-8 -*-
from odoo import fields, models


class QNESyncLog(models.Model):
    _name = 'qne.sync.log'
    _description = 'QNE Supplier Sync Log'
    _order = 'create_date desc'
    _rec_name = 'create_date'

    state = fields.Selection(
        [('done', 'Done'), ('error', 'Error')],
        string='Status',
        required=True,
        default='done',
    )
    message = fields.Text(string='Summary')
    created_count = fields.Integer(string='Created', default=0)
    updated_count = fields.Integer(string='Updated', default=0)
    error_count = fields.Integer(string='Errors', default=0)
