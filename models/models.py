# -*- coding: utf-8 -*-
import requests

from odoo import models, fields, api, _, SUPERUSER_ID
from odoo.exceptions import UserError, ValidationError
from datetime import datetime
import dateutil.parser
from odoo.osv import expression
from datetime import timedelta, date
import datetime
import calendar
from lxml import etree
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT,DEFAULT_SERVER_DATETIME_FORMAT

import logging
_logger = logging.getLogger(__name__)

KEY_SELECTION_TYPE = [
        ('maintenance', 'Facility Requests'),
        ('planning', 'Planning Requests'),
        ('schedule', 'Schedule Requests'),
        ('technology', 'Technology Requests'),
        ('transportation', 'Transportation Requests'),
        ('audio', 'Audio Requests')
]

STATES = [
        ('draft', 'Draft'),
        ('waitingfordriverassign','Waiting for Driver Assign'),
        ('waitingconfirmation', 'Waiting Confirmation'),
        ('waitingforapproval', 'Waiting For Approval'),
        # This state become after add user_ids
        ('pendingresolution', 'Pending Resolution'),
        ('resolved', 'Resolved'),
        ('final_upcoming', 'Finalized & Upcoming'),
        ('final_completed', 'Finalized & Completed'),
        ('cancelled', 'Cancelled')
]
CHECKLIST = [
        'location_id',
        'stock_location_id',
        'schedule_start_date',
        'start_time',
        'end_time',
        'repeat_type',
        'schedule_end_date',
        'all_day',
        'day_mon',
        'day_tue',
        'day_wed',
        'day_thu',
        'day_fri',
        'day_sat',
        'day_sun'
]
REPEAT_TYPE = [
        ('never', 'Never'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
]

class IsyTicketingRequests(models.Model):
    _name = 'isy.ticketing.requests'
    _inherit = 'mail.thread'

    def _name_search(self,display_stock_building, args=None, operator='ilike', limit=100):
        if operator == 'like': 
            operator = 'ilike'

        versions=self.search([('display_stock_building', operator, display_stock_building)], limit=limit)
        return versions.name_get()
    
    def _name_search_location(self,display_stock_location, args=None, operator='ilike', limit=100):
        if operator == 'like': 
            operator = 'ilike'

        versions=self.search([('display_stock_location', operator, display_stock_location)], limit=limit)
        return versions.name_get()

        @api.model
        def fields_get(self, fields=None, attributes=None):
            try:
                hide = [
                    'building_id', 'stock_building_id', 'location_address', 'location_id',
                    'stock_location_id', 'day_mon', 'day_tue', 'day_wed', 'day_thu',
                    'day_fri', 'day_sat', 'day_sun'
                ]
                
                # Check if 'fields' argument is passed, otherwise use None
                if fields is not None:
                    res = super(IsyTicketingRequests, self).fields_get(fields, attributes)
                else:
                    res = super(IsyTicketingRequests, self).fields_get(attributes=attributes)
                
                # Hide specified fields
                for field in hide:
                    if field in res:
                        res[field]['selectable'] = False
                
                return res
            except TypeError as e:
                _logger.error("TypeError in fields_get: %s", e)
                raise

    name = fields.Char(string='RequestID', readonly=True,
                                       required=True, copy=False, default='New',)
    request_type_id = fields.Many2one(
            'isy.request.type', string='Request Type', help='Choose your related request type.')
    building_id = fields.Many2one('isy.building', string='Building')
    location_id = fields.Many2one('isy.resources.locations', string='Resource/Location')
    location_address = fields.Char(string="Address", )
    
    #new building and location
    stock_building_id = fields.Many2one('stock.location', string='Building', domain=[('usage','=','internal'),('location_id','=',False)])
    stock_location_id = fields.Many2one('stock.location', string='Resource/Location', domain=[('usage','=','internal'),('location_id','!=',False)])
    is_old_location = fields.Boolean(string='Is old location(?)', default=False)
    display_stock_building = fields.Char(string="Building", compute="_get_display_name",store=True,search=_name_search)
    display_stock_location = fields.Char(string="Resource/Location", compute="_get_display_name_location",store=True,search=_name_search_location)


    equipment_id = fields.Many2one('product.product', string='Equipments')
    due_date = fields.Date(string='Due')
    start_time = fields.Float(string='Start Time', default=0.000)
    end_time = fields.Float(string='End Time', default=0.000)
    description = fields.Text(string='Note')

    request = fields.Char(string='Request')
    user_ids = fields.Many2many('res.users', 'isy_ticketing_requests_res_users_rel',
                                                            'isy_ticketing_request_id', 'user_id', string="Assign Users")
    approver_ids = fields.Many2one('res.users', string="Appprover", readonly=True)
    resolved_date = fields.Datetime(string="Resolved Date")
    resolve_user_id = fields.Many2one('res.users', string="Resolver")
    state = fields.Selection(STATES, string='State', default='draft')
    resolution_description = fields.Text(string="Resolution Description")

    #transportation request field only
    date_from = fields.Datetime(string='From')
    date_to = fields.Datetime(string='To')
    pick_up_location = fields.Char(string="Pickup Location")
    dropoff_location = fields.Char(string="Dropoff Location")
    fleet = fields.Many2one('fleet.vehicle', string='Request Vehicle')
    reserved_fleet_id = fields.Many2one('fleet.reserved', invisible=1, copy=False)
    no_of_passengers = fields.Selection('_get_no_of_passengers', string="Number of Passengers")
    pick_up_at_dropoff_location = fields.Boolean(string='Pickup at dropoff location (?)', default=False)
    driver_id = fields.Many2one('res.users', string="Driver")
    is_driver_allocated = fields.Boolean("Is Driver Allocated(?)")
    before_starttime = fields.Selection([('00', '00'), ('15', '15'), ('30', '30'), ('45', '45')], string="Before Start Time (Mins)", default="00")
    rental_vehicle = fields.Char(string="Rental Vehicle Description")
    # configurable fields lists below:
    key_type = fields.Selection(
            KEY_SELECTION_TYPE, string='Master Requests Type', help='hidden field to control menu level')
    is_request = fields.Boolean(
            string='Is Request Enable(?)', help='To handle request show/hide', default=False)

    #schedule request fields only
    event_name = fields.Char(string='Event Name')
    schedule_start_date = fields.Date(string='Start')
    all_day = fields.Boolean(string="All Day(?)")
    repeat_type = fields.Selection(REPEAT_TYPE, string="Repeats", default="never", help="Never: not repeated. \n Daily: It will run daily start from the start date until date until.\nMonthly: It will run monthly from the start date until date until.")
    schedule_end_date = fields.Date(string="Date Until")
    day_mon = fields.Boolean(string="MON")
    day_tue = fields.Boolean(string="TUE")
    day_wed = fields.Boolean(string="WED")
    day_thu = fields.Boolean(string="THU")
    day_fri = fields.Boolean(string="FRI")
    day_sat = fields.Boolean(string="SAT")
    day_sun = fields.Boolean(string="SUN")
    groups_sponsoring_activity = fields.Char(string="Groups Sponsoring Activity")
    sponsor_1 = fields.Char(string="Sponsor/s 1")
    sponsor_2 = fields.Char(string="Sponsor/s 2")

    requests_details = fields.One2many('isy.ticketing.requests.details', 'ticket_id', string="Request Details")
    parent_id = fields.Many2one('isy.ticketing.requests', string="Ref Request#")
    cancellation_reason = fields.Char(string='Cancellation Reason')
    # need_chair = fields.Boolean(string = "Do you need chairs?")
    # need_chair_qty = fields.Integer(string = "If yes, how many chairs?")
    # need_table = fields.Boolean(string = "Do you need tables?")
    # need_table_qty = fields.Integer(string = "If yes, how many tables?")
    # need_pa = fields.Boolean(string = "Do you need a PA System?")
    # need_speaker_stand = fields.Boolean(string = "Do you need a speaker's stand?")

    date_from_toshow = fields.Datetime(string='From Date (To Show)',compute='compute_date',store=True)
    date_to_toshow = fields.Datetime(string='To Date (To Show)',compute='compute_date',store=True)

    @api.onchange('description')
    def _onchange_description(self):
        if self.description:
            self._send_email_notification()
    
    def _send_email_notification(self):
        self.ensure_one()  # Ensure only one record is processed
        if not self.id:
            return  # Skip if the record is not yet saved
        # Retrieve the email template
        template = self._get_related_email_template(self.key_type, 'update')
        if template:
            # Send email with force_send to ensure immediate sending
            template.sudo().send_mail(self.id, force_send=True)
    

    def send_email_if_over_25_hours(self):
        # Get the current time
        
        current_time = fields.Datetime.now()
        # Find records created over 25 hours ago and still in 'draft' or 'waitingforapproval' state
        records_to_notify = self.search([
            ('create_date', '<', current_time - timedelta(hours=25)),
            ('state', 'in', ['draft', 'waitingconfirmation']),
            ('key_type', '=', 'maintenance')
            ])
        for record in records_to_notify:
            key = record.key_type
            if record.key_type == 'maintenance':
                # Send email to the appropriate person (approver, user, etc.)
                template = self._get_related_email_template(record.key_type, 'reminder')
                if template:
                    self.env['mail.template'].browse(template.id).sudo().send_mail(record.id)


    @api.depends('date_from','date_to')
    def compute_date(self):
        for rec in self:
            if rec.date_from and rec.date_to:
                rec.date_from_toshow = rec.date_from+timedelta(hours=6, minutes=30)
                rec.date_to_toshow = rec.date_to+timedelta(hours=6, minutes=30)

    @api.model
    def fields_view_get(self, view_id=None, view_type='form', toolbar=False, submenu=False):
        res = super(IsyTicketingRequests, self).fields_view_get(view_id=view_id, view_type=view_type, toolbar=toolbar, submenu=submenu)
        if view_type == 'form' and self.env.context.get('params'):
            #if self.env.user.has_group('base.group_portal') and self.env.us.portal_transportation_request_user:
            doc = etree.XML(res['arch'])
            if self.env.context['params'].get('id'):
                obj_rec = self.browse([self.env.context['params'].get('id')])
                if obj_rec.key_type == 'transportation' and obj_rec.state in ('waitingfordriverassign','waitingforapproval', 'pendingresolution'):
                    if self.env.user.has_group('base.group_portal') and self.env.user.portal_transportation_request_user:
                        fleet_field = doc.xpath("//field[@name='fleet']")
                        fleet_field[0].set('modifiers', '{"readonly": false}')
                        rental_vehicle = doc.xpath("//field[@name='rental_vehicle']")
                        rental_vehicle[0].set('modifiers', '{"readonly": false}')
                    elif self.env.user.has_group('isy_ticketing.group_tnr_user'):
                        fleet_field = doc.xpath("//field[@name='fleet']")
                        fleet_field[0].set('modifiers', '{"readonly": false}')
                        rental_vehicle = doc.xpath("//field[@name='rental_vehicle']")
                        rental_vehicle[0].set('modifiers', '{"readonly": false}')
                    elif self.env.user.has_group('isy_ticketing.group_tnr_manager'):
                        fleet_field = doc.xpath("//field[@name='fleet']")
                        fleet_field[0].set('modifiers', '{"readonly": false}')
                        rental_vehicle = doc.xpath("//field[@name='rental_vehicle']")
                        rental_vehicle[0].set('modifiers', '{"readonly": false}')

            if self.env.user.has_group('isy_ticketing.group_mr_manager') and self.env.context.get('params'):
                if self.env.context['params'].get('id'):
                    obj_rec = self.browse([self.env.context['params'].get('id')])
                    if obj_rec.state in ('draft', 'waitingforapproval'):
                        request_type = doc.xpath("//field[@name='request_type_id']")
                        request_type[0].set('modifiers', '{"readonly": false}')
                    else:
                        request_type = doc.xpath("//field[@name='request_type_id']")
                        request_type[0].set('modifiers', '{"readonly": true}')

                    if obj_rec.state != 'waitingforapproval':
                        request_type = doc.xpath("//field[@name='user_ids']")
                        request_type[0].set('modifiers', '{"readonly": true}')
                    else:
                        request_type = doc.xpath("//field[@name='user_ids']")
                        request_type[0].set('modifiers', '{"readonly": false}')
            elif not self.env.user.has_group('isy_ticketing.group_mr_manager'):
                request_type = doc.xpath("//field[@name='user_ids']")
                request_type[0].set('modifiers', '{"readonly": true}')

            res['arch'] = etree.tostring(doc)
            # res contains the view form, and you can manipulate res string, as you desired.
        return res

    def clean_old_data(self):
        #unlink str(datetime.datetime.now().today())
        obj_old_recs = self.env['isy.resources.locations.reserved'].search([('date_to', '<', str(datetime.datetime.now().today()))])
        obj_old_recs.sudo().unlink()
        #change state str(datetime.datetime.now().today().date())
        obj_old_requests = self.env['isy.ticketing.requests'].search([('schedule_end_date', '<=', str(datetime.datetime.now().today())), ('key_type', '=', 'schedule'), ('state', '=', 'final_upcoming')])
        for obj_old_request in obj_old_requests:
            recs = self.env['isy.resources.locations.reserved'].search([('reserved_obj', '=', obj_old_request.id)])
            if not recs:
                obj_old_request.state = 'final_completed'

    def redirect_schedule_request(self):
        self.clean_old_data()
        form_id = self.env.ref('isy_ticketing.isy_ticketing_form_ser').id
        tree_id = self.env.ref('isy_ticketing.isy_ticketing_list_ser').id

        return {
                'name': 'Schedule Requests',
                'type': 'ir.actions.act_window',
                'view_mode': 'tree,form',
                'domain': [('key_type', '=', 'schedule')],
                'context': {'default_key_type': 'schedule'},
                'res_model': 'isy.ticketing.requests',
                'view_id': tree_id,
                'views': [(tree_id, 'tree'), (form_id, 'form')],
                'target': 'current'
        }

    def redirect_stationary_request(self):
        emp_id = self.env['hr.employee'].sudo().search([('user_id','=',self.env.user.id)])
        return {
            'type': 'ir.actions.act_url',
            'target': 'new',
            'url': 'http://stationery.isyedu.org/login.php?email=%s&staff_id=%s' % (self.env.user.login,emp_id.barcode),
        }

    def allocate_driver(self):
        if self.state not in ('waitingfordriverassign','waitingforapproval','pendingresolution'):
            raise UserError(_("Allow only at WaitingForDriverAssign state"))
        user_ids = self.user_ids.ids
        if not self.env.user.has_group('isy_ticketing.group_tnr_manager'):
            if self.env.user.id not in user_ids:
                raise UserError(_("You are not in the assigned users!"))

        if not self.fleet:
            raise UserError(_("Please choose a vehicle."))
        self.fleet_reserved()
        wizard_form = self.env.ref('isy_ticketing.view_isy_driver_allocation', False)
        view_id = self.env['isy.driver.allocation']

        vals = {
            'name': False,
            'date_from': str(self.date_from),
            'date_to': str(self.date_to)
        }
        new = view_id.create(vals)

        if new.date_from and new.date_to:
            new.name = False
            driver_obj = self.env['res.users'].search([('portal_transportation_request_driver', '=', True)])
            for i in driver_obj:
                check_availability = True

                for each in i.reserved_time:
                    # if each.date_from <= self.date_from <= each.date_to:
                    #     i.sudo().write({'check_availability': False})
                    #     break
                    # elif self.date_from < each.date_from:
                    #     if each.date_from <= self.date_to <= each.date_to:
                    #         i.sudo().write({'check_availability': False})
                    #         break
                    #     elif self.date_to > each.date_to:
                    #         i.sudo().write({'check_availability': False})
                    #         break
                    #     else:
                    #         i.sudo().write({'check_availability': True})
                    # else:
                    #     i.sudo().write({'check_availability': True})

                    if not (self.date_from>=each.date_to or self.date_to<=each.date_from):
                        check_availability = False #busy
                        break
                    else:
                        check_availability = True
                i.sudo().write({'check_availability': check_availability})

        print("-----------------------------------------------------")
        print(vals)
        print("-----------------------------------------------------")
        return {
                                'name': _('Driver Allocation'),
                                'type': 'ir.actions.act_window',
                                'res_model': 'isy.driver.allocation',
                                'res_id': new.id,
                                'view_id': wizard_form.id,
                                'view_mode': 'form',
                                'target': 'new',
                                'context': {},
                        }
        return True

    def _get_no_of_passengers(self):
        nop = 0
        no_of_passengers = []
        while nop < 25:
            nop += 1
            no_of_passengers.append((str(nop), nop))
        return no_of_passengers

    @api.onchange('request_type_id')
    def change_request_type(self):
        if self.request_type_id:
            self.is_request = True if self.request_type_id.is_request else False


    #new building and location on change
    @api.onchange('stock_building_id')
    def change_stock_building_id(self):
        if self.stock_building_id:
            self.stock_location_id = False
            return {'domain': {'stock_location_id': [('location_id', '=', self.stock_building_id.id)]}}
        else:
            self.stock_location_id = False
            return []

    @api.model
    def _get_display_name(self):
        for rec in self:
            if rec.building_id:
                rec.display_stock_building = rec.building_id.name
            else:
                rec.display_stock_building = rec.stock_building_id.name
    
    @api.model
    def _get_display_name_location(self):
        for rec in self:
            if rec.location_id:
                rec.display_stock_location = rec.location_id.name
            else:
                rec.display_stock_location = rec.stock_location_id.name

    #end new building and location on change

    @api.onchange('building_id')
    def change_building_id(self):
        if self.building_id:
            return {'domain': {'location_id': [('building_id', '=', self.building_id.id)]}}
        else:
            return []

    @api.onchange('location_id')
    def change_locatioN_id(self):
        if self.location_id.is_location == True:
            self.location_address = self.location_id.address
        else:
            self.location_address = ''

    def get_emails_list(self, val):
        email_ids = ''
        if self.key_type == 'maintenance':

            #only Maintenance Request Manager will receive email
            if val == 'mr_received':
                user_ids = self.env.ref('isy_ticketing.group_mr_manager').users
                for user_id in user_ids:
                    if not user_id.partner_id.email == 'odooadmin@isyedu.org':
                        email_ids += str(user_id.partner_id.email) + ','
                return email_ids

            #only assign person will receive email
            elif val == 'mr_received_approved':
                user_ids = self.user_ids
                for user_id in user_ids:
                    if not user_id.partner_id.email == 'odooadmin@isyedu.org':
                        email_ids += str(user_id.partner_id.email) + ','
                email_ids += str(self.create_uid.partner_id.email)
                return email_ids

            #only request person and maintenance request manager will receive email
            elif val == 'mr_received_approved_resolved':
                user_ids = self.env.ref('isy_ticketing.group_mr_manager').users
                for user_id in user_ids:
                    if not user_id.partner_id.email == 'odooadmin@isyedu.org':
                        email_ids += str(user_id.partner_id.email) + ','
                email_ids += str(self.create_uid.partner_id.email)
                return email_ids
            elif val == 'mr_cancelled':
                user_ids = self.env.ref('isy_ticketing.group_mr_manager').users
                for user_id in user_ids:
                    if not user_id.partner_id.email == 'odooadmin@isyedu.org':
                        email_ids += str(user_id.partner_id.email) + ','
                email_ids += str(self.create_uid.partner_id.email)
                return email_ids
        elif self.key_type == 'schedule':
            if val == 'ser_received':
                user_ids = self.env.ref('isy_ticketing.group_ser_user').users
                user_ids += self.env.ref('base.group_portal').users.filtered(lambda l: l.portal_schedule_request_user == True)
                for user_id in user_ids:
                    if not user_id.partner_id.email == 'odooadmin@isyedu.org':
                        email_ids += str(user_id.partner_id.email) + ','
                return email_ids
            elif val == 'ser_received_approved':
                user_ids = self.env.ref('isy_ticketing.group_ser_user').users
                user_ids += self.env.ref('base.group_portal').users.filtered(lambda l: l.portal_schedule_request_user == True)
                for user_id in user_ids:
                    if not user_id.partner_id.email == 'odooadmin@isyedu.org':
                        email_ids += str(user_id.partner_id.email) + ','
                email_ids += str(self.create_uid.partner_id.email)
                return email_ids
            elif val == 'ser_cancelled':
                user_ids = self.env.ref('isy_ticketing.group_ser_user').users
                user_ids += self.env.ref('base.group_portal').users.filtered(lambda l: l.portal_schedule_request_user == True)
                for user_id in user_ids:
                    if not user_id.partner_id.email == 'odooadmin@isyedu.org':
                        email_ids += str(user_id.partner_id.email) + ','
                email_ids += str(self.create_uid.partner_id.email)
                return email_ids
        elif self.key_type == 'transportation':
            if val == 'tnr_received':
                user_ids = list(set(self.env.ref('isy_ticketing.group_tnr_user').users)-set(self.env.ref('isy_ticketing.group_tnr_manager').users))
                for user_id in user_ids:
                    if not user_id.partner_id.email == 'odooadmin@isyedu.org':
                        email_ids += str(user_id.partner_id.email) + ','
                return email_ids
            elif val == 'tnr_received_toapprove':
                user_ids = self.env.ref('isy_ticketing.group_tnr_manager').users
                for user_id in user_ids:
                    if not user_id.partner_id.email == 'odooadmin@isyedu.org':
                        email_ids += str(user_id.partner_id.email) + ','
                return email_ids
            elif val == 'tnr_received_approved':
                user_ids = self.user_ids
                # for mgr in self.env.ref('isy_ticketing.group_tnr_manager').users:
                #     if not mgr.id in user_ids.ids:
                #         if not mgr.partner_id.email == 'odooadmin@isyedu.org':
                #             user_ids += mgr
                for user_id in user_ids:
                    if not user_id.partner_id.email == 'odooadmin@isyedu.org':
                        email_ids += str(user_id.partner_id.email) + ','
                email_ids += str(self.create_uid.partner_id.email)
                return email_ids
            elif val == 'tnr_driver_assign':
                user_ids = self.user_ids
                # for mgr in self.env.ref('isy_ticketing.group_tnr_manager').users:
                #     if not mgr.id in user_ids.ids:
                #         if not mgr.partner_id.email == 'odooadmin@isyedu.org':
                #             user_ids += mgr
                for user_id in user_ids:
                    if not user_id.partner_id.email == 'odooadmin@isyedu.org':
                        email_ids += str(user_id.partner_id.email) + ','
                #email_ids += str(self.create_uid.partner_id.email) + ','
                email_ids += str(self.driver_id.partner_id.email)
                return email_ids
            elif val == 'tnr_driver_assign_requestor_info':
                email_ids = str(self.create_uid.partner_id.email)
                return email_ids
            elif val == 'tnr_received_approved_resolved':
                user_ids = self.env.ref('isy_ticketing.group_tnr_manager').users
                for user_id in user_ids:
                    if not user_id.partner_id.email == 'odooadmin@isyedu.org':
                        email_ids += str(user_id.partner_id.email) + ','
                email_ids += str(self.create_uid.partner_id.email)
                return email_ids
            elif val == 'tnr_cancelled':
                user_ids = self.env.ref('isy_ticketing.group_tnr_user').users # include John Whalen
                # user_ids += self.env.ref('base.group_portal').users.filtered(lambda l: l.portal_transportation_request_user == True)
                for user_id in user_ids:
                    if not user_id.partner_id.email == 'odooadmin@isyedu.org':
                        email_ids += str(user_id.partner_id.email) + ','
                email_ids += str(self.create_uid.partner_id.email)
                return email_ids
        else:
            for partner in self.message_partner_ids:
                email_ids += str(partner.email) + ','

            return email_ids

    def get_assign_users(self):
        str = ''
        if self.user_ids:
            for usr in self.user_ids:
                if len(self.user_ids) == 1:
                    str = usr.name
                else:
                    if not str:
                        str = usr.name + ','
                    else:
                        str += usr.name + ','
            return str

    def get_isy_ticketing_status(self):
        return dict(self._fields['state'].selection).get(self.state)

    @api.model
    def create(self, vals):
        _logger.info('aaaaaaaa')
        _logger.info(vals)
        if vals.get('name', 'New') == 'New':
            if vals.get('key_type') == 'maintenance':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                        'isy.ticketing.requests.maintenance') or 'New'
            if vals.get('key_type') == 'planning':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                        'isy.ticketing.requests.planning') or 'New'
            if vals.get('key_type') == 'schedule':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                        'isy.ticketing.requests.schedule') or 'New'
                if vals.get('all_day') == True:
                    vals['start_time'] = 0.05*60*60
                    vals['end_time'] = 23.916*60*60
            # if vals.get('key_type') == 'technology':
            # 	vals['name'] = self.env['ir.sequence'].next_by_code(
            # 		'isy.ticketing.requests.technology') or 'New'
            if vals.get('key_type') == 'transportation':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                        'isy.ticketing.requests.transportation') or 'New'

        if vals.get('key_type')=='maintenance':
            user = self.env['res.users'].search([('email', '=', 'pnyein@isyedu.org')], limit=1) 
            if user:
                vals['user_ids'] = [(6, 0, [user.id])]


        if vals.get('key_type')=='transportation':
            if not vals.get('start_time') or not vals.get('end_time') or vals.get('start_time')==0 or vals.get('end_time')==0:
                raise UserError('Please choose Start Time (HH:MM) and End Time (HH:MM).')
            vals['state'] = 'waitingfordriverassign'
            vals['user_ids'] = list(set(self.env.ref('isy_ticketing.group_tnr_user').users.ids)-set(self.env.ref('isy_ticketing.group_tnr_manager').users.ids))
        elif vals.get('key_type') == 'maintenance':
            vals['state'] = 'waitingconfirmation'
        else:
            vals['state'] = 'waitingforapproval'
        if vals.get('due_date'):
            if vals.get('due_date') < str(fields.datetime.now().date()):
                raise ValidationError(_("Due date must be after or equal current date!"))
        if vals.get('date_from') or vals.get('date_to'):
            if vals.get('date_from') < str(fields.datetime.now()):
                raise ValidationError(_("Date From must be after or equal current date!"))
            if vals.get('date_to') < str(fields.datetime.now()):
                raise ValidationError(_("Date To must be after or equal current date!"))
        if vals.get('schedule_start_date'):
            if vals.get('schedule_start_date') < str(fields.datetime.now().date()):
                raise ValidationError(_("Date From must be after or equal current date!"))

        result = super(IsyTicketingRequests, self).create(vals)
        #message = """
        #Hello world
        #"""
        #result.message_post(body=message)

        self.sudo().add_follower(result)

        template = self._get_related_email_template(result.key_type, 'received')

        self.env['mail.template'].browse(template.id).sudo().send_mail(result.id)
        # if result.key_type == 'transportation':
        #     result.fleet_reserved()
        # elif result.key_type == 'schedule':
        if result.key_type == 'schedule':
            result.resources_locations_reserved()
        return result

    def resources_locations_reserved(self):
        #Daily Avoid Sat, Sunday --> Improvement based on include weekends?
        #Monthly Allow all
        #Weekly allow all
        if self.start_time >= self.end_time:
            raise ValidationError("Start time must be before end time!")

        schedule_start_date = self.schedule_start_date
        schedule_end_date = self.schedule_end_date
        start_time, end_time = self.start_time, self.end_time
        #start_time_str = '{0:02.0f}:{1:02.0f}'.format(*divmod(float(self.start_time) / 60, 60))
        start_time_str = f"{int(self.start_time):02}:00"
        end_time_str = f"{int(self.end_time):02}:00"
        #end_time_str = '{0:02.0f}:{1:02.0f}'.format(*divmod(float(self.end_time) / 60, 60))
        lst_reserved = []
        dict_reserved = {}
        if self.repeat_type == 'never':
            self._validate_avaiable(schedule_start_date, start_time_str, end_time_str)

            dict_reserved = {
                                                    'user': self.create_uid.id,
                                                    'date_from': str(schedule_start_date) + ' ' + start_time_str,
                                                    'date_to': str(schedule_start_date) + ' ' + end_time_str,
                                                    'reserved_obj': self.stock_location_id.id,
                                                    'request_id': self.id
                                            }
            lst_reserved.append(dict_reserved)
        elif self.repeat_type == 'daily':
            lst_dates = self.repeated_range_calculation(schedule_start_date, schedule_end_date, 'daily')
            for lst_date in lst_dates:
                dict_reserved = {
                                                        'user': self.create_uid.id,
                                                        'date_from': lst_date['datetime_start'],
                                                        'date_to':  lst_date['datetime_end'],
                                                        'reserved_obj': self.stock_location_id.id,
                                                        'request_id': self.id
                                                }
                lst_reserved.append(dict_reserved)
        elif self.repeat_type == 'weekly':
            lst_dates = self.repeated_range_calculation(schedule_start_date, schedule_end_date, 'weekly')
            for lst_date in lst_dates:
                dict_reserved = {
                                                        'user': self.create_uid.id,
                                                        'date_from': lst_date['datetime_start'],
                                                        'date_to':  lst_date['datetime_end'],
                                                        'reserved_obj': self.stock_location_id.id,
                                                        'request_id': self.id
                                                }
                lst_reserved.append(dict_reserved)

        elif self.repeat_type == 'monthly':
            end_date_of_month = calendar.monthrange(schedule_end_date.year, schedule_end_date.month)[1]
            if end_date_of_month != schedule_end_date.day:
                raise ValidationError(_("Date until must be end of the month!"))
            lst_dates = self.repeated_range_calculation(schedule_start_date, schedule_end_date, 'monthly')
            for lst_date in lst_dates:
                dict_reserved = {
                                                        'user': self.create_uid.id,
                                                        'date_from': lst_date['datetime_start'],
                                                        'date_to':  lst_date['datetime_end'],
                                                        'reserved_obj': self.stock_location_id.id,
                                                        'request_id': self.id
                                                }
                lst_reserved.append(dict_reserved)
        reserved_id = self.location_id.reserved_time.create(lst_reserved)

    def repeated_range_calculation(self, date1, date2, repeat_type):
        lst_date = []
        dist_date = {}
        day_avoid = [5, 6]
        start_time_str = '{0:02.0f}:{1:02.0f}'.format(*divmod(float(self.start_time) / 60, 60))
        end_time_str = '{0:02.0f}:{1:02.0f}'.format(*divmod(float(self.end_time) / 60, 60))

        if repeat_type == 'daily':
            for n in range(int((date2 - date1).days) + 1):
                append_date = date1 + timedelta(n)
                if append_date.weekday() not in day_avoid:
                    self._validate_avaiable(append_date, start_time_str, end_time_str)
                    dict_date = {
                            'datetime_start': str(append_date) + ' ' + str(start_time_str),
                            'datetime_end': str(append_date) + ' ' + str(end_time_str)
                    }
                    lst_date.append(dict_date)
        elif repeat_type == 'weekly':
            selected_day = []
            if self.day_mon:
                selected_day.append(0)
            if self.day_tue:
                selected_day.append(1)
            if self.day_wed:
                selected_day.append(2)
            if self.day_thu:
                selected_day.append(3)
            if self.day_fri:
                selected_day.append(4)
            if self.day_sat:
                selected_day.append(5)
            if self.day_sun:
                selected_day.append(6)

            for n in range(int((date2 - date1).days) + 1):
                append_date = date1 + timedelta(n)
                if append_date.weekday() in selected_day:
                    self._validate_avaiable(append_date, start_time_str, end_time_str)
                    dict_date = {
                            'datetime_start': str(append_date) + ' ' + str(start_time_str),
                            'datetime_end': str(append_date) + ' ' + str(end_time_str)
                    }
                    lst_date.append(dict_date)
        elif repeat_type == 'monthly':
            num_months = (date2.year - date1.year) * 12 + (date2.month - date1.month)
            for i in range(num_months + 1):
                after_inc_month = self.increase_month(date1, i)
                self._validate_avaiable(after_inc_month, start_time_str, end_time_str)
                dict_date = {
                        'datetime_start': str(after_inc_month) + ' ' + str(start_time_str),
                        'datetime_end': str(after_inc_month) + ' ' + str(end_time_str)
                }
                lst_date.append(dict_date)
        return lst_date

    def _validate_avaiable(self, append_date, start_time_str, end_time_str):
        obj_isy_rlr = self.env['isy.resources.locations.reserved']
        # date_from validation based on start_time and end_time
        obj_isy_rlr_recs = obj_isy_rlr.search([('reserved_obj', '=', self.stock_location_id.id), ('date_from', '>=', str(append_date) + ' ' + start_time_str), ('date_from', '<=', str(append_date) + ' ' + end_time_str)])
        if obj_isy_rlr_recs:
            raise ValidationError(_("Resource/Location [ %s ] is not available for your schedule start datetime!") % (self.stock_location_id.name,))
        # date_to validation based on start_time and end_time
        if not obj_isy_rlr_recs:
            obj_isy_rlr_recs = obj_isy_rlr.search([('reserved_obj', '=', self.stock_location_id.id), ('date_to', '>=', str(append_date) + ' ' + start_time_str), ('date_to', '<=', str(append_date) + ' ' + end_time_str)])
            if obj_isy_rlr_recs:
                raise ValidationError(_("Resource/Location [ %s ] is not available for your schedule start datetime!") % (self.location_id.name,))

        # start_time validation based on date_from and date_to
        if not obj_isy_rlr_recs:
            obj_isy_rlr_recs = obj_isy_rlr.search([('reserved_obj', '=', self.stock_location_id.id), ('date_from', '<=', str(append_date) + ' ' + start_time_str), ('date_to', '>=', str(append_date) + ' ' + start_time_str)])
            if obj_isy_rlr_recs:
                raise ValidationError(_("Resource/Location [ %s ] is not available for your schedule start datetime!") % (self.stock_location_id.name,))

        # end_time validation based on date_from and date_to
        if not obj_isy_rlr_recs:
            obj_isy_rlr_recs = obj_isy_rlr.search([('reserved_obj', '=', self.stock_location_id.id), ('date_from', '<=', str(append_date) + ' ' + end_time_str), ('date_to', '>=', str(append_date) + ' ' + end_time_str)])
            if obj_isy_rlr_recs:
                raise ValidationError(_("Resource/Location [ %s ] is not available for your schedule end datetime!") % (self.stock_location_id.name,))

    def increase_month(self, sourcedate, months):
        month = sourcedate.month - 1 + months
        year = sourcedate.year + month // 12
        month = month % 12 + 1
        day = min(sourcedate.day, calendar.monthrange(year, month)[1])
        return datetime.date(year, month, day)

    def write(self, vals):
        #maintenance validation
        if self.key_type == 'maintenance' and vals.get('description') and self.state not in ('resolved', 'cancelled') and not self.env.user.has_group('isy_ticketing.group_mr_manager'):
            raise UserError(_("Only Facility Manager Role can edit description"))
        elif self.key_type == 'maintenance' and vals.get('description') and self.state in ('resolved', 'cancelled'):
            raise UserError(_("Only Allow to edit except Resolved State and Cancelled State"))
        elif self.key_type == 'maintenance' and vals.get('before_starttime') and not self.env.user.has_group('isy_ticketing.group_mr_manager'):
            raise ValidationError(_("Only Maintenance Manager can edit setup time."))

        elif vals.get('user_ids') and not self.env.user.has_group('isy_ticketing.group_mr_manager') and self.state == 'waitingforapproval':
            raise ValidationError(_("Only Maintenance Manager can assign users"))
        #transportation validation
        elif self.key_type == 'transportation' and vals.get('fleet') and self.state not in ('resolved', 'cancelled') and not self.env.user.has_group('isy_ticketing.group_tnr_user'):
            if self.env.user.has_group('base.group_portal') and not self.env.user.portal_transportation_request_user:
                raise UserError(_("Only Transportation Manager Role can change vehicle."))
        elif self.key_type == 'transportation' and vals.get('no_of_passengers') and self.state not in ('resolved', 'cancelled') and not self.env.user.has_group('isy_ticketing.group_tnr_user'):
            raise UserError(_("Only Transportation Manager Role can change number of passengers."))
        elif self.key_type == 'transportation' and vals.get('rental_vehicle') and self.state not in ('resolved', 'cancelled') and not self.env.user.has_group('isy_ticketing.group_tnr_user'):
            if self.env.user.has_group('base.group_portal') and not self.env.user.portal_transportation_request_user:
                raise UserError(_("Only Transportation Manager Role can change."))
        elif self.key_type == 'transportation' and vals.get('rental_vehicle') and self.state in ('resolved', 'cancelled'):
            raise UserError(_("Only Allow to change except Resolved State and Cancelled State"))
        elif self.key_type == 'transportation' and vals.get('fleet') and self.state in ('resolved', 'cancelled'):
            raise UserError(_("Only Allow to change except Resolved State and Cancelled State"))
        elif self.key_type == 'transportation' and vals.get('no_of_passengers') and self.state in ('resolved', 'cancelled'):
            raise UserError(_("Only Allow to change except Resolved State and Cancelled State"))
        #others
        else:
            # if self.state == 'pendingresolution' and not self.fleet and self.key_type == 'transportation':
            #     if not vals.get('fleet') and vals.get('state') != 'cancelled':
            #         raise ValidationError(_("Please choose a vehicle."))
            #remove old fleet reserved
            if self.key_type == 'transportation' and 'fleet' in vals.keys() and self.fleet.id:
                if vals.get('fleet')!=self.fleet.id:
                    self.reserved_fleet_id.unlink()
            result = super(IsyTicketingRequests, self).write(vals)
            if 'description' in vals:
                self._send_email_notification()
            if self.key_type == 'schedule' and all(item in CHECKLIST for item in [*vals.keys()]):
                self.env['isy.resources.locations.reserved'].search([('request_id', '=', self.id)]).sudo().unlink()
                self.resources_locations_reserved()
            if self.key_type == 'transportation':
                if (vals.get('start_time') or vals.get('end_time') or vals.get('schedule_start_date') or vals.get('schedule_end_date')):
                    if not self.env.user.has_group('isy_ticketing.group_tnr_user') and not self.env.user.portal_transportation_request_user:
                        raise UserError("You can request Transportation Manager<Pyi Nyein> to change date and time.")
                    if self.fleet:
                        self.fleet_reserved(reserved=True)
                    if self.driver_id:
                        self.driver_reserved()
                elif vals.get('fleet'):
                    self.fleet_reserved()
            self.add_follower(self)
            return result

    def add_follower(self, record):
        res_list = []
        if record.user_ids:
            for user_id in record.user_ids:
                if not self.env['mail.followers'].search([('res_id', '=', record.id), ('res_model', '=', 'isy.ticketing.requests'), ('partner_id', '=', user_id.partner_id.id)]):
                    reg = {
                            'res_id': record.id,
                            'res_model': 'isy.ticketing.requests',
                            'partner_id': user_id.partner_id.id,
                    }
                    res_list.append(reg)
        if record.driver_id:
            if not self.env['mail.followers'].search([('res_id', '=', record.id), ('res_model', '=', 'isy.ticketing.requests'), ('partner_id', '=', record.driver_id.partner_id.id)]):
                reg = {
                        'res_id': record.id,
                        'res_model': 'isy.ticketing.requests',
                        'partner_id': record.driver_id.partner_id.id,
                }
                res_list.append(reg)
        channel_id = self.env['discuss.channel'].search([('key_type', '=', record.key_type)])
        if channel_id:
            for cmi in channel_id.channel_partner_ids:
                if not self.env['mail.followers'].search([('res_id', '=', record.id), ('res_model', '=', 'isy.ticketing.requests'), ('partner_id', '=', cmi.id)]):
                    reg = {
                            'res_id': record.id,
                            'res_model': 'isy.ticketing.requests',
                            'partner_id': cmi.id,
                    }
                    res_list.append(reg)

        if record.parent_id:
            index = 0
            while index < len(res_list):
                if res_list[index].get('partner_id') != record.parent_id.create_uid.partner_id.id:
                    res_list.append({
                        'res_id': record.id,
                        'res_model': 'isy.ticketing.requests',
                        'partner_id': record.parent_id.create_uid.partner_id.id,
                    })
                    index += 1
                else:
                    index += 1

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

    def approve_request(self):
        #no need because handle from view.

        if self.key_type == 'transportation':
            if not self.env.user.has_group('isy_ticketing.group_tnr_user') and not self.env.user.portal_transportation_request_user:
                raise UserError(_("Only Transportation Manager Role can request this approval."))
            if not self.fleet or not self.driver_id:
                raise UserError('You first need to assign Vehicle and Driver before request to approve.')
            
            template = self._get_related_email_template(self.key_type, 'tnr_received_toapprove')
            self.env['mail.template'].browse(template.id).sudo().send_mail(self.id)
        self.state = 'waitingforapproval'

    def confirm_process(self):
        #adding CCM approval stage for facility request
        if self.key_type == 'maintenance' and not (
            self.env.user.id == self.approver_ids.id or 
            self.env.user.has_group('isy_ticketing.group_mr_manager')
        ):
            raise UserError('You are not allowed to approve this facility request!')
            
        else:
            self.state = 'waitingforapproval'
            template = self._get_related_email_template(self.key_type, 'to_approve')
            self.env['mail.template'].browse(template.id).sudo().send_mail(self.id)
           
    def approve_process(self):
        #no need because handle from view.

        if not self.env.user.has_group('isy_ticketing.group_mr_manager') and self.key_type == 'maintenance':
            raise ValidationError(_("You do not have approval authorization"))
        if not self.env.user.has_group('isy_ticketing.group_tnr_manager') and self.key_type == 'transportation':
            raise ValidationError(_("You do not have approval authorization"))
        if not self.env.user.has_group('isy_ticketing.group_ser_manager') and self.key_type == 'schedule':
            if self.key_type == 'schedule' and not self.env.user.has_group('isy_ticketing.group_ser_user'):
                raise ValidationError(_("You do not have approval authorization"))

            #handle from view portal but portal user has different sub groups. So, check condition.
        if self.env.user.has_group('base.group_portal') and self.key_type == 'schedule' and not self.env.user.portal_schedule_request_user:
            raise ValidationError(_("You do not have approval authorization"))

        if not self.user_ids and self.key_type != 'schedule':
            raise UserError(_("Please assign to users before approve for this request."))

        self.state = 'pendingresolution' if self.key_type != 'schedule' else 'final_upcoming'
        template = self._get_related_email_template(self.key_type, 'approved')
        self.env['mail.template'].browse(template.id).sudo().send_mail(self.id)

        if self.key_type == 'schedule':
            self.create_related_request()

    def create_related_request(self):
        facility_objs = self.requests_details.filtered(lambda r: r.details_request_type == 'facility')

        fac_list = []
        if facility_objs:
            fac_dict = {}
            fac_desc_note = "This is from Schedule Request by "+self.create_uid.name+" for "+self.event_name+"\n***************************************** "
            irlr_objs = self.env['isy.resources.locations.reserved'].search([('request_id', '=', self.id)])
            if self.description:
                fac_desc_note += "\nNote : "+self.description
            # if self.repeat_type and self.repeat_type!='never':
            #     fac_desc_note += "\nRepeat Type : "+ dict(self._fields['repeat_type'].selection).get(self.repeat_type)
            for irlr_obj in irlr_objs:                    
                fac_desc_note += "\nDate From : " + str(irlr_obj.date_from) + " To : " + str(irlr_obj.date_to) 
                
            count = 1
            for fo in facility_objs:
                fac_desc_note += "\n" + "Description-" + str(count) + ": " + str(fo.name) + "\n" + "Qty For Description-" + str(count) + ": " + str(fo.qty)
                count += 1
            
            fac_dict.update(
                    {
                            'key_type': 'maintenance',
                            #need to make dynamic request type id remaining
                            'request_type_id': self.env['isy.request.type'].search([('key_type', '=', 'maintenance'), ('default_request', '=', True)])[0].id,
                            'stock_building_id': self.stock_building_id.id,
                            'stock_location_id': self.stock_location_id.id,
                            'description': fac_desc_note,
                            'due_date':  str(self.schedule_start_date),
                            'parent_id': self.id,
                            # 'create_uid': self.create_uid.id,

                    }
            )
            new_obj_fac = self.env['isy.ticketing.requests'].sudo().create(fac_dict)
            #self.env.cr.execute(""" update isy_ticketing_requests set create_uid ="""+ str(self.create_uid.id)+""" where id="""+ str(new_obj_fac.id))

        technology_objs = self.requests_details.filtered(lambda r: r.details_request_type == 'technology')
        tech_list = []
        if technology_objs:
            irlr_objs = self.env['isy.resources.locations.reserved'].search([('request_id', '=', self.id)])
            tech_dict = {}
            tech_desc_note = "This is from Schedule Request by "+self.create_uid.name+"<br/>***************************************** "
            if self.description:
                tech_desc_note += "<br/>Note : "+self.description
            # if self.repeat_type and self.repeat_type!='never':
            #     tech_desc_note += "<br/>Repeat Type : "+ dict(self._fields['repeat_type'].selection).get(self.repeat_type)
            for irlr_obj in irlr_objs:
                tech_desc_note += "<br/>Date From : " + str(irlr_obj.date_from) + " " + " To : " + str(irlr_obj.date_to) + "<br/>Location : " + str(irlr_obj.reserved_obj.complete_name)
                
            count = 1
            for fo in technology_objs:
                tech_desc_note += "<br/>" + "Description-" + str(count) + ": " + str(fo.name) + "<br/>" + "Qty For Description-" + str(count) + ": " + str(fo.qty)
                count += 1
            tech_dict.update(
                    {
                            #need to make dynamic request type id remaining
                            'key_type': 'technology',
                            'subject': self.event_name,
                            'body': tech_desc_note,
                            'request_person':  self.env['hr.employee'].search([('user_id', '=', self.create_uid.id)]).id,
                            'request_person_email': self.create_uid.login,
                            'parent_id': self.id,



                    }
            )
            new_obj_tech = self.env['isy.technology.request'].sudo().create(tech_dict)
            #self.env.cr.execute(""" update isy_technology_request set create_uid ="""+ str(self.create_uid.id)+""" where id="""+ str(new_obj_tech.id))

        #self.env.cr.commit()

    # def time_to_localtz(self, val):
    #     if val == 'start_time':
    #         val_time = '{0:02.0f}:{1:02.0f}'.format(*divmod(self.start_time * 60, 60))
    #     elif val == 'end_time':
    #         val_time = '{0:02.0f}:{1:02.0f}'.format(*divmod(self.end_time * 60, 60))
    #
    #     return val_time

    def _get_related_email_template(self, check_key_type, val):
        template = self.env.ref('isy_ticketing.blank_template')
        if check_key_type == 'maintenance':
            if val == 'received':
                template = self.env.ref('isy_ticketing.mr_received')
            elif val == 'to_approve':
                template = self.env.ref('isy_ticketing.mr_to_approve')
            elif val == 'approved':
                template = self.env.ref('isy_ticketing.mr_received_approved')
            elif val == 'resolved':
                template = self.env.ref('isy_ticketing.mr_received_approved_resolved')
            elif val == 'cancelled':
                template = self.env.ref('isy_ticketing.mr_cancelled')
            elif val == 'update':
                template = self.env.ref('isy_ticketing.mr_update')  
            elif val == 'reminder':
                template = self.env.ref('isy_ticketing.mr_reminder')
        # if check_key_type == 'planning':
        # 	template = self.env.ref('isy_ticketing.mr_received')
        if check_key_type == 'schedule':
            if val == 'received':
                template = self.env.ref('isy_ticketing.ser_received')
            elif val == 'approved':
                template = self.env.ref('isy_ticketing.ser_received_approved')
            elif val == 'cancelled':
                template = self.env.ref('isy_ticketing.ser_cancelled')
        if check_key_type == 'technology':
            if val == 'received':
                template = self.env.ref('isy_ticketing.tyr_received')
            elif val == 'approved':
                template = self.env.ref('isy_ticketing.tyr_received_approved')
            elif val == 'resolved':
                template = self.env.ref('isy_ticketing.tyr_received_approved_resolved')
        if check_key_type == 'transportation':
            if val == 'received': # waitingfordriverassign
                template = self.env.ref('isy_ticketing.tnr_received')
            elif val == 'tnr_received_toapprove':
                template = self.env.ref('isy_ticketing.tnr_received_toapprove')
            elif val == 'approved':
                template = self.env.ref('isy_ticketing.tnr_received_approved')
            elif val == 'resolved':
                template = self.env.ref('isy_ticketing.tnr_received_approved_resolved')
            elif val == 'assign':
                template = self.env.ref('isy_ticketing.tnr_driver_assign')
            elif val == 'assign_info':
                template = self.env.ref('isy_ticketing.tnr_driver_assign_requestor_info')
            elif val == 'cancelled':
                template = self.env.ref('isy_ticketing.tnr_cancelled')
        return template

    def resolve_process(self):
        if self.key_type == 'transportation' and self.is_driver_allocated == False and not self.driver_id:
            raise UserError(_("Please allocate driver first"))
        if self.state == 'pendingresolution' and not self.fleet and self.key_type == 'transportation':
            raise ValidationError(_("Please choose a vehicle."))
        _logger.debug("Ticketing Requests Resolve Wizard Start")
        wizard_form = self.env.ref('isy_ticketing.view_isy_ticketing_resolve_wizard', False)
        view_id = self.env['isy.ticketing.resolve.wizard']
        new = view_id.create({})
        user_ids = self.user_ids.ids
        driver_id = self.driver_id.id
        state = self.state

        return {
                                'name': _('Fill your resolution description!'),
                                'type': 'ir.actions.act_window',
                                'res_model': 'isy.ticketing.resolve.wizard',
                                'res_id': new.id,
                                'view_id': wizard_form.id,
                                'view_mode': 'form',
                                'target': 'new',
                                'context': {'user_ids': user_ids, 'driver_id': driver_id, 'state': state},
                        }
        #if not self.env.user.id in self.user_ids.ids:
        #raise UserError(_("Only Assign Users must resolve!"))

        #self.state = 'resolved'
        #self.resolve_user_id = self.env.user.id

    def cancel_process(self):
        if not self.cancellation_reason and self.key_type in ('maintenance', 'transportation'):
            raise ValidationError(_("Please fill cancellation reason."))
        self.state = 'cancelled'

        if self.key_type == 'maintenance':
            template = self._get_related_email_template(self.key_type, 'cancelled')
            self.env['mail.template'].browse(template.id).sudo().send_mail(self.id)

        if self.key_type == 'transportation':
            if self.reserved_fleet_id:
                self.reserved_fleet_id.sudo().unlink()
            if self.driver_id:
                self.driver_id.reserved_time.search([('ticket_id', '=', self.id)]).sudo().unlink()
                self.driver_id.sudo().check_availability = True
            template = self._get_related_email_template(self.key_type, 'cancelled')
            self.env['mail.template'].browse(template.id).sudo().send_mail(self.id)

        if self.key_type == 'schedule':
            self.env['isy.resources.locations.reserved'].search([('request_id', '=', self.id)]).sudo().unlink()
            template = self._get_related_email_template(self.key_type, 'cancelled')
            self.env['mail.template'].browse(template.id).sudo().send_mail(self.id)
            obj_facilities = self.env['isy.ticketing.requests'].search([('parent_id', '=', self.id)])
            for obj_fac in obj_facilities:
                obj_fac.write({'cancellation_reason': self.cancellation_reason})
                obj_fac.cancel_process()
            obj_technologies = self.env['isy.technology.request'].search([('parent_id', '=', self.id)])
            for obj_tech in obj_technologies:
                # obj_tech.write({'state': 'cancelled'})
                obj_tech.request_cancelled()

    @api.constrains('date_from', 'date_to')
    def onchange_date_to(self):
        for each in self:
            if each.date_from > each.date_to:
                raise UserError('Date To must be greater than Date From')

    @api.onchange('schedule_start_date', 'start_time')
    def onchange_schedule_from_datetime(self):
        if self.key_type == 'transportation' and self.schedule_start_date and self.start_time:
            #start_time_str = '{0:02.0f}:{1:02.0f}'.format(*divmod(float(self.start_time) / 60, 60))
            if self.start_time:
                try:
                    start_time = float(self.start_time)  # Ensure it's a float
                    hours = int(start_time)  # Extract the hour part
                    minutes = int((start_time - hours) * 60)  # Convert the decimal part to minutes
                    start_time_str = '{:02}:{:02}'.format(hours, minutes)
                except ValueError:
                    start_time_str = "00:00"  # Default value in case of invalid format
            else:
                start_time_str = "00:00"  # Default value in case of invalid format
            # start_time_str = f"{float(self.start_time):02}:00"
            #date_from = datetime.datetime.strptime(str(self.schedule_start_date) + ' ' + start_time_str + ':00', "%Y-%m-%d %H:%M:%S")
            date_from = datetime.datetime.strptime(f"{self.schedule_start_date} {start_time_str}:00", "%Y-%m-%d %H:%M:%S")
            self.date_from = date_from - timedelta(hours=6, minutes=30)

    @api.onchange('schedule_end_date', 'end_time')
    def onchange_schedule_to_datetime(self):
        if self.key_type == 'transportation' and self.schedule_end_date and self.end_time:
            #end_time_str = '{0:02.0f}:{1:02.0f}'.format(*divmod(float(self.end_time) / 60, 60))
            if self.end_time:
                try:
                    end_time = float(self.end_time)  # Ensure it's a float
                    hours = int(end_time)  # Extract the hour part
                    minutes = int((end_time - hours) * 60)  # Convert the decimal part to minutes
                    end_time_str = '{:02}:{:02}'.format(hours, minutes)
                except ValueError:
                    end_time_str = "00:00"  # Default value in case of invalid format
            else:
                end_time_str = "00:00"  # Default value in case of invalid format
            #end_time_str = f"{float(self.end_time):02}:00"
            #date_to = datetime.datetime.strptime(str(self.schedule_end_date) + ' ' + end_time_str + ':00', "%Y-%m-%d %H:%M:%S")
            date_to = datetime.datetime.strptime(f"{self.schedule_end_date} {end_time_str}:00", "%Y-%m-%d %H:%M:%S")
            self.date_to = date_to - timedelta(hours=6, minutes=30)

    @api.onchange('date_from', 'date_to')
    def check_availability(self):
        if self.date_from and self.date_to and self.no_of_passengers:
            self.fleet = ''
            fleet_obj = self.env['fleet.vehicle'].search([])
            for i in fleet_obj:
                for each in i.reserved_time:
                    if each.date_from <= self.date_from <= each.date_to:
                        i.write({'check_availability': False})
                    elif self.date_from < each.date_from:
                        if each.date_from <= self.date_to <= each.date_to:
                            i.write({'check_availability': False})
                        elif self.date_to > each.date_to:
                            i.write({'check_availability': False})
                        else:
                            i.write({'check_availability': True})
                    else:
                        i.write({'check_availability': True})

    def fleet_reserved(self,reserved=False):
        fleet_obj = self.fleet
        check_availability = 0
        for each in fleet_obj.reserved_time.filtered(lambda x: x.id!=self.reserved_fleet_id.id):
            # if each.date_from <= self.date_from <= each.date_to:
            #     check_availability = 1
            # elif self.date_from < each.date_from:
            #     if each.date_from <= self.date_to <= each.date_to:
            #         check_availability = 1
            #     elif self.date_to > each.date_to:
            #         check_availability = 1
            #     else:
            #         check_availability = 0
            # else:
            #     check_availability = 0
            if not (self.date_from>=each.date_to or self.date_to<=each.date_from):
                check_availability = 1
                user = each.user.name
                e_df = each.date_from+timedelta(hours=6,minutes=30)
                e_dt = each.date_to+timedelta(hours=6,minutes=30)
                break
        
        if check_availability == 0:
            if reserved==True:
                self.reserved_fleet_id.sudo().write({
                                            'date_from': self.date_from,
                                            'date_to': self.date_to,
                                            })
            else:
                if fleet_obj and not fleet_obj.reserved_time.filtered(lambda x: x.id==self.reserved_fleet_id.id):
                    reserved_id = fleet_obj.reserved_time.create({'user': self.create_uid.id,
                                                                   'date_from': self.date_from,
                                                                   'date_to': self.date_to,
                                                                   'reserved_obj': fleet_obj.id,
                                                                   })
                    self.write({'reserved_fleet_id': reserved_id.id})
        else:
            raise UserError('Sorry This vehicle is already requested by %s from %s to %s.'%(user,e_df,e_dt))



    def driver_reserved(self):
        driver_obj = self.driver_id
        check_availability = 0
        for each in driver_obj.reserved_time.filtered(lambda x: x.ticket_id.id!=self.id):
            if not (self.date_from>=each.date_to or self.date_to<=each.date_from):
                check_availability = 1
                t_name = each.ticket_id.name
                e_df = each.date_from+timedelta(hours=6,minutes=30)
                e_dt = each.date_to+timedelta(hours=6,minutes=30)
                break
        if check_availability == 0:
            reserved_obj = driver_obj.reserved_time.filtered(lambda x: x.ticket_id.id==self.id)
            reserved_obj.sudo().write({
                    'date_from': self.date_from,
                    'date_to': self.date_to,
                })
            # reserved_id = self.name.reserved_time.create({'user': self.name.id,
            #                                                'date_from': self.date_from,
            #                                                'date_to': self.date_to,
            #                                                'ticket_id': self._context.get('active_id')
            #                                               })
        else:
            raise UserError('Sorry This driver is already assigned from %s to %s for %s.'%(e_df,e_dt,t_name))

        template = self._get_related_email_template(self.key_type, 'assign')
        self.env['mail.template'].browse(template.id).sudo().send_mail(self.id)

        template = self._get_related_email_template(self.key_type, 'assign_info')
        self.env['mail.template'].browse(template.id).sudo().send_mail(self.id)


