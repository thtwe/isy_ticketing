# -*- coding: utf-8 -*-
from odoo import models, fields, api, _, SUPERUSER_ID
from odoo.exceptions import UserError, ValidationError
from odoo.tools import email_split
from odoo.tools import html2plaintext
from odoo.addons.mail.models import mail_template
from datetime import datetime, timedelta
import logging
import math
_logger = logging.getLogger(__name__)

class ISYClinicAssignPerson(models.Model):
    _name = 'isy.clinic.assign.person'
    _description = 'Clinic Assign Person'
    _inherit = ['mail.thread']

    assign_person_id = fields.Many2one('hr.employee', string="Assign Person")
    name = fields.Char(string="Name", related='assign_person_id.name')
    assign_person_email = fields.Char(string="Assign Person Email", related='assign_person_id.work_email')
    assign_person_manager_id = fields.Many2one('hr.employee', string="Assign Person Manager", related='assign_person_id.parent_id')
    assign_person_manager_email = fields.Char(string="Assign Person Manager Email", related='assign_person_manager_id.work_email')
    active = fields.Boolean(string="Active", default=True)

class ISYClinicRequest(models.Model):
    _name = 'isy.clinic.request'
    _description = 'Clinic Request'
    _inherit = ['mail.thread']

    name = fields.Char(string="Request ID", readonly=True, required=True, copy=False, default='New', index=True)
    subject = fields.Char(string="Subject")
    assign_person_id = fields.Many2one('isy.clinic.assign.person', string="Assign Person", required=True)
    request_person = fields.Many2one('hr.employee', string="Request Person")
    request_person_email = fields.Char(string="Request Person Email", related='request_person.work_email')
    state = fields.Selection([
        ('draft', 'Draft'), 
        ('request_for_confirmation', 'Waiting for Confirmation'), 
        ('request_for_approval', 'Waiting for Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled')
        ], string="State", default='draft', tracking=True)
    request_date = fields.Date(string='Request Date', default=fields.Date.today)
    event_date = fields.Date(string='Event Date')
    start_time = fields.Float(string='Start Time', default=0.000)
    end_time = fields.Float(string='End Time', default=0.000)
    location_id = fields.Many2one('stock.location', string='Resource/Location', domain=[('usage','=','internal'),('location_id','!=',False)])
    special_note = fields.Text(string='Note')
    cancellation_reason = fields.Text(string='Cancellation Reason')
    first_approver_id = fields.Many2one('hr.employee', string="First Approver", readonly=True)
    second_approver_id = fields.Many2one('hr.employee', string="Second Approver", related='assign_person_id.assign_person_manager_id')
    date_from_to_show = fields.Datetime(string='Date From to Show', compute='_compute_date_from_to_show')
    date_to_toshow = fields.Datetime(string='Date To Show', compute='_compute_date_from_to_show')
    display_name = fields.Char(string='Display Name', compute='_compute_display_name')

    @api.depends('name', 'state')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"{rec.name} - {' '.join(rec.state.split('_')).capitalize()}"

    @api.depends('event_date', 'start_time', 'end_time')
    def _compute_date_from_to_show(self):
        for rec in self:
            if rec.event_date and rec.start_time and rec.end_time:
                start_hour, start_minute = self.float_time_to_hours_minutes(rec.start_time)
                end_hour, end_minute = self.float_time_to_hours_minutes(rec.end_time)
                # Combine with event_date to create datetime object
                start_dt = datetime.combine(rec.event_date, datetime.min.time()) + timedelta(hours=start_hour, minutes=start_minute)
                end_dt = datetime.combine(rec.event_date, datetime.min.time()) + timedelta(hours=end_hour, minutes=end_minute)

                # Subtract 6 hours 30 minutes
                rec.date_from_to_show = start_dt - timedelta(hours=6, minutes=30)
                rec.date_to_toshow = end_dt - timedelta(hours=6, minutes=30)
            else:
                rec.date_from_to_show = False
                rec.date_to_toshow = False

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('isy.ticketing.requests.clinic') or 'New'

        if not vals.get('request_person'):
            obj_emp = self.env['hr.employee'].search([('user_id', '=', self.env.user.id)])
            vals['request_person'] = obj_emp.id
            vals['request_person_email'] = obj_emp.work_email
            vals['first_approver_id'] = obj_emp.parent_id.id

        vals['state'] = 'request_for_confirmation'
        record = super(ISYClinicRequest, self).create(vals)
        return record 

    def float_time_to_hours_minutes(self, float_time):
        hours = int(float_time)
        minutes = round((float_time - hours) * 60)
        return hours, minutes

    def get_start_time_str(self):
        start_hour, start_minute = self.float_time_to_hours_minutes(self.start_time)
        return f"{start_hour:02d}:{start_minute:02d}"

    def get_end_time_str(self):
        end_hour, end_minute = self.float_time_to_hours_minutes(self.end_time)
        return f"{end_hour:02d}:{end_minute:02d}"

    def confirm_request(self):
        for rec in self:
            if rec.state == 'request_for_confirmation':
                if rec.env.user.login not in ('odooadmin@isyedu.org', rec.first_approver_id.work_email):
                    raise ValidationError(_("You are not authorized to approve this request."))
            rec.state = "request_for_approval"

    def approve_request(self):
        for rec in self:
            if rec.state == 'request_for_approval':
                if rec.env.user.login not in ('odooadmin@isyedu.org', rec.second_approver_id.work_email):
                    raise ValidationError(_("You are not authorized to approve this request."))
            rec.state = "approved"

    def request_cancelled(self):
        for rec in self:
            if rec.env.user.login not in ('odooadmin@isyedu.org', rec.request_person_email, rec.first_approver_id.work_email, rec.second_approver_id.work_email):
                raise ValidationError(_("You are not authorized to cancel this request."))
            rec.state = "cancelled"

    def reject_request(self):
        for rec in self:
            if rec.env.user.login not in ('odooadmin@isyedu.org', rec.first_approver_id.work_email, rec.second_approver_id.work_email):
                raise ValidationError(_("You are not authorized to reject this request."))
            rec.state = "rejected"

    def done_request(self):
        for rec in self:
            if rec.env.user.login not in ('odooadmin@isyedu.org', rec.assign_person_id.assign_person_email, rec.second_approver_id.work_email):
                raise ValidationError(_("You are not authorized to done this request."))
            rec.state = "done"

    def get_record_url(self):
        url = "https://sas.isyedu.org/web#id=%s&action=1868&model=isy.clinic.request&view_type=form&menu_id=764" % (self.id,)
        return url
