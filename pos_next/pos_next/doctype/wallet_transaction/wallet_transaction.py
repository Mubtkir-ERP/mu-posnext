# Copyright (c) 2024, BrainWise and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, today
from erpnext.accounts.general_ledger import make_gl_entries
from erpnext.controllers.accounts_controller import AccountsController

class WalletTransaction(AccountsController):
	def validate(self):
		# Wallet/customer/company are server-authoritative.  Populate them before
		# validating the amount so a crafted request cannot validate against a
		# different customer or company.
		self.validate_wallet()
		self.set_customer_from_wallet()
		self.validate_source_integrity()
		self.validate_amount()

	def validate_wallet(self):
		"""Validate wallet and pin transaction context to its trusted row."""
		if not self.wallet:
			frappe.throw(_("Wallet is required"))

		wallet = frappe.db.get_value(
			"Wallet",
			self.wallet,
			["customer", "company", "account", "status"],
			as_dict=True,
		)
		if not wallet:
			frappe.throw(_("Wallet {0} does not exist").format(self.wallet))
		if wallet.status not in ("Active", "active"):
			frappe.throw(_("Wallet {0} is not active").format(self.wallet))

		# Never trust company/customer values supplied by a browser or API client.
		self.customer = wallet.customer
		self.company = wallet.company
		self._wallet_account = wallet.account

	def validate_amount(self):
		"""Validate amount and live balance for debit transactions."""
		if flt(self.amount) <= 0:
			frappe.throw(_("Amount must be greater than zero"))

		if self.transaction_type == "Debit":
			from pos_next.api.wallet import _get_customer_wallet_balance, _lock_wallet

			_lock_wallet(self.wallet)
			balance = _get_customer_wallet_balance(self.customer, self.company)
			if flt(self.amount) > flt(balance) + 0.005:
				frappe.throw(
					_("Insufficient wallet balance. Available: {0}, Requested: {1}").format(
						frappe.format_value(balance, {"fieldtype": "Currency"}),
						frappe.format_value(self.amount, {"fieldtype": "Currency"}),
					)
				)

	def set_customer_from_wallet(self):
		"""Refresh customer/company from wallet even when client sent values."""
		if not self.wallet:
			return
		wallet = frappe.db.get_value(
			"Wallet", self.wallet, ["customer", "company"], as_dict=True
		)
		if wallet:
			self.customer = wallet.customer
			self.company = wallet.company

	def validate_source_integrity(self):
		"""Protect server-generated loyalty credits from client tampering."""
		valid_sources = {"Mode of Payment", "Loyalty Program", "Manual Adjustment", "Refund"}
		if self.source_type and self.source_type not in valid_sources:
			frappe.throw(_("Invalid wallet transaction source type."))

		if self.source_account:
			account = frappe.db.get_value(
				"Account", self.source_account, ["company", "is_group", "disabled"], as_dict=True
			)
			if not account or account.company != self.company or account.is_group or account.disabled:
				frappe.throw(_("Source account is not valid for the wallet company."))

		if self.source_type == "Loyalty Program":
			if self.transaction_type != "Loyalty Credit":
				frappe.throw(_("Loyalty Program transactions must use Loyalty Credit type."))
			if self.reference_doctype != "Sales Invoice" or not self.reference_name:
				frappe.throw(_("Loyalty wallet credit requires a Sales Invoice reference."))

			from pos_next.api.wallet import _get_loyalty_credit_details

			details = _get_loyalty_credit_details(self.reference_name)
			if not details:
				frappe.throw(_("No earned loyalty points were found for this invoice."))
			if details.customer != self.customer or details.company != self.company:
				frappe.throw(_("The loyalty reference does not belong to this wallet."))
			if abs(flt(self.amount) - flt(details.credit_amount)) > 0.005:
				frappe.throw(_("Loyalty wallet amount does not match the server-calculated amount."))

			# Exact source account is also server-authoritative for loyalty credit.
			self.source_account = details.expense_account

	def on_submit(self):
		"""Create GL entries on submit"""
		self.make_gl_entries()
		self.update_wallet_balance()

	def on_cancel(self):
		"""Reverse GL entries on cancel"""
		self.ignore_linked_doctypes = (
        "GL Entry",
		"Payment Ledger Entry"
    	)
		self.make_gl_entries(cancel=True)
		self.update_wallet_balance()

	def update_wallet_balance(self):
		"""Update the wallet's current balance"""
		wallet_doc = frappe.get_doc("Wallet", self.wallet)
		wallet_doc.update_balance()

	def make_gl_entries(self, cancel=False):
		"""Create GL entries for wallet transaction"""
		gl_entries = self.build_gl_entries()

		if gl_entries:
			make_gl_entries(
				gl_entries,
				cancel=cancel,
				update_outstanding="Yes",
				merge_entries=frappe.db.get_single_value(
					"Accounts Settings", "merge_similar_account_heads"
				)
			)

	def build_gl_entries(self):
		"""Build GL entry list based on transaction type"""
		gl_entries = []

		wallet_account = frappe.db.get_value("Wallet", self.wallet, "account")
		if not wallet_account:
			frappe.throw(_("Wallet {0} does not have an account configured").format(self.wallet))

		# Get source account based on source type
		source_account = self.get_source_account()

		if not source_account:
			frappe.throw(_("Source account is required for wallet transaction"))

		cost_center = self.cost_center or frappe.get_cached_value(
			"Company", self.company, "cost_center"
		)

		amount = flt(self.amount, self.precision("amount"))

		if self.transaction_type in ["Credit", "Loyalty Credit"]:
			# Credit to wallet (increase balance)
			# Debit source account, Credit wallet account (with party)
			source_gl = {
				"account": source_account,
				"debit": amount,
				"debit_in_account_currency": amount,
				"cost_center": cost_center,
				"remarks": self.remarks or _("Wallet Credit: {0}").format(self.name)
			}
			# Receivable/Payable accounts require party information
			if not hasattr(self, '_source_account_type'):
				self._source_account_type = frappe.get_cached_value("Account", source_account, "account_type")
			if self._source_account_type in ("Receivable", "Payable") and self.customer:
				source_gl["party_type"] = "Customer"
				source_gl["party"] = self.customer
			gl_entries.append(self.get_gl_dict(source_gl))
			gl_entries.append(
				self.get_gl_dict({
					"account": wallet_account,
					"party_type": "Customer",
					"party": self.customer,
					"credit": amount,
					"credit_in_account_currency": amount,
					"cost_center": cost_center,
					"remarks": self.remarks or _("Wallet Credit: {0}").format(self.name)
				})
			)

		elif self.transaction_type == "Debit":
			# Debit from wallet (decrease balance)
			# Debit wallet account (with party), Credit source account
			gl_entries.append(
				self.get_gl_dict({
					"account": wallet_account,
					"party_type": "Customer",
					"party": self.customer,
					"debit": amount,
					"debit_in_account_currency": amount,
					"cost_center": cost_center,
					"remarks": self.remarks or _("Wallet Debit: {0}").format(self.name)
				})
			)
			debit_source_gl = {
				"account": source_account,
				"credit": amount,
				"credit_in_account_currency": amount,
				"cost_center": cost_center,
				"remarks": self.remarks or _("Wallet Debit: {0}").format(self.name)
			}
			# Receivable/Payable accounts require party information
			if not hasattr(self, '_source_account_type'):
				self._source_account_type = frappe.get_cached_value("Account", source_account, "account_type")
			if self._source_account_type in ("Receivable", "Payable") and self.customer:
				debit_source_gl["party_type"] = "Customer"
				debit_source_gl["party"] = self.customer
			gl_entries.append(self.get_gl_dict(debit_source_gl))

		return gl_entries

	def get_source_account(self):
		"""Get source account based on source type"""
		if self.source_account:
			return self.source_account

		if self.source_type == "Mode of Payment" and self.source_account:
			return self.source_account

		if self.source_type == "Loyalty Program":
			# Get loyalty expense account from loyalty program or company
			loyalty_account = frappe.db.get_value(
				"Loyalty Program",
				{"company": self.company},
				"expense_account"
			)
			if loyalty_account:
				return loyalty_account

			# Fallback to company's default expense account
			return frappe.get_cached_value("Company", self.company, "default_expense_account")

		if self.source_type == "Refund":
			# Use company's default receivable account
			return frappe.get_cached_value("Company", self.company, "default_receivable_account")

		if self.source_type == "Manual Adjustment":
			# Use company's adjustment account or default expense
			return frappe.get_cached_value("Company", self.company, "default_expense_account")

		return None