class IsyTicketingRequestsDetails(models.Model):
    _name = 'isy.ticketing.requests.details'

    name = fields.Char(string="Description")
    qty = fields.Float(string="Qty", default=1)
    details_request_type = fields.Selection([('facility', 'Facility'), ('technology', 'Technology')], string="Request Type")
    ticket_id = fields.Many2one('isy.ticketing.requests', string="Ticket No.")


class IsyTechnicianNeeded(models.Model):
    _name = 'isy.technician.needed'

    name = fields.Char(string='Name')
    active = fields.Boolean(default=True)

class IsyBuildings(models.Model):
    _name = 'isy.building'
    _inherit = ['mail.thread', ]

    name = fields.Char(string="Building Name")
    isy_address = fields.Text(string="Address")
    isy_phone = fields.Char(string="Phone")
    isy_type = fields.Char(string="Type")
    isy_year_built = fields.Char(string="Year Built")
    isy_area = fields.Char(string="Area (Sq ft)")
    isy_no_of_units = fields.Char(string="Number of units")
    isy_emergency_info = fields.Text(string="Emergency Info")
    isy_additional_comments = fields.Text(string="Additional Comments")
    active = fields.Boolean(string="Active(?)", default=True)

class IsyResourcesLocationsReserved(models.Model):
    _name = "isy.resources.locations.reserved"
    _description = "Reserved Time Resources"
    _rec_name = 'reserved_obj'

    user = fields.Many2one('res.users', string='Users')
    date_from = fields.Datetime(string='From Inactive')
    date_to = fields.Datetime(string='To Inactive')
    date_from_toshow = fields.Datetime(string='Reserved Date From',compute='compute_date',store=True)
    date_to_toshow = fields.Datetime(string='Reserved Date To',compute='compute_date',store=True)
    reserved_obj = fields.Many2one('stock.location', string='Locations')
    request_id = fields.Many2one('isy.ticketing.requests')

    # @api.depends('date_from','date_to')
    # def compute_date(self):
    #     for rec in self:
    #         rec.date_from_toshow = rec.date_from-timedelta(hours=6, minutes=30)
    #         rec.date_to_toshow = rec.date_to-timedelta(hours=6, minutes=30)
    @api.depends('date_from', 'date_to')
    def compute_date(self):
        for rec in self:
            if rec.date_from:
                rec.date_from_toshow = rec.date_from - timedelta(hours=6, minutes=30)
            if rec.date_to:
                rec.date_to_toshow = rec.date_to - timedelta(hours=6, minutes=30)


