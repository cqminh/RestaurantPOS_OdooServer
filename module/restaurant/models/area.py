from odoo import fields, models

class Area(models.Model):
    _name = "restaurant.area"
    _description = "Restaurant Area"

    name = fields.Char("Name", required=True, index=True)
    company_id = fields.Many2one('res.company', string='Company', required=True,
                                 default=lambda self: self.env.user.company_id)

    pos_ids = fields.Many2many('restaurant.pos', string='Point of Sale')
    table_ids = fields.One2many('restaurant.table', 'area_id', string='Tables')