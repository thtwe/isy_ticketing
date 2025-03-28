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
        domain = [('key_type', '=', 'maintenance'), '|', ('create_uid', '=', request.env.user.id), ('message_partner_ids', 'in', [request.env.user.partner_id.id])]
        maintenance_requests_count = request.env['isy.ticketing.requests'].search_count(domain)
        values['maintenance_requests_count'] = maintenance_requests_count
        return values

    @http.route(['/my/maintenance_requests', '/my/maintenance_requests/page/<int:page>'], type='http', auth="user", website=True)
    def portal_maintenance_requests(self, page=1, sortby=None, filterby=None, search=None, search_in='all', **kw):
        domain = []
        values = self._prepare_portal_layout_values()
        IsyTicketingRequests = request.env['isy.ticketing.requests']

        #domain needo to modify for create user records only.

        searchbar_filters = {
            'all': {'label': _('All Status'), 'domain': []},
            'state_waitingforapproval': {'label': _('Waiting For Approval'), 'domain': [('state', '=', 'waitingforapproval')]},
            'state_pendingresolution': {'label': _('Pending Resolution'), 'domain': [('state', '=', 'pendingresolution')]},
            'state_resolved': {'label': _('Resolved'), 'domain': [('state', '=', 'resolved')]},
            }

        searchbar_sortings = {
            'due_date': {'label': _('Due Date'), 'order': 'due_date desc'},
            'name': {'label': _('Reference'), 'order': 'name desc'},
            'state': {'label': _('Status'), 'order': 'state'},
        }

        searchbar_inputs = {
            'building_id': {'input': 'building_id', 'label': _('Search <span class="nolabel"> (in Building)</span>')},
            'name': {'input': 'name', 'label': _('Search in Ref #')},
            'due_date': {'input': 'due_date', 'label': _('Search in Due Date')},
            'request_type_id': {'input': 'request_type_id', 'label': _('Search in Request Type')},
            'all': {'input': 'all', 'label': _('Search in All')},
        }
        domain += [('key_type', '=', 'maintenance'), '|', ('create_uid', '=', request.env.user.id),  ('message_partner_ids', 'in', [request.env.user.partner_id.id])]
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
            if search_in in ('building_id', 'all'):
                search_domain = OR([search_domain, [('building_id', 'ilike', search)]])
            if search_in in ('name', 'all'):
                search_domain = OR([search_domain, [('name', 'ilike', search)]])
            if search_in in ('due_date', 'all'):
                search_domain = OR([search_domain, [('due_date', 'ilike', search)]])
            if search_in in ('request_type_id', 'all'):
                search_domain = OR([search_domain, [('request_type_id', 'ilike', search)]])
            domain += search_domain

        # count for pager
        maintenance_requests_count = IsyTicketingRequests.sudo().search_count(domain)
        # pager

        pager = portal_pager(
            url="/my/maintenance_requests",
            url_args={'sortby': sortby},
            total=maintenance_requests_count,
            page=page,
            step=self._items_per_page
        )
        # content according to pager and archive selected
        maintenance_requests = IsyTicketingRequests.sudo().search(
            domain, order=order, limit=self._items_per_page, offset=pager['offset'])
        request.session['my_maintenance_requests_history'] = maintenance_requests.ids[:100]

        values.update({
            'maintenance_requests': maintenance_requests,
            'page_name': 'maintenance_request',
            'pager': pager,
            'default_url': '/my/maintenance_requests',
            'searchbar_inputs': searchbar_inputs,
            'search_in': search_in,
            'searchbar_sortings': searchbar_sortings,
            'sortby': sortby,
            'searchbar_filters': OrderedDict(sorted(searchbar_filters.items())),
            'filterby': filterby
        })
        return request.render("isy_ticketing.portal_my_maintenance_requests", values)