class StockLocation(models.Model):
    _inherit = "stock.location"
    
    reserved_time = fields.One2many('isy.resources.locations.reserved', 'reserved_obj', String='Reserved Time', readonly=1,
                                                                    ondelete='cascade')
#only for old data 
'''
Do not use any more start
'''
class IsyResourcesLocations(models.Model):
    _name = 'isy.resources.locations'
    _inherit = 'mail.thread'

    name = fields.Char()
    is_location = fields.Boolean(string='Location(?)')
    address = fields.Text(string='Address')
    # buidling and its location
    building_id = fields.Many2one('isy.building', string="Building")
    # parent resource and its location
    isy_parent_resource_id = fields.Many2one(
            'isy.resources.locations', 'Parent Resources', index=True, ondelete='cascade',
            help="This is the parent resource where current resources comes from.")
    active = fields.Boolean(default=True)

    reserved_time = fields.One2many('isy.resources.locations.reserved', 'reserved_obj', String='Reserved Time', readonly=1,
                                                                    ondelete='cascade')

    @api.model
    def _name_search(self, name, args=None, operator='ilike', limit=100, name_get_uid=None):
        domain = args or []
        domain = expression.AND([domain, [('name', operator, name)]])
        rec = self._search(domain, limit=limit, access_rights_uid=name_get_uid)
        return rec

    def _validate_isy_parent_building(self, isy_parent_resource_id, building_id):
        if isy_parent_resource_id and building_id:
            parent_building_id = self.browse(
                    [isy_parent_resource_id]).building_id.id
            if parent_building_id != building_id:
                raise UserError(
                        _("Current Building and Parent Resources's Building must same!"))

    @api.model
    def create(self, values):
        self._validate_isy_parent_building(values.get('isy_parent_resource_id'), values.get('building_id'))
        res = super(IsyResourcesLocations, self).create(values)
        return res

    def write(self, values):
        self._validate_isy_parent_building(values.get('isy_parent_resource_id'), values.get('building_id'))
        res = super(IsyResourcesLocations, self).write(values)
        return res
