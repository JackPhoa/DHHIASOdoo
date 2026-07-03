{
    'name': 'QNE Connector',

    'version': '1.0',

    'depends': [
        'base',
        'contacts'
    ],

    'data': [
        'views/settings.xml',
        'data/cron.xml',
        'security/ir.model.access.csv'
    ],

    'installable': True,

    'application': True,
}
