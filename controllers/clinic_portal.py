# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from collections import OrderedDict

from odoo import http, _
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
from odoo.exceptions import AccessError, MissingError
from odoo.http import request
from odoo.osv.expression import OR

class CustomerPortal(CustomerPortal):

    def _prepare_portal_layout_values(self):
        values = super(CustomerPortal, self)._prepare_portal_layout_values()
        domain = ['|', ('assign_person_id.assign_person_email', '=', request.env.user.login), '|', ('first_approver_id.work_email', '=', request.env.user.login), '|', ('second_approver_id.work_email', '=', request.env.user.login), '&', ('create_uid', '=', request.env.user.id), ('message_partner_ids', 'in', [request.env.user.partner_id.id])]
        clinic_requests_count = request.env['isy.clinic.request'].search_count(domain)
        values['clinic_requests_count'] = clinic_requests_count
        return values

    @http.route(['/my/clinic_requests', '/my/clinic_requests/page/<int:page>'], type='http', auth="user", website=True)
    def portal_clinic_requests(self, page=1, sortby=None, filterby=None, search=None, search_in='all', **kw):
        domain = []
        values = self._prepare_portal_layout_values()
        ISYTClinicRequest = request.env['isy.clinic.request']

        #domain needo to modify for create user records only.

        searchbar_filters = {
            'all': {'label': _('All Status'), 'domain': []},
            'state_request_for_confirmation': {'label': _('Waiting For Confirmation'), 'domain': [('state', '=', 'request_for_confirmation')]},
            'state_request_for_approval': {'label': _('Waiting for Approval'), 'domain': [('state', '=', 'request_for_approval')]},
            'state_approved': {'label': _('Approved'), 'domain': [('state', '=', 'approved')]},
            'state_rejected': {'label': _('Rejected'), 'domain': [('state', '=', 'rejected')]},
            'state_done': {'label': _('Done'), 'domain': [('state', '=', 'done')]},
            }

        searchbar_sortings = {
            'request_date': {'label': _('Request Date'), 'order': 'create_date desc'},
            'name': {'label': _('Reference'), 'order': 'name desc'},
            'state': {'label': _('Status'), 'order': 'state'},
        }

        searchbar_inputs = {
            'subject': {'input': 'subject', 'label': _('Search <span class="nolabel"> (in Email Subject)</span>')},
            'name': {'input': 'name', 'label': _('Search in Ref #')},
            'all': {'input': 'all', 'label': _('Search in All')},
        }
        domain += ['|', ('assign_person_id.assign_person_email', '=', request.env.user.login), '|', ('first_approver_id.work_email', '=', request.env.user.login), '|', ('second_approver_id.work_email', '=', request.env.user.login), '&', ('create_uid', '=', request.env.user.id), ('message_partner_ids', 'in', [request.env.user.partner_id.id])]
        # default sort by order
        if not sortby:
            sortby = 'name'
        order = searchbar_sortings[sortby]['order']
        # default filter by value
        if not filterby:
            filterby = 'all'
        domain += searchbar_filters[filterby]['domain']

        # search
        if search and search_in:
            search_domain = []
            if search_in in ('subject', 'all'):
                search_domain = OR([search_domain, [('subject', 'ilike', search)]])
            if search_in in ('name', 'all'):
                search_domain = OR([search_domain, [('name', 'ilike', search)]])
            domain += search_domain

        # count for pager
        clinic_requests_count = ISYTClinicRequest.sudo().search_count(domain)
        # pager

        pager = portal_pager(
            url="/my/clinic_requests",
            url_args={'sortby': sortby},
            total=clinic_requests_count,
            page=page,
            step=self._items_per_page
        )
        # content according to pager and archive selected
        clinic_requests = ISYTClinicRequest.sudo().search(
            domain, order=order, limit=self._items_per_page, offset=pager['offset'])
        request.session['my_clinic _requests_history'] = clinic_requests.ids[:100]

        values.update({
            'clinic_requests': clinic_requests,
            'page_name': 'clinic_request',
            'pager': pager,
            'default_url': '/my/clinic_requests',
            'searchbar_inputs': searchbar_inputs,
            'search_in': search_in,
            'searchbar_sortings': searchbar_sortings,
            'sortby': sortby,
            'searchbar_filters': OrderedDict(sorted(searchbar_filters.items())),
            'filterby': filterby
        })
        return request.render("isy_ticketing.portal_my_clinic_requests", values)