'''
Do not use any more end
'''
class IsyRequestType(models.Model):
    _name = 'isy.request.type'

    name = fields.Char(string='Request Type')
    key_type = fields.Selection(
            KEY_SELECTION_TYPE, string='Master Requests Type', help='hidden field to control menu level')
    is_request = fields.Boolean(string='Enable Request Field(?)',
                                                            help='This will show request field in requestes form')
    # is_tech_setup = fields.Boolean(string='Enable Tech Setup Related Fields',
    # 							   help='To handle show/hide for start time, end time, technology equipment requested, technician needed, quantity.')
    active = fields.Boolean(default=True)
    default_request = fields.Boolean(default=False)

    @api.constrains('default_request')
    def _check_something(self):
        for record in self:
            if record.key_type not in ['maintenance', 'technology'] and record.default_request == True:
                raise ValidationError("Allow to check True only for maintenance request and technology request")
            count_check = record.search([('default_request', '=', True), ('key_type', '=', 'maintenance')])
            if not count_check:
                count_check = record.search([('default_request', '=', True), ('key_type', '=', 'technology')])
            if len(count_check) > 1:
                raise ValidationError("Please disable the old one first.Only allow for one key type per one default_request")


class Channel(models.Model):
    _inherit = 'discuss.channel'

    key_type = fields.Selection(KEY_SELECTION_TYPE, string='Master Requests Type', help='hidden field to control menu level')


