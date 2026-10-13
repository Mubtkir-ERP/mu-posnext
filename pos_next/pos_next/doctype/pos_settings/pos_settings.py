# Copyright (c) 2025, Youssef Restom and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt
from pos_next.api.security import require_pos_profile_access, require_pos_profile_config_access


class POSSettings(Document):
	def validate(self):
		"""Validate POS Settings.

		ERPNext Stock Settings is the authoritative global source for negative-stock
		policy.  The local field is kept only as a backwards-compatible mirror for
		older POSNext clients; saving POS Settings must never toggle ERPNext's global
		stock policy.  Item-level exceptions are read directly from Item at runtime.
		"""
		self.allow_negative_stock = cint(
			frappe.db.get_single_value("Stock Settings", "allow_negative_stock") or 0
		)

		# Guard against None values and validate discount percentage
		max_discount = flt(self.max_discount_allowed)
		if max_discount < 0 or max_discount > 100:
			frappe.throw("Max Discount Allowed must be between 0 and 100")

		# Default customer group must be a selectable leaf group.
		default_customer_group = self.get("default_customer_group")
		if default_customer_group:
			is_group = frappe.db.get_value("Customer Group", default_customer_group, "is_group")
			if cint(is_group):
				frappe.throw("Default Customer Group must be a non-group (leaf) Customer Group")

		# Guard against None values and validate search limit
		if self.use_limit_search:
			search_limit = cint(self.search_limit)
			if search_limit <= 0:
				frappe.throw("Search Limit must be greater than 0")

		# Validate use_exact_amount cannot be enabled with credit sale or partial payment
		if cint(self.use_exact_amount):
			if cint(self.allow_credit_sale):
				frappe.throw(
					"'Use Exact Amount for Non-Cash' cannot be enabled together with 'Allow Credit Sale'. "
					"Please disable Credit Sale first."
				)
			if cint(self.allow_partial_payment):
				frappe.throw(
					"'Use Exact Amount for Non-Cash' cannot be enabled together with 'Allow Partial Payment'. "
					"Please disable Partial Payment first."
				)

		self.validate_wallet_loyalty_settings()
		self.validate_cash_disbursement_write_access()
		self.validate_cash_disbursement_settings()

	def validate_cash_disbursement_write_access(self):
		"""Prevent a cashier from changing the financial disbursement wiring.

		POSNext Cashier can edit some POS Settings for operational reasons, so the
		DocType permission alone is not a sufficient boundary for these two
		financial fields. Only a user who can write the POS Profile may change
		them, including through generic Frappe document APIs.
		"""
		old = None
		if not self.is_new():
			old = frappe.db.get_value(
				"POS Settings",
				self.name,
				["pos_profile", "allow_cash_disbursement", "cash_disbursement_account"],
				as_dict=True,
			)

		new_enabled = cint(self.get("allow_cash_disbursement"))
		new_account = self.get("cash_disbursement_account") or ""
		changed = False

		if not old:
			changed = bool(new_enabled or new_account)
		else:
			changed = (
				cint(old.allow_cash_disbursement) != new_enabled
				or (old.cash_disbursement_account or "") != new_account
				or (old.pos_profile != self.pos_profile and (new_enabled or new_account or cint(old.allow_cash_disbursement) or old.cash_disbursement_account))
			)

		if changed:
			require_pos_profile_config_access(self.pos_profile, ptype="write")

	def validate_cash_disbursement_settings(self):
		"""Validate cash-disbursement accounts against trusted POS configuration."""
		if not cint(self.get("allow_cash_disbursement")):
			return

		if not self.pos_profile:
			frappe.throw(_("POS Profile is required when Cash Disbursement is enabled"))

		company = frappe.db.get_value("POS Profile", self.pos_profile, "company")
		if not company:
			frappe.throw(_("A valid POS Profile is required when Cash Disbursement is enabled"))

		account_name = self.get("cash_disbursement_account")
		if not account_name:
			frappe.throw(_("Cash Disbursement Account is required when Cash Disbursement is enabled"))

		# Reuse the runtime security rules so invalid settings are rejected at
		# configuration time instead of failing only when a cashier disburses.
		from pos_next.api.cash_disbursement import (
			_get_cash_account,
			_validate_disbursement_account,
		)

		cash_account, _cash_mode = _get_cash_account(self.pos_profile, company)
		_validate_disbursement_account(account_name, company, cash_account=cash_account)

	def validate_wallet_loyalty_settings(self):
		"""Validate wallet/loyalty configuration against the POS Profile company."""
		if not cint(self.get("enable_loyalty_program")):
			return

		if not self.pos_profile:
			frappe.throw("POS Profile is required when Wallet/Loyalty is enabled")

		company = frappe.db.get_value("POS Profile", self.pos_profile, "company")
		if not company:
			frappe.throw("A valid POS Profile is required when Wallet/Loyalty is enabled")

		wallet_account = self.get("wallet_account")
		if not wallet_account:
			frappe.throw("Wallet Account is required when Wallet/Loyalty is enabled")

		account = frappe.db.get_value(
			"Account",
			wallet_account,
			["company", "account_type", "is_group", "disabled"],
			as_dict=True,
		)
		if (
			not account
			or account.company != company
			or account.account_type != "Receivable"
			or cint(account.is_group)
			or cint(account.disabled)
		):
			frappe.throw(
				"Wallet Account must be an active leaf Receivable account for the POS Profile company"
			)

		loyalty_program = self.get("default_loyalty_program")
		if loyalty_program:
			program_company = frappe.db.get_value("Loyalty Program", loyalty_program, "company")
			if not program_company or program_company != company:
				frappe.throw("Default Loyalty Program must belong to the POS Profile company")


