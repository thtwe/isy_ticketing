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

class ISYCommunicationRequestType(models.Model):
    _name = 'isy.communication.request.type'
    _description = 'Communication Request Type'

    name = fields.Char(string="Name")
    active = fields.Boolean(string="Active", default=True)

class ISYCommunicationRequest(models.Model):
    _name = 'isy.communication.request'
    _description = 'Communication Request'
    _inherit = ['mail.thread']

    name = fields.Char(string="Request ID", readonly=True, required=True, copy=False, default='New', index=True)
    subject = fields.Char(string="Subject")
    request_type_id = fields.Many2one('isy.communication.request.type', string="Request Type", required=True)
    event_date = fields.Date(string='Event Date', required=True)
    start_time = fields.Float(string='Start Time', default=0.000, required=True)
    end_time = fields.Float(string='End Time', default=0.000, required=True)
    request_date = fields.Date(string='Request Date', default=fields.Date.today)
    request_person = fields.Many2one('hr.employee', string="Request Person")
    request_person_email = fields.Char(string="Request Person Email", related='request_person.work_email')
    description = fields.Text(string='Description')
    state = fields.Selection([
        ('draft', 'Draft'), 
        ('request_for_approval', 'Waiting for Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled')
        ], string="State", default='draft', tracking=True)

    special_note = fields.Text(string='Note')
    cancellation_reason = fields.Text(string='Cancellation Reason')
    approver_id = fields.Many2one('res.users', string="Appprover", default=lambda self: self._get_default_approver_id(), required=True)
    assign_person_id = fields.Many2one('isy.ticketing.assign.person', string="Assign Person", domain=[('request_type', '=', 'communication')])
    date_from_to_show = fields.Datetime(string='Date From to Show', compute='_compute_date_from_to_show')
    date_to_toshow = fields.Datetime(string='Date To Show', compute='_compute_date_from_to_show')

    def _get_default_approver_id(self):
        return int(self.env['ir.config_parameter'].sudo().get_param('isy.communication_request_approver', 184))

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
            vals['name'] = self.env['ir.sequence'].next_by_code('isy.ticketing.requests.communication') or 'New'
        if not vals.get('request_person'):
            obj_emp = self.env['hr.employee'].search([('user_id', '=', self.env.user.id)])
            vals['request_person'] = obj_emp.id
            vals['request_person_email'] = obj_emp.work_email

        vals['state'] = 'request_for_approval'
        record = super(ISYCommunicationRequest, self).create(vals)
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

    def approve_request(self):
        for rec in self:
            if rec.state == 'request_for_approval':
                if not rec.assign_person_id:
                    raise ValidationError(_("Please assign a person to this request."))

                if rec.env.user.login not in ('odooadmin@isyedu.org', rec.approver_id.login):
                    raise ValidationError(_("You are not authorized to approve this request."))

            rec.state = "approved"

    def request_cancelled(self):
        for rec in self:
            if not rec.cancellation_reason:
                raise ValidationError(_("Please provide a reason for cancellation."))

            if rec.env.user.login not in ('odooadmin@isyedu.org', rec.request_person_email, rec.approver_id.login):
                raise ValidationError(_("You are not authorized to cancel this request."))

            rec.state = "cancelled"

    def reject_request(self):
        for rec in self:
            if rec.env.user.login not in ('odooadmin@isyedu.org', rec.approver_id.login):
                raise ValidationError(_("You are not authorized to reject this request."))
            rec.state = "rejected"

    def done_request(self):
        for rec in self:
            if rec.env.user.login not in ('odooadmin@isyedu.org', rec.assign_person_id.assign_person_email, rec.approver_id.login):
                raise ValidationError(_("You are not authorized to done this request."))
            rec.state = "done"
