# -*- coding: utf-8 -*-
from odoo import models, fields, api, _, SUPERUSER_ID
from odoo.exceptions import UserError, ValidationError
from odoo.tools import email_split
from odoo.tools import html2plaintext
from odoo.addons.mail.models import mail_template
import datetime
import logging
import math
_logger = logging.getLogger(__name__)

class ISYTAudioVisualRequest(models.Model):
    _name = 'isy.audio.request'
    _inherit = ['mail.thread']

    name = fields.Char(string="Request ID", readonly=True, required=True, copy=False, default='New', index=True)
    subject = fields.Char(string="Subject")
    assign_person = fields.Many2one('res.users', string="Assign User", readonly=True)
    request_person = fields.Many2one('hr.employee', string="Request Person")
    request_person_email = fields.Char(string="Request Person Email", related='request_person.work_email')
    state = fields.Selection([('draft', 'Draft'), ('request_for_approval', 'Waiting for Approval'), ('approved', 'Approved'), ('rejected', 'Rejected'), ('done', 'Done'), ('cancelled', 'Cancelled')], string="State", default='draft', tracking=True)
    request_date = fields.Date(string='Request Date', default=fields.Date.today)
    event_date = fields.Date(string='Event Date')
    start_time = fields.Float(string='Start Time', compute="_compute_start_time", inverse="_inverse_start_time", default=0.000)
    end_time = fields.Float(string='End Time', compute="_compute_start_time", inverse="_inverse_start_time", default=0.000)
    mic_qty = fields.Integer(String="Microphone Qty")
    projector_qty = fields.Integer(String="Projector Qty")
    location_id = fields.Many2one('stock.location', string='Resource/Location', domain=[('usage','=','internal'),('location_id','!=',False)])
    special_note = fields.Text(string='Note')
    cancellation_reason = fields.Char(string='Cancellation Reason')
    approver_id = fields.Many2one('res.users', string="Appprover", readonly=True)
    key_type = fields.Selection([('audio', 'Audio / Visual Requests')], default='audio')
    start_time_seconds = fields.Integer(string="Start Time (Seconds)", help="Stored in total seconds")
    end_time_seconds = fields.Integer(string="End Time (Seconds)", help="Stored in total seconds")

    @api.depends('start_time_seconds')
    def _compute_start_time(self):
        """Convert stored total seconds to decimal hours for UI."""
        for record in self:
            record.start_time = record.start_time_seconds / 3600 if record.start_time_seconds else 0.0

    def _inverse_start_time(self):
        """Convert decimal hours to total seconds before saving."""
        for record in self:
            record.start_time_seconds = int(record.start_time * 3600)

    @api.depends('end_time_seconds')
    def _compute_end_time(self):
        """Convert stored total seconds to decimal hours for UI."""
        for record in self:
            record.end_time = record.end_time_seconds / 3600 if record.end_time_seconds else 0.0

    def _inverse_end_time(self):
        """Convert decimal hours to total seconds before saving."""
        for record in self:
            record.end_time_seconds = int(record.end_time * 3600)

    # @api.model
    # def seconds_to_time(self, seconds):
    #     """Convert seconds to HH:MM:SS format."""
    #     hours = int(seconds // 3600)
    #     minutes = int((seconds % 3600) // 60)
    #     seconds = int(seconds % 60)
    #     return '%02d:%02d:%02d' % (hours, minutes, seconds)

    @api.model
    def seconds_to_time(self, time_float):
        """Convert time in float (hours) to HH:MM:SS format."""
        # Convert float hours to total seconds
        total_seconds = int(time_float * 3600)  # Time in seconds
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return '%02d:%02d:%02d' % (hours, minutes, seconds)

    def get_start_time_str(self):
        """Return the start time in HH:MM:SS format."""
        return self.seconds_to_time(self.start_time)

    def get_end_time_str(self):
        """Return the end time in HH:MM:SS format."""
        return self.seconds_to_time(self.end_time)


    def get_emails_list(self, val):
        email_ids = ''
        #only assign person will receive email
        if val == 'alr_approved':
            assign_person_id = self.assign_person
            if not assign_person_id.login == 'odooadmin@isyedu.org':
                    email_ids += str(assign_person_id.login) + ','
            email_ids += str(self.create_uid.partner_id.email)
            return email_ids

        if val == 'alr_cancelled':
            if not self.assign_person.login == 'odooadmin@isyedu.org':
                    email_ids += str(self.assign_person.login) + ','
                    email_ids += str(self.approver_id.login) + ','
            email_ids += str(self.create_uid.partner_id.email)
            return email_ids

    def _get_related_email_template(self, check_key_type, val):
        template = self.env.ref('isy_ticketing.blank_template')
        if val == 'received':
            template = self.env.ref('isy_ticketing.alr_received')
        elif val == 'approved':
            template = self.env.ref('isy_ticketing.alr_approved')
        elif val == 'cancelled':
            template = self.env.ref('isy_ticketing.alr_cancelled')
        elif val == 'reject':
            template = self.env.ref('isy_ticketing.alr_reject')
        elif val == 'done':
            template = self.env.ref('isy_ticketing.alr_done')
        return template


    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('isy.ticketing.requests.audio') or 'New'

        if not vals.get('request_person'):
            obj_emp = self.env['hr.employee'].search([('user_id', '=', self.env.user.id)])
            vals['request_person'] = obj_emp.id
            vals['request_person_email'] = obj_emp.work_email

        vals['state'] = 'request_for_approval'
        record = super(ISYTAudioVisualRequest, self).create(vals)
        template = record._get_related_email_template(record.key_type, 'received')
        if template:
            template.sudo().send_mail(record.id) 
        return record 

    def approve_request(self):
        for rec in self:
            rec.state = "approved"
        template = self._get_related_email_template(self.key_type, 'approved')
        if template:
            template.sudo().send_mail(self.id)
            

    def request_cancelled(self):
        for rec in self:
            rec.state = "cancelled"
        template = self._get_related_email_template(self.key_type, 'cancelled')
        if template:
            template.sudo().send_mail(self.id)

    def reject_request(self):
        for rec in self:
            rec.state = "rejected"
        template = self._get_related_email_template(self.key_type, 'reject')
        if template:
            template.sudo().send_mail(self.id)
          
    def done_request(self):
        for rec in self:
            rec.state = "done"
        template = self._get_related_email_template(self.key_type, 'done')
        if template:
            template.sudo().send_mail(self.id)

    def get_record_url(self):
        url = "https://sas.isyedu.org/web#id=%s&action=1868&model=isy.audio.request&view_type=form&menu_id=764" % (self.id,)
        return url


#class ResUsers(models.Model):
#    _inherit = "res.users"

    #portal_audio_request = fields.Boolean(string='Portal Visual Requestor', copy=True, default=True)
    #portal_audio_request_user = fields.Boolean(string='Portal Visual User', copy=True, default=True)


 