# Copyright (c) 2026, POS Next and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import cint


class PrepaidVoucherBalance(Document):
	def autoname(self):
		if self.branch:
			self.name = f"{self.customer}::{self.branch}"
		else:
			self.name = f"{self.customer}::GENERAL"

	def validate(self):
		if not self.branch:
			self.is_general = 1
		self.current_balance = cint(self.total_purchased) - cint(self.total_redeemed)
		if self.current_balance < 0:
			frappe.throw("Voucher balance cannot be negative")
