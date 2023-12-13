from datetime import datetime, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
from odoo.tests import Form


class SaleOrder(models.Model):
    _inherit = "sale.order"

    pos_id = fields.Many2one("restaurant.pos", "Point of Sale")

    table_id = fields.Many2one("restaurant.table", "Table Restaurant",
                               domain="[('company_id', '=', company_id), ('status', '=', 'available'),"
                                      "('pos_id', '=', pos_id)]")

    check_in = fields.Datetime(string='Check In',
                               default=datetime(datetime.now().year, datetime.now().month, datetime.now().day, 12, 0,
                                                0))
    # check_out = fields.Datetime(string='Check Out',
    #                             default=datetime(datetime.now().year, datetime.now().month, datetime.now().day, 14,
    #                                              0, 0))

    check_out = fields.Datetime(string='Check Out', default=lambda self: self._get_default_check_out())

    def _get_default_check_out(self):
        current_datetime = datetime.now()
        next_day_datetime = current_datetime + timedelta(days=1)

        # Thiết lập giờ, phút và giây là 14:00:00
        check_out_datetime = next_day_datetime.replace(hour=14, minute=0, second=0, microsecond=0)

        return check_out_datetime
    ''' Lấy data khách hàng default từ POS khi tạo đơn hàng '''
    partner_id_hr = fields.Many2one('res.partner', string='Partner Hotel Restaurant',
                                    default=lambda self: self.env['restaurant.pos'].browse(
                                        self._context.get('active_id')).customer_default_id.id)

    # Do partner_id la khong doi duoc nen phai tao them mot truong partner de co the thay doi user
    @api.onchange('partner_id_hr')
    def onchange_partner_id_hr(self):
        self.partner_id = self.partner_id_hr
        # self.onchange_partner_id()

    @api.constrains('partner_id_hr')
    def constraint_partner_id_hr(self):
        if self.partner_id_hr:
            listprice_id_old = self.pricelist_id.id
            self.partner_id = self.partner_id_hr
            # self.onchange_partner_id()
            if self.pricelist_id.id != listprice_id_old:
                self.pricelist_id = listprice_id_old

    '''lấy price list default của POS đó dùng riêng cho restaurant'''
    @api.constrains('pricelist_id')
    def constrains_pricelist_id(self):
        for rec in self:
            if rec.pos_id:
                if rec.pos_id.sudo().available_pricelist_id:
                    if rec.pricelist_id.id != rec.pos_id.sudo().available_pricelist_id.id:
                        rec.pricelist_id = rec.pos_id.sudo().available_pricelist_id.id

    def get_checkin_date(self):
        if "checkin" in self._context:
            return self._context["checkin"]
        else:
            now = datetime.now()
            checkin_date = datetime(now.year, now.month, now.day, 5, 0, 0)
            return checkin_date.strftime(DEFAULT_SERVER_DATETIME_FORMAT)

    def get_checkout_date(self):
        if "checkout" in self._context:
            return self._context["checkout"]
        else:
            now = datetime.now()
            checkin_date = datetime(now.year, now.month, now.day, 5, 0, 0)
            checkout_date = checkin_date + timedelta(days=1)
            return checkout_date.strftime(DEFAULT_SERVER_DATETIME_FORMAT)

    @api.model
    def create(self, vals):
        '''nếu là Language -- English thì name là New -- VN thì name sẽ là Mới'''
        if 'name' in vals:
            if self.env.user.lang == 'vi_VN' and vals.get('name') == 'New':
                vals['name'] = 'Mới'
        '''gán check in check out default'''
        if 'check_in' not in vals and 'check_out' not in vals and 'room_id' in vals:
            vals['check_in'] = self.get_checkin_date()
            vals['check_out'] = self.get_checkout_date()

        get_branch_id = self.env['restaurant.pos'].search(
            [('id', '=', vals.get('branch_id'))])
        rec = super(SaleOrder, self).create(vals)
        return rec

    def write(self, vals):
        amount_untaxed = amount_tax = amount_discount = 0.0
        for line in self.order_line:
            amount_untaxed += line.price_subtotal
            amount_tax += line.price_tax
            amount_discount += (
                                       line.product_uom_qty * line.price_unit * line.discount) / 100
        vals['amount_untaxed'] = amount_untaxed
        vals['amount_tax'] = amount_tax
        vals['amount_discount'] = amount_discount
        vals['amount_total'] = amount_untaxed + amount_tax
        if 'discount_rate' in vals:
            if 'discount_type' in vals:
                if vals['discount_type'] == 'amount':
                    vals['amount_discount'] = vals['discount_rate']
                elif vals['discount_type'] == 'percent':
                    vals['amount_discount'] = (vals['amount_untaxed'] * vals['discount_rate']) / 100
            else:
                if self.discount_type == 'amount':
                    vals['amount_discount'] = vals['discount_rate']
                elif self.discount_type == 'percent':
                    vals['amount_discount'] = (vals['amount_untaxed'] * vals['discount_rate']) / 100
            vals['amount_total'] = vals['amount_total'] - vals['amount_discount']
        elif 'discount_type' in vals:
            if 'discount_rate' in vals:
                if vals['discount_type'] == 'amount':
                    vals['amount_discount'] = vals['discount_rate']
                elif vals['discount_type'] == 'percent':
                    vals['amount_discount'] = (vals['amount_untaxed'] * vals['discount_rate']) / 100
            else:
                if vals['discount_type'] == 'amount':
                    vals['amount_discount'] = self.discount_rate
                elif vals['discount_type'] == 'percent':
                    vals['amount_discount'] = (vals['amount_untaxed'] * self.discount_rate) / 100
            vals['amount_total'] = vals['amount_total'] - vals['amount_discount']
        elif self.discount_rate:
            if self.discount_type == 'amount':
                vals['amount_discount'] = self.discount_rate
            elif self.discount_type == 'percent':
                vals['amount_discount'] = (vals['amount_untaxed'] * self.discount_rate) / 100
            vals['amount_total'] = vals['amount_total'] - vals['amount_discount']

        if self:
            reserved_old = {}
            line_ids = []
            '''
            vals {'order_line': [[1, 20, {'qty_reserved': 1}]]}
            '''
            if 'order_line' in vals:
                for line_values in vals['order_line']:
                    if line_values[0] != 0:
                        line_ids.append(int(line_values[1]))
                    if line_values[0] == 1:  # Kiểm tra action là update
                        reserved_old[str(line_values[1])] = self.env['sale.order.line'].browse(
                            line_values[1]).qty_reserved
                rec = super(SaleOrder, self).write(vals)
                for line_values in vals['order_line']:
                    if line_values[0] == 1 or line_values[0] == 0:
                        if line_values[0] == 1 and self.env['sale.order.line'].browse(
                                line_values[1]).qty_reserved >= reserved_old.get(
                            str(line_values[1])) or line_values[0] == 0:
                            '''validate'''
                            picking_ids = self.env['stock.picking'].sudo().search(
                                [('state', 'not in', ['done', 'cancel']), ('sale_id', '=', self.id),
                                 ('origin', '=', self.name)])
                            line_id = 0
                            pro_id = 0
                            if line_values[0] == 1:
                                line_id = line_values[1]
                                pro_id = self.env['sale.order.line'].browse(line_values[1]).product_id.id
                            else:
                                if line_ids and self.order_line:
                                    for line in self.order_line:
                                        if line.id not in line_ids:
                                            line_id = line.id
                                            pro_id = line.product_id.id
                                            break
                            if line_id != 0 and pro_id != 0:
                                if picking_ids:
                                    for picking in picking_ids:
                                        check = self.env['stock.move'].sudo().search(
                                            [('picking_id', '=', picking.id),
                                             ('sale_line_id', '=', line_id),
                                             ('product_id', '=', pro_id)])
                                        for i in check:
                                            if i.quantity_done > 0:
                                                picking.validate_for_restaurant()
                                                break
                        elif line_values[0] == 1 and self.env['sale.order.line'].browse(
                                line_values[1]).qty_reserved < reserved_old.get(
                            str(line_values[1])):
                            print("return")
                            '''return'''
                            picking_ids_return = self.env['stock.picking'].sudo().search(
                                [('state', 'not in', ['done', 'cancel']), ('sale_id', '=', self.id),
                                 ('origin', '!=', self.name)])
                            if picking_ids_return:
                                upgrade = False
                                for picking_return in picking_ids_return:
                                    check_s = self.env['stock.move'].sudo().search(
                                        [('picking_id', '=', picking_return.id),
                                         ('sale_line_id', '=', line_values[1]),
                                         ('product_id', '=',
                                          self.env['sale.order.line'].browse(line_values[1]).product_id.id)])
                                    for i in check_s:
                                        if i.quantity_done > 0:
                                            picking_return.validate_return_for_restaurant()
                                            upgrade = True
                                            break

                                '''chú ý CHÚ Ý'''
                                if upgrade:
                                    uom_qty = self.env['sale.order.line'].browse(line_values[1]).product_uom_qty
                                    self.env['sale.order.line'].browse(line_values[1]).write(
                                        {'product_uom_qty': uom_qty - (
                                                reserved_old.get(str(line_values[1])) - self.env[
                                            'sale.order.line'].browse(line_values[1]).qty_reserved)})
                                    self.env['sale.order.line'].browse(line_values[1]).write(
                                        {'product_uom_qty': uom_qty})
                return rec
        return super(SaleOrder, self).write(vals)

    def confirm_order(self):
        # update all food item in restaurant served
        if self and self.table_id:
            if self.table_id.status != 'occupied':
                self.table_id.write({"status": "occupied"})

        self.action_confirm()
        self.action_unlock()
        '''thực hiện DONE nếu qty_reseved > 0 Không có RETURN'''
        for rec in self:
            if rec.order_line:
                pro_ids = []
                for line in rec.order_line:
                    if line.qty_reserved > 0:
                        qty_done = line.qty_reserved
                        stock_pickings = self.env['stock.picking'].sudo().search(
                            [('sale_id', '=', rec.id), ('state', 'not in', ['done', 'cancel'])])
                        if stock_pickings:
                            product_list = [{'product_id': line.product_id.id,
                                             'qty': qty_done}]
                            '''thao tác với SP kit'''
                            check_kit = False
                            mrp_bom = self.env['mrp.bom'].sudo().search(
                                ['|', ('product_id', '=', line.product_id.sudo().id), '&',
                                 ('product_id', '=', False),
                                 ('product_tmpl_id', '=', line.product_id.sudo().product_tmpl_id.id)], limit=1)
                            if mrp_bom:
                                if mrp_bom.type == 'phantom':
                                    '''start'''
                                    '''lấy công thức trên một đơn vị'''
                                    if mrp_bom.sudo().bom_line_ids:
                                        product_list = []
                                        for i in mrp_bom.sudo().bom_line_ids:
                                            check_kit = True
                                            pro_ids.append(i.product_id.id)
                                            product_list.append({'product_id': i.product_id.id,
                                                                 'qty': (
                                                                                i.product_qty / mrp_bom.sudo().product_qty) * qty_done})
                            if not check_kit:
                                pro_ids.append(line.product_id.id)

                            ''''''
                            for product_id in product_list:
                                for stock_picking in stock_pickings:
                                    if product_id['qty'] == 0:
                                        break
                                    stock_moves = self.env['stock.move'].sudo().search(
                                        [('picking_id', '=', stock_picking.id), ('sale_line_id', '=', line.id),
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
                                                                if stock_move_lines.product_uom_qty > 0 else product_id[
                                                                'qty']
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
                                                            update_quantity_wizard = self.env[
                                                                'change.production.qty'].create({
                                                                'mo_id': production_id.id,
                                                                'product_qty': stock_move_line.qty_done + production_id.product_qty,
                                                            })
                                                            update_quantity_wizard.change_prod_qty()

                                                            mrp_product_produce = self.env[
                                                                'mrp.product.produce'].sudo().with_context(
                                                                active_id=production_id.id).sudo().create(
                                                                {'production_id': production_id.id,
                                                                 'product_id': product_id['product_id'],
                                                                 'product_qty': stock_move_line.qty_done})
                                                            mrp_product_produce._onchange_product_qty()
                                                            mrp_product_produce.do_produce()
                                                            production_id.post_inventory()

                                                            '''chú ý CHÚ Ý'''
                                                            stock_move_update = self.env['stock.move'].sudo().search(
                                                                [('raw_material_production_id', '=', production_id.id),
                                                                 ('state', 'not in', ['done', 'cancel'])])
                                                            for i in stock_move_update:
                                                                move_line = self.env['stock.move.line'].sudo().search(
                                                                    [('move_id', '=', i.id),
                                                                     ('state', 'not in', ['done', 'cancel'])])
                                                                for line_ in move_line:
                                                                    if line_.product_uom_qty < 0:
                                                                        line_.product_uom_qty = 0

                '''validate'''
                picking_ids = self.env['stock.picking'].sudo().search(
                    [('state', 'not in', ['done', 'cancel']), ('sale_id', '=', rec.id),
                     ('origin', '=', rec.name)])
                if picking_ids:
                    for picking in picking_ids:
                        check = self.env['stock.move'].sudo().search(
                            [('picking_id', '=', picking.id),
                             ('product_id', 'in', pro_ids)])
                        for i in check:
                            if i.quantity_done > 0:
                                picking.validate_for_restaurant()
                                break

    def unlock_sale_order(self):
        self.action_unlock()
        if self.table_id:
            self.table_id.status = 'occupied'

    def cancel_stock_picking(self):
        picking_ids = self.env['stock.picking'].sudo().search(
            [('state', 'not in', ['done', 'cancel']), ('sale_id', '=', self.id)])
        for picking in picking_ids:
            picking.action_cancel()

    def done_or_cancel_mrp_production(self):
        mrp_ids = self.env['mrp.production'].sudo().search(
            [('origin', '=', self.name), ('state', 'not in', ['done', 'cancel'])])
        for mrp in mrp_ids:
            if mrp.finished_move_line_ids:
                '''cập nhật lại SL SX bằng với SX thực tế'''
                qty = 0.0
                for i in mrp.finished_move_line_ids:
                    if i.qty_done:
                        qty += i.qty_done
                update_quantity_wizard = self.env['change.production.qty'].sudo().create({
                    'mo_id': mrp.id,
                    'product_qty': qty,
                })
                update_quantity_wizard.change_prod_qty()
                mrp.button_mark_done()
            else:
                mrp.action_cancel()

    def change_partner(self):
        picking_ids = self.env['stock.picking'].sudo().search(
            [('sale_id', '=', self.id)])
        for picking in picking_ids:
            if picking.sudo().partner_id:
                if picking.sudo().partner_id.id != self.partner_id.id:
                    picking.sudo().partner_id = self.partner_id.id
            else:
                picking.sudo().partner_id = self.partner_id.id

    def lock_restaurant_order(self):
        # print('lock_restaurant_order: ', state_folio)
        if self.order_line and self.pos_id.sudo().branch_id.sudo().done_invisible:
            pro_ids = []
            for line in self.order_line:
                ''' product_uom_qty = qty_reserved '''
                line.write({
                    'qty_reserved': line.product_uom_qty
                })
                pro_ids.append(line.product_id.id)
            '''validate'''
            picking_ids = self.env['stock.picking'].sudo().search(
                [('state', 'not in', ['done', 'cancel']), ('sale_id', '=', self.id)])
            if picking_ids:
                for picking in picking_ids:
                    check = self.env['stock.move'].sudo().search(
                        [('picking_id', '=', picking.id),
                         ('product_id', 'in', pro_ids)])
                    for i in check:
                        if i.quantity_done > 0:
                            picking.validate_for_restaurant()
                            break
        check = True
        if self.order_line:
            for line in self.order_line:
                if line.product_id.sudo().product_tmpl_id.sudo().type != 'service':
                    '''cập nhật lại product_uom_qty = qty_delivered'''
                    line.product_uom_qty = line.qty_delivered
                    if line.qty_reserved != line.qty_delivered:
                        check = False
                else:
                    line.product_uom_qty = line.qty_reserved

            if self.table_id:
                self.table_id.status = 'available'
        self.action_done()
        if not check and self.order_line:
            for line in self.order_line:
                if line.qty_reserved != line.qty_delivered \
                        and line.product_id.sudo().product_tmpl_id.sudo().type != 'service':
                    '''cập nhật lại qty_reserved = qty_delivered'''
                    line.qty_reserved = line.qty_delivered

        self.change_partner()
        self.done_or_cancel_mrp_production()
        self.cancel_stock_picking()

    def move_table(self):
        context = dict(self._context)
        context.update({'move_order_id_parent': self.table_id.id,
                        'company_id': self.company_id.id,
                        'pos_id': self.pos_id.id})
        view = self.env.ref('restaurant.view_move_table_virtual_form')
        return {
            'name': 'Chọn bàn để chuyển',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'table.virtual.many2one',
            'view_id': view.id,
            'context': context,
            'target': 'new',
            'type': 'ir.actions.act_window',
        }

    def invoice_create_and_validate_restaurant(self, payment_id=False):
        '''tạo invoice'''
        list_invoice = self.env['sale.order'].browse([self.id])._create_invoices(final=True)

        '''Thay đổi:
            + journal_id lấy invoice_journal_id trong POS, branch(branch giành cho folio hoặc khi POS không có)
            nếu đúng thì account_id, origin, partner_id, partner_shipping_id,user_id đều không cần đổi
            + account_id lấy trong res_partner (property_account_recievable_id) (không lấy partner có trường này null)
            + origin lấy từ SO (lấy tất cả các tên của SO. Cách nhau bằng ",")
            + partner_id và partner_shipping_id (lấy từ SO đẩy qua invoice)
            + user_id (từ salesperson trong SO, và salesperson trong folio)
        '''
        for rec in self:
            '''lấy journal_id'''
            journal_ids = []
            if payment_id:
                if 'account_payment_id' in payment_id:
                    journals = payment_id.get('account_payment_id').split(',')
                    for j in journals:
                        value = j.split(':')
                        if value and len(value) == 2:
                            journal_ids.append({'id': int(value[0]), 'value': value[1]})

            if len(journal_ids) == 0:
                if rec.pos_id:
                    if rec.pos_id.sudo().payment_journal_ids:
                        for i in rec.pos_id.sudo().payment_journal_ids:
                            journal_ids.append({'id': i.id, 'value': False})
                            break
                    else:
                        if rec.pos_id.sudo().branch_id.sudo().payment_journal_ids:
                            for j in rec.pos_id.sudo().branch_id.sudo().payment_journal_ids:
                                journal_ids.append({'id': j.id, 'value': False})
                                break

            for invoice in self.env['account.move'].sudo().search([('id', 'in', list_invoice.ids)]):
                # if rec.pos_id:
                #     if rec.pos_id.sudo().invoice_journal_id:
                #         if rec.pos_id.sudo().invoice_journal_id.id != invoice.journal_id.id:
                #             invoice.journal_id = rec.pos_id.sudo().invoice_journal_id.id
                #     else:
                #         if rec.pos_id.sudo().branch_id.sudo().invoice_journal_id.id != invoice.journal_id.id:
                #             invoice.journal_id = rec.pos_id.sudo().branch_id.sudo().invoice_journal_id.id

                '''validate'''
                self.env['account.move'].browse([invoice.id]).action_post()
                '''Register Payment'''
                if journal_ids:
                    for journal in journal_ids:
                        action = self.env['account.move'].browse([invoice.id]).action_register_payment()
                        wizard = Form(self.env['account.payment.register'].with_context(action['context'])).save()
                        wizard.journal_id = journal['id']
                        action = wizard.action_create_payments()

                        # account_payment = {
                        #     'ref': invoice.name,
                        #     'date': datetime.now().strftime("%Y-%m-%d"),
                        #     'name': "/",
                        #     'journal_id': invoice.journal_id.id,
                        #     'invoice_user_id': invoice.invoice_user_id.id,
                        #     'team_id': invoice.team_id.id,
                        #     'move_type': 'entry',
                        #     'auto_post': 'no',
                        #     'payment_method_id': 1,
                        #     'payment_method_line_id': 7
                        #     # 'invoice_ids': [[6, False, [invoice.id]]],
                        #     # 'journal_id': journal['id'],
                        #     # 'amount': journal['value'] if journal['value'] else invoice.amount_total,
                        #     # 'currency_id': invoice.currency_id.id,
                        #     # 'partner_id': invoice.partner_id.id,
                        #     # 'payment_date': datetime.now().strftime("%Y-%m-%d"),
                        #     # 'communication': invoice.reference,
                        #     # 'payment_type': 'inbound',
                        #     # 'partner_type': 'customer',
                        #     # 'payment_difference_handling': 'open',
                        #     # 'writeoff_label': 'Write-Off',
                        # }
                        # # res = self.env['account.payment'].sudo().create(account_payment)
                        # # self.env['account.payment'].browse([res.id]).action_create_payments()
                        #
                        # res = self.env['account.payment'].sudo().create(account_payment)
                        # action = res.action_register_payment()
                        #
                        # self.env['account.payment.register'].browse([action.id]).action_create_payments()
                        # # wizard = Form(self.env['account.payment.register'].with_context(action_data['context'])).save()
                        # # action = wizard.action_create_payments()

    def get_payments(self):
        for rec in self:
            # for invoice in rec.invoice_ids.sudo().filtered(
            #         lambda record: record.state in ['posted']):
            #     for move in invoice.sudo().payment_move_line_ids:
            #         value.append(move.sudo().journal_id.sudo().id)
            # if not value:
            #     if rec.invoice_ids.sudo().filtered(
            #             lambda record: record.state in ['open']):
            #         value.append(0)
            ref = []
            for invoice in self.mapped('invoice_ids'):
                ref.append(invoice.name)
            payment = self.env['account.payment'].search([('ref', 'in', ref)], limit = 1)
            if payment:
                if payment.journal_id:
                    return [payment.journal_id.id]
        return [0]

    def edit_line(self, vals):
        self.write({'order_line': vals})

# Chuyen bàn
class TableVirtualMany2one(models.TransientModel):
    _name = 'table.virtual.many2one'
    _description = 'Table Virtual Many2one To Test'

    table_id_pool = fields.Many2one('restaurant.table', string='Table Will Merge')
    order_id_parent = fields.Many2one('restaurant.table', string="Table ID Origin", readonly=True,
                                      default=lambda self: self._context.get('move_order_id_parent'))
    order_line = fields.Many2many('sale.order.line', string='List Of Dishes', domain="[]")
    company_id = fields.Many2one('res.company', string='Company', required=True,
                                 default=lambda self: self._context.get('company_id'))
    pos_id = fields.Many2one('restaurant.pos', string='Point of Sale', require=True,
                                              default=lambda self: self._context.get('pos_id'))

    @api.model
    def create(self, vals):
        record = super(TableVirtualMany2one, self).create(vals)
        if record.order_id_parent:
            order_id_parent = self.env["sale.order"].sudo().search(
                [('table_id', '=', record.order_id_parent.id), ('state', 'in', ['sale'])], limit=1)
            order_id_parent.write({'table_id': vals.get('table_id_pool')})
            return_occupied_table = self.env["restaurant.table"].sudo().search(
                [('id', '=', record.table_id_pool.id)])
            return_occupied_table.write({'status': 'occupied'})
            return_availeble_table = self.env["restaurant.table"].sudo().search(
                [('id', '=', record.order_id_parent.id)])
            return_availeble_table.write({'status': 'available'})

        return record

class ResPartner(models.Model):
    _inherit = "res.partner"

    @api.model
    def create(self, vals):
        property_account_receivable_id = self.env['account.account'].search([
            ('account_type', '=', 'asset_receivable'), ('deprecated', '=', False),
            ('company_id', '=', self.env.user.company_id.id)
        ], limit=1)
        if property_account_receivable_id:
            vals['property_account_receivable_id'] = property_account_receivable_id.id
        property_account_payable_id = self.env['account.account'].search([
            ('account_type', '=', 'liability_payable'), ('deprecated', '=', False),
            ('company_id', '=', self.env.user.company_id.id)
        ], limit=1)
        if property_account_payable_id:
            vals['property_account_payable_id'] = property_account_payable_id.id

        return super(ResPartner, self).create(vals)
