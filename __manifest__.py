# -*- coding: utf-8 -*-
{
    'name': "ISY Ticketing System",

    'summary': """
        Every operations requests can able to request from this ticketing system.
    """,

    'description': """
        1. Maintenance Request
        2. Planning Request
        3. Schedule Request
        4. Technology Request
        5. Transportation Request
    """,

    'author': "ISY Team",
    'website': "https://isyedu.org",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/12.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'ISY Modules',
    'version': '1.0',

    # any module necessary for this one to work correctly
    'depends': ['base', 'mail', 'stock', 'portal', 'fleet', 'purchase', 'email_template_qweb', 'hr'],

    # always loaded
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/views.xml',
        'views/technology_request_view.xml',
        'views/maintenance_portal_template.xml',
        'views/tech_portal_template.xml',
        'views/transportation_portal_template.xml',
        'views/schedule_portal_template.xml',
        'views/stationary_request_portal_template.xml',
        'views/audio_visual_request_view.xml',
        'views/audio_portal_template.xml',
        'data/ir_sequence_data.xml',
        'wizard/isy_ticketing_resolve_view.xml',
        'data/ir_ui_view.xml',
        'data/mail_template_data.xml',
        'data/ir_cron.xml',
    ],
    # only loaded in demonstration mode
    'demo': [

        'demo/demo.xml',
    ],
}
