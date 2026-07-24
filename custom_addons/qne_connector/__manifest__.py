# -*- coding: utf-8 -*-
{
    'name': 'QNE Connector - Supplier Sync',
    'version': '19.0.3.0.0',
    'category': 'Connector',
    'summary': 'Two-way sync of suppliers, customers, invoices, purchase orders, deliveries and products between QNE and Odoo',
    'description': """
QNE Connector
=============
Connects to the QNE accounting API to keep suppliers, customers,
invoices, purchase orders, delivery orders and products in sync with Odoo.

Features
--------
Inbound (QNE -> Odoo)
* Pull suppliers from QNE into Odoo Contacts
* Scheduled (cron) automatic pull, or manual "Sync Now"
* Create/update matching based on QNE Supplier ID (idempotent sync)

Outbound (Odoo -> QNE)
* Push a contact to QNE as a supplier ("Push Supplier to QNE" button)
* Push a contact to QNE as a customer ("Push Customer to QNE" button)
* Push a customer invoice / credit note or vendor bill / refund to QNE
  ("Push to QNE" button on the invoice form)
* Push a product to QNE as a stock item ("Push to QNE" button on the
  product form)
* Push a purchase order to QNE ("Push to QNE" button on the PO form)
* Push a delivery order (outgoing transfer) to QNE ("Push to QNE" button
  on the transfer form)
* Any related contact or product that hasn't been pushed yet is pushed
  automatically first, then the document itself is linked to it
* Records are matched/updated using the ID QNE returns on first push, so
  re-pushing updates the same record instead of duplicating it

* Sync/push log kept for troubleshooting (Settings > Technical > QNE Connector)
""",
    'author': 'Your Company',
    'website': 'https://www.example.com',
    'license': 'LGPL-3',
    'depends': ['base', 'contacts', 'mail', 'account', 'product', 'purchase', 'stock'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'views/res_config_settings_views.xml',
        'views/res_partner_views.xml',
        'views/account_move_views.xml',
        'views/product_views.xml',
        'views/purchase_order_views.xml',
        'views/stock_picking_views.xml',
        'views/qne_sync_log_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
