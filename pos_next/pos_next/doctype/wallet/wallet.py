# Copyright (c) 2024, BrainWise and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt
from erpnext.accounts.utils import get_balance_on


class Wallet(Document):
	def validate(self):
		self.validate_account_type()
		self.validate_duplicate_wallet()

	def validate_account_type(self):
		"""Wallet account must be an active leaf Receivable account in the wallet company."""
		if not self.account:
			return
		account = frappe.db.get_value(
			"Account",
			self.account,
			["account_type", "company", "is_group", "disabled"],
			as_dict=True,
		)
		if (
			not account
			or account.account_type != "Receivable"
			or account.company != self.company
			or cint(account.is_group)
			or cint(account.disabled)
		):
			frappe.throw(_("Wallet Account must be an active Receivable account for the wallet company"))

	def validate_duplicate_wallet(self):
		"""Check for duplicate wallet for same customer and company."""
		if not self.is_new():
			return
		existing = frappe.db.exists(
			"Wallet",
			{"customer": self.customer, "company": self.company, "name": ("!=", self.name)},
		)
		if existing:
			frappe.throw(
				_("A wallet already exists for customer {0} in company {1}").format(
					self.customer, self.company
				)
			)

	def get_balance(self):
		"""Get current wallet balance from GL entries."""
		if not self.account or not self.customer:
			return 0.0
		balance = get_balance_on(
			account=self.account,
			party_type="Customer",
			party=self.customer,
		)
		return -flt(balance)

	def get_available_balance(self):
		"""Get available balance using the canonical wallet service."""
		from pos_next.api.wallet import _get_customer_wallet_balance

		return _get_customer_wallet_balance(self.customer, self.company)

	def update_balance(self):
		"""Update cached balance fields from the canonical calculations."""
		self.current_balance = self.get_balance()
		self.available_balance = self.get_available_balance()
		self.db_set("current_balance", self.current_balance, update_modified=False)
		self.db_set("available_balance", self.available_balance, update_modified=False)


@frappe.whitelist()
def get_customer_wallet(customer, company=None, pos_profile=None):
	"""Compatibility wrapper around the canonical POS wallet API."""
	from pos_next.api.wallet import get_customer_wallet as canonical_get_customer_wallet

	return canonical_get_customer_wallet(customer, company, pos_profile=pos_profile)


@frappe.whitelist()
def get_customer_wallet_balance(customer, company=None, exclude_invoice=None, pos_profile=None):
	"""Compatibility wrapper around the canonical POS wallet balance API."""
	from pos_next.api.wallet import get_customer_wallet_balance as canonical_get_balance

	return canonical_get_balance(
		customer,
		company,
		exclude_invoice=exclude_invoice,
		pos_profile=pos_profile,
	)


def get_pending_wallet_payments(customer, company=None, exclude_invoice=None):
	"""Compatibility wrapper for internal callers."""
	from pos_next.api.wallet import get_pending_wallet_payments as canonical_pending

	return canonical_pending(customer, company=company, exclude_invoice=exclude_invoice)


@frappe.whitelist()
def create_customer_wallet(customer, company, account=None, pos_profile=None):
	"""Create a wallet after explicit permission and POS-context checks.

	``account`` is accepted for API compatibility but intentionally ignored; the
	server selects the configured wallet account so clients cannot redirect GL
	entries to an arbitrary Receivable account.
	"""
	frappe.has_permission("Wallet", "create", throw=True)

	from pos_next.api.wallet import (
		_authorize_wallet_context,
		_get_or_create_wallet,
		get_pos_settings,
	)

	company, profile = _authorize_wallet_context(customer, company, pos_profile=pos_profile)
	pos_settings = get_pos_settings(profile.name) if profile else None
	return _get_or_create_wallet(
		customer,
		company,
		pos_settings=pos_settings,
		force_create=True,
	)


def get_default_wallet_account(company):
	"""Return a valid configured wallet Receivable account for a company."""
	wallet_account = frappe.db.get_value(
		"POS Settings",
		{"enabled": 1, "wallet_account": ["is", "set"]},
		"wallet_account",
	)
	if wallet_account:
		row = frappe.db.get_value(
			"Account", wallet_account, ["company", "account_type", "is_group", "disabled"], as_dict=True
		)
		if row and row.company == company and row.account_type == "Receivable" and not row.is_group and not row.disabled:
			return wallet_account

	return frappe.db.get_value(
		"Account",
		{
			"company": company,
			"account_type": "Receivable",
			"is_group": 0,
			"disabled": 0,
			"name": ["like", "%wallet%"],
		},
		"name",
	)


@frappe.whitelist()
def get_or_create_wallet(customer, company, pos_profile=None):
	"""Compatibility wrapper around the canonical guarded wallet API."""
	from pos_next.api.wallet import get_or_create_wallet as canonical_get_or_create

	return canonical_get_or_create(customer, company, pos_profile=pos_profile)
