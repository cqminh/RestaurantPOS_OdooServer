from odoo import _, api, fields, models
from odoo.addons import decimal_precision as dp
from odoo.exceptions import UserError
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare, float_is_zero
from odoo.tests import Form


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    remarks = fields.Char("Note")

    @api.depends('taxes_id')
    def _compute_tax_list(self):
        for rec in self:
            rec.taxes_id = rec.product_id.product_tmpl_id.taxes_id

    #So luong dat va rang buoc lay lam tron bang voi lam tron cua Stock Weight
    qty_reserved = fields.Float(string="Quantity Done", default=0.0, digits=dp.get_precision('Stock Weight'),
                                store=True, compute_sudo=True)
    taxes_id = fields.Many2many("account.tax", string="Taxes", compute="_compute_tax_list")

    @api.model
    def create(self, vals):
        order = self.env['sale.order'].sudo().search([('id', '=', vals.get('order_id'))], limit=1)
        rec = self.env['sale.order.line']
        if order:
            if 'product_id' in vals:
                check_product = self.env["product.product"].sudo().search(
                    [("id", "=", vals.get('product_id'))])
                if check_product and check_product.product_tmpl_id.type != 'service':
                    cr = self.env.cr
                    get_infor_order = self.env["sale.order"].sudo().search(
                        [("id", "=", vals.get('order_id'))])
                    default_route = get_infor_order.pos_id.default_route_id.id
                    custom_route = get_infor_order.pos_id.custom_routes_id.ids
                    result = False
                    if custom_route:
                        product_product = self.env['product.product'].sudo().search(
                            [('id', '=', vals.get('product_id'))])
                        if product_product:
                            if product_product.product_tmpl_id:
                                cr.execute(
                                    "SELECT * FROM stock_route_product WHERE product_id = %s and route_id IN %s",
                                    (product_product.product_tmpl_id.id, tuple(custom_route)))
                                result = cr.fetchall()
                    if result:
                        vals["route_id"] = result[0][0]
                    else:
                        vals["route_id"] = default_route

            '''nếu qty_reserved > 0 thì để hàm write xử lý'''
            qty_reserved = False
            if 'qty_reserved' in vals:
                if vals.get('qty_reserved') > 0 and self.env['sale.order'].sudo().search(
                        [('id', '=', vals.get('order_id'))]).state in ['sale']:
                    qty_reserved = vals.get('qty_reserved')
                    vals['qty_reserved'] = 0
            rec = super(SaleOrderLine, self).create(vals)
            if qty_reserved:
                rec.qty_reserved = qty_reserved
        return rec

    def write(self, values):
        quantity_done_old = 0.0
        if self.order_id:
            quantity_done_old = self.qty_reserved
            if 'product_uom_qty' in values:
                if values.get('product_uom_qty') == 0:
                    values['discount'] = 0
        rec = super(SaleOrderLine, self).write(values)
        if 'qty_reserved' in values and self.state not in ['done', 'cancel']:
            '''qty_done nhỏ hơn product_uom_qty'''
            if 0 > values.get('qty_reserved') or values.get('qty_reserved') > self.product_uom_qty:
                raise UserError(_("SL Done lớn hơn 0 và nhỏ hơn SL đặt."))
            elif quantity_done_old > values.get('qty_reserved'):
                '''RETURN'''
                '''Xử lý của DELIVERY'''
                quantity_return = quantity_done_old - values.get('qty_reserved')
                pickings = self.env['stock.picking'].sudo().search(
                    [('sale_id', '=', self.order_id.id), ('state', 'in', ['done']),
                     ('origin', '=', self.order_id.name)])
                product_list = [{'product_id': self.product_id.id,
                                 'qty': quantity_return}]
                kit = False
                '''thao tác với SP kit'''
                mrp_bom = self.env['mrp.bom'].sudo().search(
                    ['|', ('product_id', '=', self.product_id.sudo().id), '&', ('product_id', '=', False),
                     ('product_tmpl_id', '=', self.product_id.sudo().product_tmpl_id.id)], limit=1)
                if mrp_bom:
                    if mrp_bom.type == 'phantom':
                        '''start'''
                        '''lấy công thức trên một đơn vị'''
                        if mrp_bom.sudo().bom_line_ids:
                            product_list = []
                            kit = True
                            for i in mrp_bom.sudo().bom_line_ids:
                                product_list.append({'product_id': i.product_id.id,
                                                     'qty': (i.product_qty / mrp_bom.sudo().product_qty) * quantity_return})
                ''''''
                created_picking_ids = []
                for product_id in product_list:
                    '''tạo và Done phiếu RETURN'''
                    if pickings:
                        for picking in pickings:
                            if product_id['qty'] == 0:
                                break
                            stock_move = self.env['stock.move'].sudo().search(
                                [('picking_id', '=', picking.id), ('sale_line_id', '=', self.id),
                                 ('product_id', '=', product_id['product_id'])], limit=1)
                            if stock_move:
                                new_return_picking = self.env['stock.return.picking'].sudo().with_context(
                                    active_ids=picking.ids, active_id=picking.id).create({
                                    'location_id': picking.location_id.id,
                                    'picking_id': picking.id,
                                })
                                new_return_picking._onchange_picking_id()
                                if new_return_picking.product_return_moves:
                                    temp = product_id['qty']
                                    for product_return in new_return_picking.product_return_moves:
                                        if temp > 0 and product_return.product_id.id == product_id[
                                            'product_id'] and product_return.move_id.id == stock_move.id:
                                            if product_return.quantity < temp:
                                                temp -= product_return.quantity
                                            else:
                                                product_return.quantity = temp
                                                temp = 0
                                        else:
                                            product_return.sudo().unlink()

                                new_picking, picking_type_id = new_return_picking._create_returns()
                                created_picking_ids.append(new_picking)
                                '''Write SL done cho phiếu RETURN'''
                                picking_rs = self.env['stock.picking'].sudo().search(
                                    [('state', 'not in', ['done', 'cancel']),
                                     ('id', '=', new_picking)
                                     ])
                                if picking_rs:
                                    for picking_r in picking_rs:
                                        if product_id['qty'] <= 0:
                                            break
                                        stock_moves_return = self.env['stock.move'].sudo().search(
                                            [('picking_id', '=', picking_r.id),
                                             ('sale_line_id', '=', self.id),
                                             ('product_id', '=', product_id['product_id'])])
                                        for stock_move in stock_moves_return:
                                            if product_id['qty'] <= 0:
                                                break
                                            stock_move_lines_return = self.env['stock.move.line'].sudo().search(
                                                [('move_id', '=', stock_move.id), ('picking_id', '=', picking_r.id),
                                                 ('product_id', '=', product_id['product_id'])])
                                            if not stock_move_lines_return:
                                                '''tạo STOCK MOVE LINE'''
                                                '''nếu không có picking_type_id.default_location_dest_id thì sẽ lấy id=9'''
                                                if picking_r.picking_type_id and picking_r.location_id:
                                                    location_dest_id = picking_r.location_id
                                                    if picking_r.picking_type_id.sudo().default_location_dest_id:
                                                        location_id = \
                                                            picking_r.picking_type_id.sudo().default_location_dest_id.id
                                                    else:
                                                        location_id = 9
                                                    if product_id['qty'] >= stock_move.product_uom_qty:
                                                        done = stock_move.product_uom_qty
                                                    else:
                                                        done = product_id['qty']
                                                    product_id['qty'] -= done
                                                    self.env['stock.move.line'].sudo().create(
                                                        [{
                                                            'picking_id': picking_r.id,
                                                            'product_id': product_id['product_id'],
                                                            'location_id': location_id.id,
                                                            'location_dest_id': location_dest_id,
                                                            'description_picking': '',
                                                            'qty_done': done,
                                                            'product_uom_id': stock_move.product_uom.id,
                                                            'state': 'confirmed',
                                                            'move_id': stock_move.id,
                                                        }]
                                                    )
                                            else:
                                                for stock_move_line_r in stock_move_lines_return:
                                                    if product_id['qty'] <= 0:
                                                        break
                                                    qty_r = stock_move_line_r.reserved_uom_qty - stock_move_line_r.qty_done
                                                    if product_id['qty'] > qty_r:
                                                        stock_move_line_r.qty_done += qty_r
                                                        product_id['qty'] -= qty_r
                                                    else:
                                                        stock_move_line_r.qty_done += product_id['qty']
                                                        product_id['qty'] = 0

                    '''xử lý của lệnh SX'''
                    '''lấy DS mrp.production theo origin, product_id'''
                    mrp_productions = self.env['mrp.production'].sudo().search(
                        [('origin', '=', self.order_id.sudo().name), ('product_id', '=', product_id['product_id']),
                         ('state', 'in', ['done'])])

                    if mrp_productions:
                        for mrp_pro in mrp_productions:
                            if mrp_pro.unbuild_count != 0:
                                continue
                            action = mrp_pro.button_unbuild()
                            wizard = Form(self.env[action['res_model']].with_context(action['context'])).save()
                            wizard.action_unbuild()
                    #         '''lấy công thức và tính theo SL RETURN'''
                    #         product_list_sx = []
                    #         if mrp_pro.bom_id:
                    #             bom_id = mrp_pro.bom_id
                    #             if bom_id.sudo().bom_line_ids:
                    #                 '''tính ra SL trên một đơn vị'''
                    #                 for i in bom_id.sudo().bom_line_ids:
                    #                     product_list_sx.append({'product_id': i.product_id.id,
                    #                                             'qty': (i.product_qty / bom_id.sudo().product_qty)})
                    #         if product_list_sx:
                    #             if mrp_pro.finished_move_line_ids and mrp_pro.move_raw_ids:
                    #                 '''call action unlock'''
                    #                 # mrp_pro.action_toggle_is_locked()
                    #                 '''RETURN SL SP giao'''
                    #                 qty_return = product_id['qty']
                    #                 for finished in mrp_pro.finished_move_line_ids:
                    #                     '''có thể RETURN'''
                    #                     if qty_return <= 0:
                    #                         qty_return = 0
                    #                         break
                    #                     if finished.qty_done > 0:
                    #                         if finished.qty_done > qty_return:
                    #                             finished.qty_done -= qty_return
                    #                             qty_return = 0
                    #                         else:
                    #                             qty_return -= finished.qty_done
                    #                             finished.qty_done = 0
                    #
                    #                 '''RETURN nguyên vật liệu'''
                    #                 '''Trừ đi SL RETURN dư'''
                    #                 qty_return_nvl = product_id['qty'] - qty_return
                    #                 '''Tinh NVL theo SL trên qty_return_nvl đơn vị'''
                    #                 for i in product_list_sx:
                    #                     i['qty'] = i.get('qty') * qty_return_nvl
                    #                 for return_nvl in mrp_pro.move_raw_ids:
                    #                     if return_nvl.quantity_done > 0 and return_nvl.active_move_line_ids:
                    #                         for i in product_list_sx:
                    #                             if return_nvl.product_id.id == i.get('product_id') and i['qty'] > 0:
                    #                                 for line_ids in return_nvl.active_move_line_ids:
                    #                                     if i['qty'] <= 0:
                    #                                         break
                    #                                     if i.get('qty') > line_ids.qty_done:
                    #                                         i['qty'] -= line_ids.qty_done
                    #                                         line_ids.qty_done = 0
                    #                                     else:
                    #                                         line_ids.qty_done -= i.get('qty')
                    #                                         i['qty'] = 0
                    #                                 break
                    #                 # mrp_pro.action_toggle_is_locked()
                    #                 product_id['qty'] = qty_return

                '''sẽ validate những PS kit'''
                if kit and created_picking_ids:
                    picking_ids = self.env['stock.picking'].sudo().search(
                        [('state', 'not in', ['done', 'cancel']), ('id', 'in', created_picking_ids)])
                    if picking_ids:
                        for picking in picking_ids:
                            for i in picking.move_ids_without_package:
                                if i.quantity_done > 0:
                                    picking.validate_return_for_restaurant()
                                    break

            elif quantity_done_old < values.get('qty_reserved'):
                '''DONE'''
                qty_done = values.get('qty_reserved') - quantity_done_old
                stock_pickings = self.env['stock.picking'].sudo().search(
                    [('sale_id', '=', self.order_id.id), ('state', 'not in', ['done', 'cancel'])])
                if stock_pickings:
                    product_list = [{'product_id': self.product_id.id,
                                     'qty': qty_done}]
                    kit = False
                    '''thao tác với SP kit'''
                    mrp_bom = self.env['mrp.bom'].sudo().search(
                        ['|', ('product_id', '=', self.product_id.sudo().id), '&', ('product_id', '=', False),
                         ('product_tmpl_id', '=', self.product_id.sudo().product_tmpl_id.id)], limit=1)
                    if mrp_bom:
                        if mrp_bom.type == 'phantom':
                            '''start'''
                            '''lấy công thức trên một đơn vị'''
                            if mrp_bom.sudo().bom_line_ids:
                                product_list = []
                                kit = True
                                for i in mrp_bom.sudo().bom_line_ids:
                                    product_list.append({'product_id': i.product_id.id,
                                                         'qty': (
                                                                        i.product_qty / mrp_bom.sudo().product_qty) * qty_done})
                    for product_id in product_list:
                        for stock_picking in stock_pickings:
                            if product_id['qty'] == 0:
                                break
                            stock_moves = self.env['stock.move'].sudo().search(
                                [('picking_id', '=', stock_picking.id), ('sale_line_id', '=', self.id),
                                 ('product_id', '=', product_id['product_id'])])
                            production_id = False
                            if stock_moves:
                                for stock_move in stock_moves:
                                    if product_id['qty'] == 0:
                                        break
                                    '''lấy cho lệnh SX'''
                                    if stock_move.created_production_id and not production_id:
                                        production_id = stock_move.sudo().created_production_id
                                    ''''''
                                    stock_move_lines = self.env['stock.move.line'].sudo().search(
                                        [('move_id', '=', stock_move.id), ('picking_id', '=', stock_picking.id),
                                         ('product_id', '=', product_id['product_id'])])
                                    if not stock_move_lines:
                                        '''tạo STOCK MOVE LINE'''
                                        '''nếu không có picking_type_id.default_location_dest_id thì sẽ lấy id=9'''
                                        if stock_picking.picking_type_id and stock_picking.location_id:
                                            location_id = stock_picking.location_id
                                            if stock_picking.picking_type_id.sudo().default_location_dest_id:
                                                location_dest_id = \
                                                    stock_picking.picking_type_id.sudo().default_location_dest_id.id
                                            else:
                                                location_dest_id = 9
                                            stock_move_lines = self.env['stock.move.line'].sudo().create(
                                                [{
                                                    'picking_id': stock_picking.id,
                                                    'product_id': product_id['product_id'],
                                                    'location_id': location_id.id,
                                                    'location_dest_id': location_dest_id,
                                                    'description_picking': '',
                                                    'qty_done': 0.0,
                                                    'product_uom_id': stock_move.product_uom.id,
                                                    'state': 'confirmed',
                                                    'move_id': stock_move.id,
                                                }]
                                            )
                                    if stock_move_lines:
                                        length = 0
                                        for stock_move_line in stock_move_lines:
                                            length += 1
                                            if product_id['qty'] <= 0:
                                                break
                                            else:
                                                '''nếu stock_move_line.product_uom_qty = 0 thì vẫn tiếp tục done'''
                                                if length == len(stock_move_lines):
                                                    qty_tang = product_id['qty']
                                                else:
                                                    qty_tang = (
                                                            stock_move_line.product_uom_qty - stock_move_line.qty_done) \
                                                        if stock_move_lines.product_uom_qty > 0 else product_id['qty']
                                                if product_id['qty'] >= qty_tang:
                                                    stock_move_line.qty_done += qty_tang
                                                    sx = True
                                                    product_id['qty'] -= qty_tang
                                                else:
                                                    stock_move_line.qty_done += product_id['qty']
                                                    sx = True
                                                    product_id['qty'] = 0
                                                ''' Bắt đầu cho SX và not tồn kho '''
                                                if sx and production_id:
                                                    '''chú ý CHÚ Ý'''
                                                    update_quantity_wizard = self.env['change.production.qty'].create({
                                                        'mo_id': production_id.id,
                                                        'product_qty': production_id.product_qty,
                                                        # 'product_qty': stock_move_line.qty_done + production_id.product_qty,
                                                    })
                                                    update_quantity_wizard.change_prod_qty()

                                                    # mrp_product_produce = self.env[
                                                    #     'mrp.product.produce'].sudo().with_context(
                                                    #     active_id=production_id.id).sudo().create(
                                                    #     {'production_id': production_id.id,
                                                    #      'product_id': product_id['product_id'],
                                                    #      'product_qty': stock_move_line.qty_done})
                                                    # mrp_product_produce._onchange_product_qty()
                                                    # mrp_product_produce.do_produce()
                                                    # production_id._post_inventory()

                                                    res_dict = production_id.button_mark_done()
                                                    # self.assertEqual(res_dict.get('res_model'),
                                                    #                  'mrp.immediate.production')
                                                    wizard = Form(self.env[res_dict['res_model']].with_context(
                                                        res_dict['context'])).save()
                                                    wizard.process()

                                                    '''chú ý CHÚ Ý'''
                                                    stock_move_update = self.env['stock.move'].sudo().search(
                                                        [('raw_material_production_id', '=', production_id.id),
                                                         ('state', 'not in', ['done', 'cancel'])])
                                                    for i in stock_move_update:
                                                        move_line = self.env['stock.move.line'].sudo().search(
                                                            [('move_id', '=', i.id),
                                                             ('state', 'not in', ['done', 'cancel'])])
                                                        for line_ in move_line:
                                                            if line_.reserved_uom_qty < 0:
                                                                line_.reserved_uom_qty = 0

                    '''sẽ validate những SP kit'''
                    if kit:
                        picking_ids = self.env['stock.picking'].sudo().search(
                            [('state', 'not in', ['done', 'cancel']), ('sale_id', '=', self.order_id.id),
                             ('origin', '=', self.order_id.sudo().name)])
                        if picking_ids:
                            for picking in picking_ids:
                                for i in picking.move_ids_without_package:
                                    if i.quantity_done > 0:
                                        picking.validate_return_for_restaurant()
                                        break
        return rec

    class Picking(models.Model):
        _inherit = "stock.picking"

        def validate_for_restaurant(self):
            self.button_validate()
            # self.ensure_one()
            # if not self.move_lines and not self.move_line_ids:
            #     raise UserError(_('Please add some items to move.'))
            #
            # # If no lots when needed, raise error
            # picking_type = self.picking_type_id
            # precision_digits = self.env['decimal.precision'].precision_get('Product Unit of Measure')
            # no_quantities_done = all(
            #     float_is_zero(move_line.qty_done, precision_digits=precision_digits) for move_line in
            #     self.move_line_ids.filtered(lambda m: m.state not in ('done', 'cancel')))
            # no_reserved_quantities = all(
            #     float_is_zero(move_line.reserved_qty, precision_rounding=move_line.product_uom_id.rounding) for move_line
            #     in
            #     self.move_line_ids)
            # if no_reserved_quantities and no_quantities_done:
            #     raise UserError(
            #         _('You cannot validate a transfer if no quantites are reserved nor done. To force the transfer, switch in edit more and encode the done quantities.'))
            #
            # if picking_type.use_create_lots or picking_type.use_existing_lots:
            #     lines_to_check = self.move_line_ids
            #     if not no_quantities_done:
            #         lines_to_check = lines_to_check.filtered(
            #             lambda line: float_compare(line.qty_done, 0,
            #                                        precision_rounding=line.product_uom_id.rounding)
            #         )
            #
            #     for line in lines_to_check:
            #         product = line.product_id
            #         if product and product.tracking != 'none':
            #             if not line.lot_name and not line.lot_id:
            #                 raise UserError(
            #                     _('You need to supply a Lot/Serial number for product %s.') % product.display_name)
            #
            # # Check backorder should check for other barcodes
            # if self._check_backorder():
            #     new = self.env['stock.backorder.confirmation'].sudo().create({'pick_ids': [(6, 0, [self.id])]})
            #     new.process()
            #     return
            # self.action_done()
            # return

        def validate_return_for_restaurant(self):
            self.button_validate()
            # self.ensure_one()
            # if not self.move_lines and not self.move_line_ids:
            #     raise UserError(_('Please add some items to move.'))
            #
            # # If no lots when needed, raise error
            # picking_type = self.picking_type_id
            # precision_digits = self.env['decimal.precision'].precision_get('Product Unit of Measure')
            # no_quantities_done = all(
            #     float_is_zero(move_line.qty_done, precision_digits=precision_digits) for move_line in
            #     self.move_line_ids.filtered(lambda m: m.state not in ('done', 'cancel')))
            # no_reserved_quantities = all(
            #     float_is_zero(move_line.product_qty, precision_rounding=move_line.product_uom_id.rounding) for move_line
            #     in
            #     self.move_line_ids)
            # if no_reserved_quantities and no_quantities_done:
            #     raise UserError(
            #         _('You cannot validate a transfer if no quantites are reserved nor done. To force the transfer, switch in edit more and encode the done quantities.'))
            #
            # if picking_type.use_create_lots or picking_type.use_existing_lots:
            #     lines_to_check = self.move_line_ids
            #     if not no_quantities_done:
            #         lines_to_check = lines_to_check.filtered(
            #             lambda line: float_compare(line.qty_done, 0,
            #                                        precision_rounding=line.product_uom_id.rounding)
            #         )
            #
            #     for line in lines_to_check:
            #         product = line.product_id
            #         if product and product.tracking != 'none':
            #             if not line.lot_name and not line.lot_id:
            #                 raise UserError(
            #                     _('You need to supply a Lot/Serial number for product %s.') % product.display_name)
            #
            # # Check backorder should check for other barcodes
            # if self._check_backorder():
            #     new = self.env['stock.backorder.confirmation'].sudo().create({'pick_ids': [(6, 0, [self.id])]})
            #     new.process_cancel_backorder()
            #     return
            # self.action_done()
            # return