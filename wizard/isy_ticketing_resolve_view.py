# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import requests
import logging
_logger = logging.getLogger(__name__)
from datetime import timedelta

class IsyDriverAllocation(models.TransientModel):
    _name = 'isy.driver.allocation'

    name = fields.Many2one('res.users', string='Choose Driver')
    date_from = fields.Datetime(string='From')
    date_to = fields.Datetime(string='To')

    def allocate_driver(self):
        driver_obj = self.name
        check_availability = 0
        for i in driver_obj:
            for each in i.reserved_time:
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
                    t_name = each.ticket_id.name
                    e_df = each.date_from+timedelta(hours=6,minutes=30)
                    e_dt = each.date_to+timedelta(hours=6,minutes=30)
                    break
        if check_availability == 0:
            reserved_id = self.name.reserved_time.create({'user': self.name.id,
                                                           'date_from': self.date_from,
                                                           'date_to': self.date_to,
                                                           'ticket_id': self._context.get('active_id')
                                                          })
        else:
            raise UserError('Sorry This driver is already assigned from %s to %s for %s.'%(e_df,e_dt,t_name))

    def apply_driver(self):
        if self.name:
            obj_isy_ticketing_requests = self.env['isy.ticketing.requests'].search([('id', '=', self._context.get('active_id'))])
            if obj_isy_ticketing_requests.driver_id:
                #need to add isy_ticket_request for driver allocation
                self.name.reserved_time.search([('ticket_id', '=', obj_isy_ticketing_requests.id)]).unlink()
                obj_isy_ticketing_requests.driver_id.sudo().check_availability = True
            obj_isy_ticketing_requests.write({'driver_id': self.name.id, 'is_driver_allocated': True})
            self.allocate_driver()
            template = obj_isy_ticketing_requests._get_related_email_template(obj_isy_ticketing_requests.key_type, 'assign')
            self.env['mail.template'].browse(template.id).sudo().send_mail(obj_isy_ticketing_requests.id)

            template = obj_isy_ticketing_requests._get_related_email_template(obj_isy_ticketing_requests.key_type, 'assign_info')
            self.env['mail.template'].browse(template.id).sudo().send_mail(obj_isy_ticketing_requests.id)
        else:
            raise UserError(_("Please choose driver."))


class IsyTicketingResolveWizard(models.TransientModel):
    _name = 'isy.ticketing.resolve.wizard'

    name = fields.Text(string="Resolution Description")

    def resolve_wizard(self):
        if self._context.get('state') == 'resolved':
            raise ValidationError(_("Already resolved by responsible person. Please refresh the page by pressing F5."))
        obj_isy_ticketing_requests = self.env['isy.ticketing.requests'].search([('id', '=', self._context.get('active_id'))])
        if obj_isy_ticketing_requests.key_type not in ('maintenance', 'transportation') and not self.env.user.id in self._context.get('user_ids'):
            if obj_isy_ticketing_requests.key_type == 'transportation' and not self.env.user.id == self._context.get('driver_id'):
                raise ValidationError(_("Only Driver must resolve!"))
            else:
                raise ValidationError(_("Only Assign Users must resolve!"))

        # maintenance request only for manager and assign users only
        elif not self.env.user.id in self._context.get('user_ids') and obj_isy_ticketing_requests.key_type == 'maintenance' and not self.env.user.has_group('isy_ticketing.group_mr_manager'):
            raise UserError(_("Only Assign Users must resolve!"))
        vals = {
                'state': 'resolved',
                'resolution_description': self.name,
                'resolve_user_id': self.env.user.id,
                'resolved_date': fields.Datetime.now()
        }
        obj_isy_ticketing_requests.write(vals)
        if obj_isy_ticketing_requests.key_type == "technology":
            #"https://api.trello.com/1/cards/%s"
            channel_id = self.env['discuss.channel'].search([('key_type', '=', obj_isy_ticketing_requests.key_type), ('trello_enable', '=', True)])
            if channel_id:
                lists_url = channel_id.trello_board_url  # "https://trello.com/1/boards/wo08IvOv/lists"
                key = channel_id.trello_key
                token = channel_id.trello_token
                params = {'key': key, 'token': token}
                response = requests.get(lists_url, params=params).json()
                idLists = []
                for res in response:
                    if res.get('name') == 'Done':
                        idLists.append(res.get('id'))
                #https://api.trello.com/1/cards/%s card update endpoint
                url = channel_id.trello_card_update_url % obj_isy_ticketing_requests.trello_id
                querystring = {"key": channel_id.trello_key, "token": channel_id.trello_token, "dueComplete": "true", "idList": idLists}
                response = requests.request("PUT", url, params=querystring)
                _logger.info("Move card to Done and Due Done................................")
        template = obj_isy_ticketing_requests._get_related_email_template(obj_isy_ticketing_requests.key_type, 'resolved')
        self.env['mail.template'].browse(template.id).send_mail(obj_isy_ticketing_requests.id)
