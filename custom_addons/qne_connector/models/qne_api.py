import requests

from odoo import models

class QNEApi(models.AbstractModel):

    _name = "qne.api"

    def get_supplier(self):

        ICP = self.env['ir.config_parameter'].sudo()

        url = ICP.get_param('qne.url')

        api = ICP.get_param('qne.db_code')

        response = requests.get(

            url + "/api/suppliers",

            headers={

                "DbCode": f"{api}"

            }

        )

        return response.json()
