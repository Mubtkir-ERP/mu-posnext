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

		# Guard against invalid stock-sync interval
		if cint(self.get("enable_auto_stock_sync")):
			if cint(self.get("stock_sync_interval")) < 10:
				frappe.throw("Stock Sync Interval must be at least 10 seconds")

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

	# ERPNext Stock Settings is the global source of truth.  Keep the legacy
	# POSSettings field as a read-only mirror for frontend compatibility.
	global_allow_negative = cint(
		frappe.db.get_single_value("Stock Settings", "allow_negative_stock") or 0
	)
	settings["allow_negative_stock"] = global_allow_negative
	settings["_global_allow_negative_stock"] = global_allow_negative

	# Discount / rate-editing policy is owned by the POS Profile only
	# (قرار الجرد: الخصومات وتعديل السعر من البروفايل فقط).
	from pos_next.api.constants import apply_profile_discount_policy
	profile = frappe.get_cached_doc("POS Profile", pos_profile)
	apply_profile_discount_policy(settings, profile)

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

	# POSNext manager dialog may change operational fields only.
	# Per-branch discount/rate/printing-template and cash controls belong to POS Profile.
	allowed = {"silent_print", "enable_auto_stock_sync", "stock_sync_interval"}
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