@frappe.whitelist()
def get_pos_settings(pos_profile):
	"""
	Get POS Settings for a specific POS Profile.

	Also injects the current global Stock Settings value to show the actual
	source of truth, preventing confusion when the checkbox appears enabled
	but the global setting was changed elsewhere.
	Also includes allow_rate_change from POS Profile.
	"""
	from frappe import _

	if not pos_profile:
		return None

	require_pos_profile_access(pos_profile)

	settings = frappe.db.get_value(
		"POS Settings",
		{"pos_profile": pos_profile},
		"*",
		as_dict=True
	)

	# If no settings exist, create default settings
	if not settings:
		settings = create_default_settings(pos_profile)

	# Get allow_rate_change from POS Profile
	allow_rate_change = frappe.db.get_value("POS Profile", pos_profile, "allow_rate_change")
	if allow_rate_change is not None:
		settings["allow_rate_change"] = cint(allow_rate_change)
	else:
		settings["allow_rate_change"] = 0

	# One effective rule across ERPNext and POSNext; never elevate permissions.
	settings["allow_user_to_edit_rate"] = int(
		bool(cint(settings.get("enabled")))
		and bool(cint(settings.get("allow_user_to_edit_rate")))
		and bool(cint(settings["allow_rate_change"]))
	)

	# ERPNext Stock Settings is the global source of truth.  Keep the legacy
	# POSSettings field as a read-only mirror for frontend compatibility.
	global_allow_negative = cint(
		frappe.db.get_single_value("Stock Settings", "allow_negative_stock") or 0
	)
	settings["allow_negative_stock"] = global_allow_negative
	settings["_global_allow_negative_stock"] = global_allow_negative
	# Read branch-specific values from POS Profile (legacy POS Settings fields
	# are retained only for compatibility with existing integrations).
	profile = frappe.get_cached_doc("POS Profile", pos_profile)
	settings["tax_inclusive"] = cint(profile.get("mu_tax_inclusive") or 0)
	settings["default_customer_group"] = profile.get("mu_default_customer_group") or ""

	return settings


def create_default_settings(pos_profile):
	"""Create default POS Settings for a POS Profile"""
	doc = frappe.new_doc("POS Settings")
	doc.pos_profile = pos_profile
	doc.enabled = 1
	doc.insert()

	return doc.as_dict()


@frappe.whitelist()
def update_pos_settings(pos_profile, settings):
	"""Update POS Settings for a POS Profile"""
	import json
	from frappe import _

	if isinstance(settings, str):
		settings = json.loads(settings)
	if not isinstance(settings, dict):
		frappe.throw(_("Invalid settings payload"))
	# Never permit the caller to overwrite identity, derived values or
	# framework-owned bookkeeping fields through this generic endpoint.
	for protected in ("name", "pos_profile", "doctype", "owner", "creation",
		"modified", "modified_by", "docstatus", "idx", "allow_rate_change"):
		settings.pop(protected, None)

	# POSNext Settings dialog may change its operational tax mode only.
	# Per-branch pricing, customers, printing and cash controls belong to POS Profile.
	allowed = set()
	unexpected = set(settings) - allowed
	if unexpected:
		frappe.throw(_("These settings must be changed in POS Profile: {0}").format(", ".join(sorted(unexpected))))

	# Negative stock is controlled by ERPNext Stock Settings / Item, never by
	# caller-supplied POS Settings.  Ignore the legacy mirror field on writes.
	settings.pop("allow_negative_stock", None)
	settings.pop("_global_allow_negative_stock", None)

	require_pos_profile_access(pos_profile)
	# Updating policy values requires configuration permission, not merely
	# permission to operate a cashier session. The modal only sends two
	# operational fields, but this endpoint also serves administrative clients.
	require_pos_profile_config_access(pos_profile, ptype="write")
	if not settings:
		return get_pos_settings(pos_profile)

	# Sensitive cash-disbursement fields are separately protected in
	# validate_cash_disbursement_write_access(), including generic DocType saves.
	# Check if settings exist
	existing = frappe.db.exists("POS Settings", {"pos_profile": pos_profile})

	if existing:
		doc = frappe.get_doc("POS Settings", existing)
		doc.update(settings)
		doc.save()
	else:
		doc = frappe.new_doc("POS Settings")
		doc.pos_profile = pos_profile
		doc.update(settings)
		doc.insert()

	return doc.as_dict()