def create_wallet_credit(wallet, amount, source_type="Manual Adjustment", remarks=None,
						 reference_doctype=None, reference_name=None, submit=True):
	"""Internal low-level wallet credit creator.

	This function is intentionally not whitelisted.  Public API callers must use
	the guarded endpoints in ``pos_next.api.wallet``.  Loyalty credit values are
	recalculated from ERPNext records even for internal callers.
	"""
	wallet_doc = frappe.get_doc("Wallet", wallet)
	if wallet_doc.status not in ("Active", "active"):
		frappe.throw(_("Wallet {0} is not active").format(wallet))

	amount = flt(amount)
	if amount <= 0:
		frappe.throw(_("Amount must be greater than zero"))

	transaction_type = "Loyalty Credit" if source_type == "Loyalty Program" else "Credit"
	source_account = None

	if source_type == "Loyalty Program":
		if reference_doctype != "Sales Invoice" or not reference_name:
			frappe.throw(_("Loyalty wallet credit requires a Sales Invoice reference."))

		from pos_next.api.wallet import _get_loyalty_credit_details

		details = _get_loyalty_credit_details(reference_name)
		if not details:
			frappe.throw(_("No earned loyalty points were found for this invoice."))
		if details.customer != wallet_doc.customer or details.company != wallet_doc.company:
			frappe.throw(_("The loyalty invoice does not belong to this wallet."))

		# Ignore any caller-provided loyalty amount.  The Loyalty Point Entry and
		# Loyalty Program conversion factor are the only sources of truth.
		amount = flt(details.credit_amount)
		source_account = details.expense_account

	# Reference-backed credits are idempotent.  This is especially important for
	# invoice submit retries: one invoice can create at most one active loyalty/refund credit.
	if reference_doctype and reference_name and source_type in ("Loyalty Program", "Refund"):
		existing_name = frappe.db.get_value(
			"Wallet Transaction",
			{
				"wallet": wallet,
				"reference_doctype": reference_doctype,
				"reference_name": reference_name,
				"source_type": source_type,
				"transaction_type": transaction_type,
				"docstatus": ["!=", 2],
			},
			"name",
		)
		if existing_name:
			existing = frappe.get_doc("Wallet Transaction", existing_name)
			if submit and existing.docstatus == 0:
				existing.flags.ignore_permissions = True
				existing.submit()
				return existing
			if existing.docstatus == 1:
				# If a previous request died after docstatus changed but before GL
				# creation, recover instead of silently accepting a broken credit.
				if frappe.db.exists("GL Entry", {"voucher_no": existing.name, "is_cancelled": 0}):
					return existing
				try:
					existing.flags.ignore_permissions = True
					existing.cancel()
				except Exception:
					frappe.log_error(
						title="Wallet Transaction Recovery Error",
						message=f"Could not cancel broken WT {existing.name}: {frappe.get_traceback()}",
					)
					return existing
			else:
				return existing

	if not source_account:
		if source_type == "Refund":
			source_account = frappe.get_cached_value(
				"Company", wallet_doc.company, "default_receivable_account"
			)
		else:
			source_account = frappe.get_cached_value(
				"Company", wallet_doc.company, "default_expense_account"
			)

	if not source_account:
		frappe.throw(_("Source account is required for wallet transaction"))

	transaction = frappe.get_doc({
		"doctype": "Wallet Transaction",
		"transaction_type": transaction_type,
		"wallet": wallet,
		"company": wallet_doc.company,
		"posting_date": today(),
		"amount": amount,
		"source_type": source_type,
		"source_account": source_account,
		"remarks": remarks,
		"reference_doctype": reference_doctype,
		"reference_name": reference_name,
	})
	transaction.flags.ignore_permissions = True
	transaction.insert(ignore_permissions=True)
	if submit:
		transaction.submit()
	return transaction