class Message(models.Model):
    """ Messages model: system notification (replacing res.log notifications),
            comments (OpenChatter discussion) and incoming emails. """
    _inherit = 'mail.message'

    # @api.model
    # def _search(self, args, offset=0, limit=None, order=None, count=False, access_rights_uid=None):
    #     """ Override that adds specific access rights of mail.message, to remove
    #     ids uid could not see according to our custom rules. Please refer to
    #     check_access_rule for more details about those rules.

    #     Non employees users see only message with subtype (aka do not see
    #     internal logs).

    #     After having received ids of a classic search, keep only:
    #     - if author_id == pid, uid is the author, OR
    #     - uid belongs to a notified channel, OR
    #     - uid is in the specified recipients, OR
    #     - uid has a notification on the message
    #     - otherwise: remove the id
    #     """
    #     # Rules do not apply to administrator
    #     if self.env.is_superuser():
    #         return super(Message, self)._search(
    #             args, offset=offset, limit=limit, order=order,
    #             count=count, access_rights_uid=access_rights_uid)
    #     # Non-employee see only messages with a subtype and not internal
    #     """ #ISYers can see all messages
    #     if not self.env['res.users'].has_group('base.group_user'):
    #         args = expression.AND([self._get_search_domain_share(), args])
    #     """
    #     # Perform a super with count as False, to have the ids, not a counter
    #     ids = super(Message, self).sudo()._search(
    #         args, offset=offset, limit=limit, order=order,
    #         access_rights_uid=access_rights_uid)
    #     if not ids and count:
    #         return 0
    #     elif not ids:
    #         return ids

    @api.model
    def _search(self, args, offset=0, limit=None, order=None, count=False, access_rights_uid=None):
        """ Override that adds specific access rights of mail.message, to remove
        ids uid could not see according to our custom rules. Please refer to
        check_access_rule for more details about those rules.

        Non employees users see only message with subtype (aka do not see
        internal logs).

        After having received ids of a classic search, keep only:
        - if author_id == pid, uid is the author, OR
        - uid belongs to a notified channel, OR
        - uid is in the specified recipients, OR
        - uid has a notification on the message
        - otherwise: remove the id
        """
        # Rules do not apply to administrator
        if self.env.is_superuser():
            return super(Message, self)._search(
                args, offset=offset, limit=limit, order=order,
                access_rights_uid=access_rights_uid)

        # Perform a classic search
        query_result = super(Message, self).sudo()._search(
            args, offset=offset, limit=limit, order=order,
            access_rights_uid=access_rights_uid)

        # If 'count' is true, we only return the count of the records
        if count:
            return len(query_result)  # Return the count of records found

        return query_result  # Return the actual list of record IDs

        

        pid = self.env.user.partner_id.id
        author_ids, partner_ids, allowed_ids = set([]), set([]), set([])
        model_ids = {}

        # check read access rights before checking the actual rules on the given ids
        super(Message, self.with_user(access_rights_uid or self._uid)).check_access_rights('read')

        self.flush(['model', 'res_id', 'author_id', 'message_type', 'partner_ids'])
        self.env['mail.notification'].flush(['mail_message_id', 'res_partner_id'])
        for sub_ids in self._cr.split_for_in_conditions(ids):
            self._cr.execute("""
                SELECT DISTINCT m.id, m.model, m.res_id, m.author_id, m.message_type,
                                COALESCE(partner_rel.res_partner_id, needaction_rel.res_partner_id)
                FROM "%s" m
                LEFT JOIN "mail_message_res_partner_rel" partner_rel
                ON partner_rel.mail_message_id = m.id AND partner_rel.res_partner_id = %%(pid)s
                LEFT JOIN "mail_notification" needaction_rel
                ON needaction_rel.mail_message_id = m.id AND needaction_rel.res_partner_id = %%(pid)s
                WHERE m.id = ANY (%%(ids)s)""" % self._table, dict(pid=pid, ids=list(sub_ids)))
            for msg_id, rmod, rid, author_id, message_type, partner_id in self._cr.fetchall():
                if author_id == pid:
                    author_ids.add(msg_id)
                elif partner_id == pid:
                    partner_ids.add(msg_id)
                elif rmod and rid and message_type != 'user_notification':
                    model_ids.setdefault(rmod, {}).setdefault(rid, set()).add(msg_id)

        allowed_ids = self._find_allowed_doc_ids(model_ids)

        final_ids = author_ids | partner_ids | allowed_ids

        if count:
            return len(final_ids)
        else:
            # re-construct a list based on ids, because set did not keep the original order
            id_list = [id for id in ids if id in final_ids]
            return id_list
            

