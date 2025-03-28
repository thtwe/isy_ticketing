from odoo import models, fields, api, _, SUPERUSER_ID
from odoo.exceptions import UserError, ValidationError
from odoo.tools import email_split
from odoo.tools import html2plaintext
from odoo.addons.mail.models import mail_template
import datetime
import logging
import math
_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = "res.users"

    portal_maintenance_request = fields.Boolean(string='Portal Maintenance Requestor', copy=True, default=False)
    portal_technology_request = fields.Boolean(string='Portal Technology Requestor', copy=True, default=False)
    portal_transportation_request = fields.Boolean(string='Portal Transportation Requestor', copy=True, default=False)
    portal_schedule_request = fields.Boolean(string="Portal Schedule Requestor", copy=True, default=False)

    portal_maintenance_request_user = fields.Boolean(string='Portal Maintenance User', copy=True, default=False)
    portal_technology_request_user = fields.Boolean(string='Portal Technology User', copy=True, default=False)
    portal_transportation_request_user = fields.Boolean(string='Portal Transportation User', copy=True, default=False)
    portal_transportation_request_driver = fields.Boolean(string='Portal Transportation Driver', copy=True, default=False)
    portal_schedule_request_user = fields.Boolean(string="Portal Schedule User", copy=True, default=False)

    check_availability = fields.Boolean(default=True, copy=False)
    reserved_time = fields.One2many('driver.allocation', 'user', String='Allocation Times', readonly=1,
                                                                    ondelete='cascade')