from odoo import _, api, fields, models

class RestaurantPOS(models.Model):
    _name = "restaurant.pos"
    _description = "Restaurant POS"

    def _default_pricelist(self):
        return self.env['product.pricelist'].search([('company_id', 'in', (False, self.env.user.company_id.id)),
                                                     ('currency_id', '=', self.env.user.company_id.currency_id.id)],
                                                    limit=1)

    name = fields.Char('POS Name', required=True, index=True, help='An internal identification of the point of sale.')
    company_id = fields.Many2one('res.company', string="Company", required=True,
                                 default=lambda self: self.env.user.company_id)
    branch_id = fields.Many2one("restaurant.branch", string="Branch", required=True,
                                domain="[('company_id', '=', company_id)]")

    ''' POS users '''
    #POS user la cac nhan vien phuc vu tren POS, them domain theo cong ty cho user
    user_ids = fields.Many2many('res.users', string="POS's Users",
                                domain=lambda self: [("company_id", "=", self.env.user.company_id.id)])

    ''' Category '''
    limit_categories = fields.Boolean("Restrict Available Product Categories")
    available_cat_ids = fields.Many2many('pos.category', string='Available PoS Product Categories',
                                                 help='The point of sale will only display products \n'
                                                      'which are within one of the selected category trees. \n'
                                                      'If no category is specified, all available'
                                                      'products will be shown')
                                                 # domain=lambda self: [("company_id", "=", self.env.user.company_id.id)])
    # qty_available_product = fields.Boolean("Show quanity available product", default=False)

    ''' Pricing '''
    tax_included = fields.Selection([('subtotal', 'Tax-Excluded Price'), ('total', 'Tax-Included Price')],
                                          string="Display sale price within tax (Maintained)", default='subtotal',
                                          required=True)
    # Cac price_list se duoc xuat hien trong POS
    available_pricelist_ids = fields.Many2many('product.pricelist', string='Available Price Lists',
                                               default=_default_pricelist)
    available_pricelist_id = fields.Many2one('product.pricelist', string='Default Price List',
                                             default=_default_pricelist)

    ''' Inventory '''
    picking_type_id = fields.Many2one("stock.picking.type", string="Operation Type",
                                      domain="[('warehouse_id', '=', False)]")
    pos_location_id = fields.Many2one("stock.location", string="Default POS location",
                                      domain=lambda self: [("company_id", "=", self.env.user.company_id.id),
                                                           ("usage", "=", "internal")])
    default_route_id = fields.Many2one("stock.route", string="Default route")
    custom_routes_id = fields.Many2many('stock.route', string='Custom routes')
    allow_out_of_stock = fields.Boolean("Allow out of stock", default=True)

    ''' Accounting '''
    # Day la tat ca journal cua POS domain theo cong ty, con 2 truong kia neu can thi them vao module account.journal
    payment_journal_ids = fields.Many2many('account.journal', string='Payment journals',
                                           domain=lambda self: [('company_id', '=', self.env.user.company_id.id)])
    # payment_journal_ids = fields.Many2many('account.journal', string='Payment journals',
    #                                        domain=[('journal_user', '=', True),
    #                                                ('pos_method_type', '=', 'default')])
    invoice_journal_id = fields.Many2one("account.journal", string="Accounting invoice journal",
                                         domain=lambda self: [("company_id", "=", self.env.user.company_id.id)])

    ''' Order '''
    customer_default_id = fields.Many2one("res.partner", string='Customer default', required=True)

    @api.onchange('branch_id')
    def _onchange_picking_type(self):
        if self.branch_id.warehouse_id:
            res = {'domain': {
                'picking_type_id': [('warehouse_id', '=', self.branch_id.warehouse_id.id)]}}
            return res

    def action_open_restaurant_order_view(self):
        restaurant_order_tree_view = self.env.ref('restaurant.restaurant_order_tree_view')
        restaurant_order_form_view = self.env.ref('restaurant.restaurant_order_form_view')
        return {
            'name': _(self.name),
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'sale.order',
            'views': [(restaurant_order_tree_view.id, 'tree'), (restaurant_order_form_view.id, 'form')],
            'view_id': False,
            'type': 'ir.actions.act_window',
            'domain': [('pos_id', '=', self.id)],
            'context': {'search_default_order_sale': 1,
                        'default_pos_id': self.id,
                        'default_warehouse_id': self.branch_id.warehouse_id.id,
                        'default_partner_id': self.customer_default_id.id},
            'target': 'current',
        }