class FleetReservedTime(models.Model):
    _name = "fleet.reserved"
    _description = "Reserved Time"

    user = fields.Many2one('res.users', string='Users')
    date_from = fields.Datetime(string='Reserved Date From')
    date_to = fields.Datetime(string='Reserved Date To')
    reserved_obj = fields.Many2one('fleet.vehicle')


class DriverAllocateTime(models.Model):
    _name = "driver.allocation"

    user = fields.Many2one('res.users', string='Users')
    date_from = fields.Datetime(string='Reserved Date From')
    date_to = fields.Datetime(string='Reserved Date To')
    ticket_id = fields.Many2one('isy.ticketing.requests')

class FleetVehicleInherit(models.Model):
    _inherit = 'fleet.vehicle'

    check_availability = fields.Boolean(default=True, copy=False)
    reserved_time = fields.One2many('fleet.reserved', 'reserved_obj', String='Reserved Time', readonly=0,
                                                                    ondelete='cascade')

    @api.model
    def _name_search(self, name, args=None, operator='ilike', limit=100, name_get_uid=None,order=None):
        domain = args or []
        domain = expression.AND([domain, [('name', operator, name)]])
        rec = self._search(domain, limit=limit, access_rights_uid=name_get_uid, order=order)
        return rec

class ResUsers(models.Model):
    _inherit = "res.users"

    portal_maintenance_request = fields.Boolean(string='Portal Maintenance Requestor', copy=True, default=False)
    portal_technology_request = fields.Boolean(string='Portal Technology Requestor', copy=True, default=False)
    portal_transportation_request = fields.Boolean(string='Portal Transportation Requestor', copy=True, default=False)
    portal_schedule_request = fields.Boolean(string="Portal Schedule Requestor", copy=True, default=False)
    portal_audio_request = fields.Boolean(string="Portal Audio Requestor", copy=True, default=False)
    portal_maintenance_request_user = fields.Boolean(string='Portal Maintenance User', copy=True, default=False)
    portal_technology_request_user = fields.Boolean(string='Portal Technology User', copy=True, default=False)
    portal_transportation_request_user = fields.Boolean(string='Portal Transportation User', copy=True, default=False)
    portal_transportation_request_driver = fields.Boolean(string='Portal Transportation Driver', copy=True, default=False)
    portal_schedule_request_user = fields.Boolean(string="Portal Schedule User", copy=True, default=False)
    portal_audio_request_user = fields.Boolean(string="Portal Audio User", copy=True, default=False)
    check_availability = fields.Boolean(default=True, copy=False)
    reserved_time = fields.One2many('driver.allocation', 'user', String='Allocation Times', readonly=1,
                                                                    ondelete='cascade')


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    isy_ticketing_ref = fields.Char(string="ISY Ticketing Ref#", store=True, copy=False)
