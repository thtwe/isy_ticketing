# -*- coding: utf-8 -*-

from odoo import models, fields, api, _, SUPERUSER_ID

REQUEST_TYPE = [
        ('clinic', 'Clinic'),
        ('communication', 'Communication')
]

class ISYTicketingAssignPerson(models.Model):
    _name = 'isy.ticketing.assign.person'
    _description = 'Ticketing Assign Person'
    _inherit = ['mail.thread']

    assign_person_id = fields.Many2one('hr.employee', string="Assign Person")
    name = fields.Char(string="Name", related='assign_person_id.name')
    assign_person_email = fields.Char(string="Assign Person Email", related='assign_person_id.work_email')
    assign_person_manager_id = fields.Many2one('hr.employee', string="Assign Person Manager", related='assign_person_id.parent_id')
    assign_person_manager_email = fields.Char(string="Assign Person Manager Email", related='assign_person_manager_id.work_email')
    active = fields.Boolean(string="Active", default=True)
    request_type = fields.Selection(REQUEST_TYPE, string="Request Type")