@frappe.whitelist()
def credit_loyalty_points_to_wallet(customer, company, loyalty_points=None, conversion_factor=None):
	"""Deprecated direct conversion endpoint.

	The old endpoint trusted a point count and conversion factor from the caller,
	which allowed wallet value to be forged.  POSNext now creates loyalty wallet
	credit only from a submitted invoice's server-generated Loyalty Point Entry.
	"""
	frappe.throw(
		_("Direct loyalty-to-wallet conversion is disabled. Loyalty credit is created from submitted invoices."),
		frappe.PermissionError,
	)


def credit_return_to_wallet(return_invoice, amount=None):
	"""Credit a return invoice to the customer's wallet.

	The return invoice total is the source of truth.  ``amount`` is retained only
	for backward-compatible Python callers and is never trusted to increase the
	wallet credit.
	"""
	return_data = frappe.db.get_value(
		"Sales Invoice",
		return_invoice,
		["customer", "company", "grand_total", "is_return", "return_against", "pos_profile", "docstatus"],
		as_dict=True,
	)
	if not return_data or not return_data.is_return or return_data.docstatus != 1:
		frappe.log_error(
			title="Wallet Credit on Return Error",
			message=f"Invoice {return_invoice} is not a submitted return invoice",
		)
		return None

	credit_amount = abs(flt(return_data.grand_total))
	if credit_amount <= 0:
		return None

	# ``amount`` is intentionally ignored.  The submitted return invoice total is
	# the only authority for how much wallet credit may be created.

	from pos_next.api.wallet import _get_or_create_wallet, get_pos_settings

	pos_settings = get_pos_settings(return_data.pos_profile) if return_data.pos_profile else None
	wallet = _get_or_create_wallet(
		return_data.customer,
		return_data.company,
		pos_settings=pos_settings,
		force_create=True,
	)
	if not wallet:
		frappe.log_error(
			title="Wallet Credit on Return Error",
			message=f"Could not get or create wallet for customer {return_data.customer}, company {return_data.company}",
		)
		return None

	wallet_name = wallet.name if hasattr(wallet, "name") else wallet["name"]
	transaction = create_wallet_credit(
		wallet=wallet_name,
		amount=credit_amount,
		source_type="Refund",
		reference_doctype="Sales Invoice",
		reference_name=return_invoice,
		remarks=_("Return credit to wallet for {0} against {1}: {2}").format(
			return_invoice,
			return_data.return_against or "",
			frappe.format_value(credit_amount, {"fieldtype": "Currency"}),
		),
		submit=True,
	)
	return transaction


