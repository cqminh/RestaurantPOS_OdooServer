from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

class Table(models.Model):
    _name = "restaurant.table"
    _description = "Table of restaurant"

    name = fields.Char("Table Name", required=True, index=True)
    capacity = fields.Integer("Capacity")
    company_id = fields.Many2one('res.company', string='Company', required=True,
                                 default=lambda self: self.env.user.company_id)

    area_id = fields.Many2one("restaurant.area", string="Table Area", help="At which area the table is located.",
        domain="[('company_id', '=', company_id)]",)
    status = fields.Selection(
        [("available", "Available"), ("occupied", "Occupied"), ("maintained", "Maintained"), ("reserved", "Reserved")],
        "Status",
        default="available",
    )
    pos_id = fields.Many2one('restaurant.pos', string='Point of Sale', required=True,
                             domain="[('company_id', '=', company_id)]")

    def write(self, vals):
        return super(Table, self).write(vals)

    @api.constrains("capacity")
    def check_capacity(self):
        for table in self:
            if table.capacity <= 0:
                raise ValidationError(_("Room capacity must be more than 0"))
