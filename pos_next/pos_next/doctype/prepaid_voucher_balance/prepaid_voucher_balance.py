# Copyright (c) 2026, POS Next and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import cint


class PrepaidVoucherBalance(Document):
	def validate(self):
		self.current_balance = cint(self.total_purchased) - cint(self.total_redeemed)
		if self.current_balance < 0:
			frappe.throw("Voucher balance cannot be negative")
