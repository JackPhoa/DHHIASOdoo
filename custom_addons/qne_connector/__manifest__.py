{
    'name': 'QNE Connector',

    'version': '1.0',

    'depends': [
        'base',
        'contacts'
    ],

    'data': [
        'views/res_config_settings_views.xml',
        'views/res_partner_views.xml',
        'views/qne_sync_log_views.xml',
        'data/ir_cron_data.xml',
        'security/ir.model.access.csv'
    ],

    'installable': True,

    'application': False,
}
