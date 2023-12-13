from odoo import models, fields, api

class RestaurantBranch(models.Model):
    _name = "restaurant.branch"
    _description = "Restaurant Branch"

    def _default_pricelist(self):
        return self.env['product.pricelist'].search([('company_id', 'in', (False, self.env.user.company_id.id)),
                                                     ('currency_id', '=', self.env.user.company_id.currency_id.id)],
                                                    limit=1)

    name = fields.Char("Name", required=1)
    company_id = fields.Many2one('res.company', string='Company', required=True,
                                 default=lambda self: self.env.user.company_id)
    phone = fields.Char('Phone number', help='Contact telephone Number', required=True)
    address = fields.Char('Address', help='Contact address', required=True)
    period = fields.Float(string="Period")

    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse')

    ''' Users '''
    user_id = fields.Many2one('res.users', 'Manager User', required=1,
                              domain=lambda self: [("company_id", "in", self.env.user.company_ids.ids)])
    user_ids = fields.Many2many('res.users', 'restaurant_branch_user_rel', 'branch_id', 'user_id',
                                string="POS Users",
                                domain=lambda self: [("company_id", "in", self.env.user.company_ids.ids)])

    pos_ids = fields.One2many('restaurant.pos', 'branch_id', string="Point Of Sale")

    ''' Price '''
    tax_included = fields.Selection([('subtotal', 'Tax-Excluded Price'), ('total', 'Tax-Included Price')],
                                   string="Tax Display", default='subtotal', required=True)
    available_pricelist_ids = fields.Many2many('product.pricelist', string='Available Pricelists', default=_default_pricelist)

    ''' Accounting '''
    payment_journal_ids = fields.Many2many('account.journal', string='Payment journals', required=True)
    # payment_journal_ids = fields.Many2many('account.journal', string='Payment journals', required=True,
    #                                        domain=[('journal_user', '=', True),
    #                                                ('pos_method_type', '=', 'default')])
    invoice_journal_id = fields.Many2one("account.journal", string="Accounting invoice journal",
                                         domain=lambda self: [("company_id", "=", self.env.user.company_id.id)],
                                         required=True)
    done_invisible = fields.Boolean("Hide done")

    datetime_now = fields.Datetime(string='Date To', compute='time_now')

    def time_now(self):
        for rec in self:
            rec.datetime_now = fields.Datetime.now()
