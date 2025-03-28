# -*- coding: utf-8 -*-
from odoo import models, fields, api, _, SUPERUSER_ID
from odoo.exceptions import UserError, ValidationError
from odoo.tools import email_split
from odoo.tools import html2plaintext
from odoo.addons.mail.models import mail_template
import datetime
import logging
_logger = logging.getLogger(__name__)


class ISYTechnologyRequest(models.Model):
    _name = 'isy.technology.request'
    _inherit = ['mail.thread']

    name = fields.Char(string="Request ID", readonly=True, required=True, copy=False, default='New')
    subject = fields.Char(string="Subject")
    body = fields.Html(string="Description")
    assign_person = fields.Many2one("hr.employee", string="Assign Person")
    assign_date = fields.Date(string="Assign Date", readonly="1", store=True, compute="_get_assign_date")
    state = fields.Selection([('draft', 'Draft'), ('request_for_approval', 'Waiting for Approval'), ('approved', 'Approved'), ('rejected', 'Rejected'), ('progress', 'Pending Resolution'), ('done', 'Done'), ('cancelled', 'Cancelled')], string="State", default='request_for_approval')
    resolved_date = fields.Date(string="Resolved Date")
    request_person_email = fields.Char(string="Request Person Email", related='request_person.work_email')
    request_person = fields.Many2one('hr.employee', string="Request Person")
    resolution_description = fields.Text(string="Resolution Description")
    key_type = fields.Selection([('technology', 'Technology Requests')], default='technology')
    from_email = fields.Boolean(string="Email Tickets (?)", default=False)
    special_note = fields.Char(string="Note")
    next_reminder = fields.Date(string="Last Reminder")
    parent_id = fields.Many2one('isy.ticketing.requests', string="Ref Request#")
    location_id = fields.Many2one('stock.location', string='Resource/Location', domain=[('usage','=','internal'),('location_id','!=',False)])



    def _technology_request_reminder(self):
        _logger.info("==================Reminder Checking For Technologpy Request Started!========================")
        from pytz import timezone
        now_utc = datetime.datetime.now(timezone('UTC'))
        now_myanmar = now_utc.astimezone(timezone('Asia/Yangon'))
        office_start = now_myanmar.replace(hour=7, minute=30, second=0, microsecond=0)
        office_end = now_myanmar.replace(hour=16, minute=00, second=0, microsecond=0)

        if now_myanmar >= office_start and now_myanmar <= office_end and now_myanmar.date().strftime("%A") not in ['Saturday', 'Sunday']:
            obj_reminders = self.search([('state', '=', 'draft')])
            for obj_reminder in obj_reminders:
                if obj_reminder.create_date == obj_reminder.write_date:
                    diff = fields.datetime.now() - obj_reminder.create_date
                    seconds_in_day = 24 * 60 * 60
                    diff_seconds = diff.days * seconds_in_day + diff.seconds
                    diff_hours = diff_seconds / 3600

                    if diff_hours > 1:
                        if obj_reminder.next_reminder and obj_reminder.next_reminder == fields.datetime.now().date():
                            _logger.info("==================SendReminderAction(No action within a day after reminder)========================")
                            _logger.info("==================SendReminder========================")
                            template = self._get_related_email_template('technology', 'reminder')
                            self.env['mail.template'].browse(template.id).sudo().send_mail(obj_reminder.id)
                            #update next reminder
                            #obj_reminder.next_reminder = fields.datetime.now().date() + datetime.timedelta(1)
                            self.env.cr.execute("""update isy_technology_request set next_reminder='""" + str(fields.datetime.now().date() + datetime.timedelta(1)) + """' where id=""" + str(obj_reminder.id))
                        elif not obj_reminder.next_reminder:
                            _logger.info("==================SendReminderAction(No action within 1 hour)========================")
                            template = self._get_related_email_template('technology', 'reminder')
                            self.env['mail.template'].browse(template.id).sudo().send_mail(obj_reminder.id)
                            #update next reminder
                            self.env.cr.execute("""update isy_technology_request set next_reminder='""" + str(fields.datetime.now().date() + datetime.timedelta(1)) + """' where id=""" + str(obj_reminder.id))

                            #obj_reminder.next_reminder = fields.datetime.now().date() + datetime.timedelta(1)
                else:
                    #update blank at next reminder.
                    _logger.info("==================No more reminder for ticket========================")
                    self.env.cr.execute("""update isy_technology_request set next_reminder=Null where id=""" + str(obj_reminder.id))
            self.env.cr.commit()

        # converted_content = mail_template.mako_template_env.from_string(self.body).render({'object': self,})
        # return converted_content
        # if not self.from_email:
        #     return html2plaintext(self.body)
        # else:
        #     return self.body

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('isy.ticketing.requests.technology') or 'New'
        if not vals.get('request_person'):
            obj_emp = self.env['hr.employee'].search([('user_id', '=', self.env.user.id)])
            vals['request_person'] = obj_emp.id
            vals['request_person_email'] = obj_emp.work_email
        if vals.get('assign_person'):
            if self.env.user.has_group('base.group_portal') and not self.env.user.portal_technology_request_user:
                raise UserError("You don't have access to add assign person! Please contact OdooAdmin.")
        result = super(ISYTechnologyRequest, self).create(vals)
        self.sudo().add_follower(result)
        template = self._get_related_email_template(result.key_type, 'received')
        #mail_values = template.sudo().generate_email(self.env.user.id)
        #template.body_html = mail_values['body_html']
        self.env['mail.template'].browse(template.id).sudo().send_mail(result.id)

        return result

    def write(self, vals):
        if vals.get('assign_person'):
            if self.env.user.has_group('base.group_portal') and not self.env.user.portal_technology_request_user:
                raise UserError("You don't have access to add assign person! Please contact OdooAdmin.")
        result = super(ISYTechnologyRequest, self).write(vals)
        return result

    def add_follower(self, record):
        res_list = []
        channel_id = self.env['discuss.channel'].search([('key_type', '=', record.key_type)])
        if channel_id:
            for cmi in channel_id.channel_partner_ids:
                if not self.env['mail.followers'].search([('res_id', '=', record.id), ('res_model', '=', 'isy.technology.request'), ('partner_id', '=', cmi.id)]):
                    reg = {
                        'res_id': record.id,
                        'res_model': 'isy.technology.request',
                        'partner_id': cmi.id,
                    }
                    res_list.append(reg)
        if record.parent_id:
            res_list.append({
                'res_id': record.id,
                'res_model': 'isy.technology.request',
                'partner_id': record.parent_id.create_uid.partner_id.id,
            })
        if record.message_partner_ids:
            index = 0
            while index < len(res_list):
                if res_list[index].get('partner_id') in record.message_partner_ids.ids:
                    del res_list[index]
                    index += 1
                else:
                    index += 1
        if res_list:
            unique_sets = set(frozenset(d.items()) for d in res_list)
            unique_dicts = [dict(s) for s in unique_sets]
            follower_ids = self.env['mail.followers'].sudo().create(unique_dicts)

    def _get_related_email_template(self, check_key_type, val):
        template = self.env.ref('isy_ticketing.blank_template')
        if val == 'received':
            template = self.env.ref('isy_ticketing.new_tyr_received')
        elif val == 'approved':
            template = self.env.ref('isy_ticketing.new_tyr_received_approved')
        elif val == 'done':
            template = self.env.ref('isy_ticketing.new_tyr_received_approved_resolved')
        elif val == 'progress':
            template = self.env.ref('isy_ticketing.new_tyr_progress')
        elif val == 'rejected':
            template = self.env.ref('isy_ticketing.new_tyr_rejected')
        elif val == 'reminder':
            template = self.env.ref('isy_ticketing.new_tyr_reminder')
        return template

    def get_record_url(self):
        url = "https://sas.isyedu.org/web#id=%s&action=1230&model=isy.technology.request&view_type=form&menu_id=764" % (self.id,)
        return url

    def get_emails_list(self):
        email_ids = ''
        for partner in self.message_partner_ids:
            email_ids += str(partner.email) + ','
        email_ids += str(self.request_person_email)
        return email_ids

    @api.model
    def message_new(self, msg_dict, custom_values=None):
        if custom_values is None:
            custom_values = {}
        #name
        msg_subject = msg_dict.get('subject', '')
        #body
        msg_body = msg_dict.get('body', '')
        #request_person_email
        email_address = email_split(msg_dict.get('email_from', False))[0]
        employee_id = self.env['hr.employee'].search([('work_email', '=', email_address)])

        custom_values.update({
            'name': 'New',
            'subject': msg_subject,
            'body': msg_body,
            'request_person_email': email_address,
            'request_person': employee_id and employee_id.id or False,
            'from_email': True
        })
        return super(ISYTechnologyRequest, self).message_new(msg_dict, custom_values)

    def reopen_request(self):
        for rec in self:
            template = self._get_related_email_template(rec.key_type, 'received')
            #mail_values = template.generate_email(self.env.user.id)
            #template.body_html = mail_values['body_html']
            self.env['mail.template'].browse(template.id).sudo().send_mail(rec.id)
            rec.state = 'draft'

    def request_for_approval(self):
        for rec in self:
            rec.state = "request_for_approval"

    def request_cancelled(self):
        for rec in self:
            rec.state = "cancelled"

    def approve_request(self):
        for rec in self:
            rec.state = "approved"
            template = rec._get_related_email_template(rec.key_type, 'approved')
            #mail_values = template.generate_email(self.env.user.id)
            #import pdb;pdb.set_trace();
            #template.body_html = mail_values['body_html']
            rec.env['mail.template'].browse(template.id).send_mail(rec.id)

    def reject_request(self):
        for rec in self:
            rec.state = "rejected"
            template = rec._get_related_email_template(rec.key_type, 'rejected')
            rec.env['mail.template'].browse(template.id).send_mail(rec.id)

    def done_request(self):
        for rec in self:
            if not self.env.user.has_group('isy_ticketing.group_tyr_user'):
                if not self.env.user.has_group('isy_ticketing.group_tyr_manager'):
                    if not self.env.user.portal_technology_request_user:
                        raise UserError("You don't have access to do this! Please contact odooadmin.")

            if not rec.resolution_description:
                raise UserError('Please fill resolution description')

            rec.resolved_date = fields.Datetime.now().date()
            rec.state = "done"
            template = rec._get_related_email_template(rec.key_type, 'done')
            rec.env['mail.template'].browse(template.id).send_mail(rec.id)

    def progress_request(self):
        for rec in self:
            if not self.env.user.has_group('isy_ticketing.group_tyr_user'):
                if not self.env.user.has_group('isy_ticketing.group_tyr_manager'):
                    if not self.env.user.portal_technology_request_user:
                        raise UserError("You don't have access to do this! Please contact OdooAdmin.")
            if not rec.assign_person:
                rec.assign_person = self.env['hr.employee'].search([('user_id', '=', self.env.user.id)])[0].id
            rec.state = "progress"
            template = rec._get_related_email_template(rec.key_type, 'progress')
            rec.env['mail.template'].browse(template.id).send_mail(rec.id)

    @api.depends("assign_person")
    def _get_assign_date(self):
        if self.assign_person:
            self.assign_date = fields.Datetime.now().date()
        else:
            self.assign_date = False