@frappe.whitelist()
def reverse_wallet_transactions_for_return(original_invoice, return_invoice):
	"""
	Reverse wallet transactions linked to the original invoice when a return is made.

	For full returns: Cancel the linked Wallet Transaction(s)
	For partial returns: Create a proportional Debit transaction to reverse the credit

	Args:
		original_invoice: Original Sales Invoice name
		return_invoice: Return Sales Invoice name (is_return=1)
	"""
	from pos_next.api.security import require_pos_document_access

	# Authorize both documents before any wallet mutation.  The database-linked
	# POS Profile/company is authoritative; invoice names from the browser are not.
	require_pos_document_access("Sales Invoice", original_invoice, ptype="read")
	require_pos_document_access("Sales Invoice", return_invoice, ptype="read")

	# Get both invoices only after the permission boundary has been checked.
	return_doc = frappe.get_doc("Sales Invoice", return_invoice)
	original_doc = frappe.get_doc("Sales Invoice", original_invoice)

	if original_doc.docstatus != 1 or return_doc.docstatus != 1:
		frappe.throw(_("Wallet reversal requires submitted invoices."), frappe.ValidationError)
	if (
		return_doc.company != original_doc.company
		or return_doc.customer != original_doc.customer
		or not return_doc.is_return
		or return_doc.return_against != original_invoice
	):
		frappe.throw(_("Return invoice does not match the original wallet invoice."), frappe.ValidationError)

	existing = frappe.db.exists("Wallet Transaction", {
		"reference_doctype": "Sales Invoice",
		"reference_name": return_invoice,
		"transaction_type": "Debit",
		"source_type": "Refund",
		"docstatus": ["!=", 2],
	})
	if existing:
		return
	# Find all submitted Wallet Transactions linked to the original invoice
	wallet_transactions = frappe.get_all(
		"Wallet Transaction",
		filters={
			"reference_doctype": "Sales Invoice",
			"reference_name": original_invoice,
			"docstatus": 1,
			"transaction_type": ["in", ["Credit", "Loyalty Credit"]]
		},
		fields=["name", "wallet", "amount", "transaction_type", "source_type",
				"source_account", "company", "customer"]
	)

	if not wallet_transactions:
		return

	# return grand_total is negative, original is positive
	original_total = abs(flt(original_doc.grand_total))
	returned_amount = abs(flt(return_doc.grand_total))

	if original_total <= 0:
		return
	if returned_amount > original_total + 0.005:
		frappe.throw(_("Return amount cannot exceed the original invoice amount."), frappe.ValidationError)

	# Check if this is a full return
	# Keep full precision for ratio; only round the final reverse_amount
	return_ratio = returned_amount / original_total
	is_full_return = return_ratio >= 0.999  # Allow small rounding tolerance

	# Get loyalty program details for tier-aware reversal of Loyalty Credit.
	# Supports both "Single Tier Program" (one rule) and "Multiple Tier Program" (many rules).
	# Original credit: points = int(eligible_amount / collection_factor), wallet = points * conversion_factor
	loyalty_program = frappe.db.get_value(
		"Loyalty Point Entry",
		{
			"invoice_type": "Sales Invoice",
			"invoice": original_invoice,
			"customer": original_doc.customer,
			"loyalty_points": [">", 0],
		},
		"loyalty_program",
	)

	tiers = []
	conversion_factor = 1.0
	if loyalty_program:
		lp_doc = frappe.get_doc("Loyalty Program", loyalty_program)
		conversion_factor = flt(lp_doc.conversion_factor) or 1.0
		tiers = sorted(
			[d.as_dict() for d in (lp_doc.get("collection_rules") or [])],
			key=lambda r: flt(r.get("min_spent")),
		)

	invoiced_amount_after_return = flt(original_total) - flt(returned_amount)

	def _find_tier(amount):
		"""Return the highest tier whose min_spent <= amount, or None."""
		matched = None
		for t in tiers:
			if flt(amount) >= flt(t.get("min_spent")):
				matched = t
		return matched

	# Determine the applicable tier for the post-return effective amount
	new_tier = _find_tier(invoiced_amount_after_return) if tiers else None

	for wt in wallet_transactions:
		# ── Decide: cancel entirely  OR  create a partial Debit ──
		should_cancel = False
		reverse_amount = 0

		if is_full_return:
			should_cancel = True

		elif wt.transaction_type == "Loyalty Credit" and tiers:
			# Tier-aware reversal for Loyalty Credit
			if not new_tier:
				# Post-return amount below the lowest tier's min_spent → reverse ALL
				should_cancel = True
			else:
				# Recalculate what the credit should be for the post-return amount
				new_cf = flt(new_tier.get("collection_factor")) or 1.0
				recalculated_points = int(flt(invoiced_amount_after_return) / new_cf)
				recalculated_credit = flt(recalculated_points) * flt(conversion_factor)
				reverse_amount = flt(flt(wt.amount) - recalculated_credit, 2)

				if flt(reverse_amount) >= flt(wt.amount):
					# Recalculated credit is zero or negative → cancel entirely
					should_cancel = True
					reverse_amount = 0

		else:
			# Regular Credit (or Loyalty Credit without tiers) → proportional reversal
			reverse_amount = flt(wt.amount * return_ratio, 2)

		# ── Execute the reversal ──
		if should_cancel:
			try:
				wt_doc = frappe.get_doc("Wallet Transaction", wt.name)
				wt_doc.flags.ignore_permissions = True
				wt_doc.cancel()
				frappe.msgprint(
					_("Cancelled Wallet Transaction {0} due to return").format(wt.name),
					alert=True, indicator="blue"
				)
			except Exception as e:
				frappe.log_error(
					title="Wallet Transaction Cancel on Return Error",
					message=f"WT: {wt.name}, Return: {return_invoice}, Error: {str(e)}\n{frappe.get_traceback()}"
				)

		elif reverse_amount > 0:
			try:
				reverse_wt = frappe.get_doc({
					"doctype": "Wallet Transaction",
					"transaction_type": "Debit",
					"wallet": wt.wallet,
					"company": wt.company,
					"posting_date": today(),
					"amount": reverse_amount,
					"source_type": "Refund",
					"source_account": wt.source_account,
					"reference_doctype": "Sales Invoice",
					"reference_name": return_invoice,
					"remarks": _("Wallet reversal for return {0} against {1}: returned {2}, reversed {3}").format(
						return_invoice, original_invoice,
						frappe.format_value(returned_amount, {"fieldtype": "Currency"}),
						frappe.format_value(reverse_amount, {"fieldtype": "Currency"})
					)
				})
				reverse_wt.flags.ignore_permissions = True
				reverse_wt.insert()
				reverse_wt.submit()

				frappe.msgprint(
					_("Created wallet debit of {0} for partial return {1}").format(
						frappe.format_value(reverse_amount, {"fieldtype": "Currency"}),
						return_invoice
					),
					alert=True, indicator="blue"
				)
			except Exception as e:
				frappe.log_error(
					title="Wallet Transaction Reverse on Partial Return Error",
					message=(
						f"WT: {wt.name}, Return: {return_invoice}, "
						f"Original: {original_invoice}, Reverse Amount: {reverse_amount}, "
						f"Error: {str(e)}\n{frappe.get_traceback()}"
					)
				)
