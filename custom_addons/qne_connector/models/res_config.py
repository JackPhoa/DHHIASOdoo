from odoo import models, fields

class ResConfigSettings(models.TransientModel):

    _inherit = 'res.config.settings'

    qne_url = fields.Char()

    qne_db_code = fields.Char()


def set_values(self):

    super().set_values()

    self.env['ir.config_parameter'].sudo().set_param(
        'qne.url',
        self.qne_url
    )

    self.env['ir.config_parameter'].sudo().set_param(
        'qne.db_code',
        self.qne_api_key
    )

def get_values(self):

    res = super().get_values()

    ICP = self.env['ir.config_parameter'].sudo()

    res.update(

        qne_url=ICP.get_param('qne.url'),

        qne_api_key=ICP.get_param('qne.db_code')

    )

    return res
