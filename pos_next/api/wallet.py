# Copyright (c) 2024, BrainWise and contributors
# For license information, please see license.txt

"""Wallet API for POS Next.

Phase 3 / security point 2 keeps wallet and loyalty amounts server-authoritative.
Public endpoints only select a customer/profile context; balances, wallet accounts,
loyalty points and conversion factors are always read from ERPNext on the server.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from pos_next.api.security import (
	require_company_access,
	require_customer_read,
	require_pos_profile_access,
)
from pos_next.api.payment_security import resolve_pos_payment_account


def _authorize_wallet_context(customer, company, pos_profile=None):
	"""Authorize a wallet request and return the trusted company/profile.

	When a POS Profile is supplied it is the source of truth for the company and
	customer-group boundary.  Requests without a profile must pass the normal
	company/customer permission checks instead.
	"""
	if not customer:
		frappe.throw(_("Customer is required."), frappe.ValidationError)
	if not company:
		frappe.throw(_("Company is required."), frappe.ValidationError)

	profile = None
	if pos_profile:
		profile = require_pos_profile_access(pos_profile, company=company)
		company = profile.company
		require_customer_read(customer, pos_profile=profile.name)
	else:
		require_company_access(company)
		require_customer_read(customer)

	return company, profile


def _get_active_wallet(customer, company):
	"""Return the active wallet row for the exact customer/company pair."""
	if not customer or not company:
		return None

	return frappe.db.get_value(
		"Wallet",
		{"customer": customer, "company": company, "status": ["in", ["Active", "active"]]},
		["name", "customer", "company", "account", "status", "current_balance"],
		as_dict=True,
	)


def _lock_wallet(wallet_name):
	"""Serialize spend validation for one wallet inside the current DB transaction."""
	if not wallet_name:
		return

	# Use the wallet row as a transaction-scoped mutex.  Keep the statement
	# compatible with both MariaDB and PostgreSQL installations.
	table = '"tabWallet"' if getattr(frappe.db, "db_type", None) == "postgres" else "`tabWallet`"
	frappe.db.sql(f"SELECT name FROM {table} WHERE name = %s FOR UPDATE", (wallet_name,))


def _get_customer_wallet_balance(customer, company, exclude_invoice=None):
	"""Internal, permission-free balance calculation for already-authorized flows."""
	from erpnext.accounts.utils import get_balance_on

	wallet = _get_active_wallet(customer, company)
	if not wallet or not wallet.account:
		return 0.0

	gl_balance = get_balance_on(
		account=wallet.account,
		party_type="Customer",
		party=customer,
	)

	# A negative receivable balance means the company owes the customer.
	wallet_balance = -flt(gl_balance)
	pending_wallet_amount = get_pending_wallet_payments(
		customer,
		company=company,
		exclude_invoice=exclude_invoice,
	)
	available_balance = flt(wallet_balance) - flt(pending_wallet_amount)
	return available_balance if available_balance > 0 else 0.0


def get_pending_wallet_payments(customer, company=None, exclude_invoice=None):
	"""Return wallet amounts reserved by open POS invoices.

	This helper is intentionally internal.  It is company-scoped so a customer's
	wallet in one company cannot be reduced by invoices from another company.
	"""
	# Submitted POS wallet payments are already reflected in GL, so counting them
	# again here would reduce the available balance twice.  Reserve only draft
	# invoices that have not posted their wallet spend to GL yet.
	filters = {
		"customer": customer,
		"docstatus": 0,
		"is_pos": 1,
	}
	if company:
		filters["company"] = company

	invoices = frappe.get_all("Sales Invoice", filters=filters, fields=["name"])
	pending_amount = 0.0

	for invoice in invoices:
		if exclude_invoice and invoice.name == exclude_invoice:
			continue

		payments = frappe.get_all(
			"Sales Invoice Payment",
			filters={"parent": invoice.name, "parenttype": "Sales Invoice"},
			fields=["mode_of_payment", "amount"],
		)
		for payment in payments:
			if payment.mode_of_payment and cint(
				frappe.db.get_value("Mode of Payment", payment.mode_of_payment, "is_wallet_payment") or 0
			):
				pending_amount += max(0.0, flt(payment.amount))

	return pending_amount


def _get_wallet_payment_rows(payments):
	rows = []
	for payment in payments or []:
		mode = payment.get("mode_of_payment") if hasattr(payment, "get") else None
		if not mode:
			continue
		if cint(frappe.db.get_value("Mode of Payment", mode, "is_wallet_payment") or 0):
			rows.append(payment)
	return rows


def get_wallet_amount_from_payments(payments):
	"""Calculate the signed total of wallet payment rows."""
	return sum(flt(row.get("amount") or 0) for row in _get_wallet_payment_rows(payments))


def _get_mode_account(mode_of_payment, company, pos_profile=None):
	"""Return the company account configured on the Mode of Payment."""
	# ERPNext's POS Payment Method child table stores only the mode/default flag;
	# the actual company account is stored in Mode of Payment Account.
	return frappe.db.get_value(
		"Mode of Payment Account",
		{"parent": mode_of_payment, "company": company},
		"default_account",
	)


def _validate_wallet_payment_configuration(doc, wallet_rows, pos_settings, wallet):
	"""Validate payment method/account wiring and replace client account values."""
	if not cint(pos_settings.get("enable_loyalty_program")):
		frappe.throw(_("Wallet payments are disabled for this POS Profile."), frappe.ValidationError)

	wallet_account = pos_settings.get("wallet_account")
	if not wallet_account:
		frappe.throw(_("Wallet Account is not configured for this POS Profile."), frappe.ValidationError)

	if not wallet or wallet.account != wallet_account:
		frappe.throw(
			_("The customer's wallet is not configured with the POS wallet account."),
			frappe.ValidationError,
		)

	for payment in wallet_rows:
		mode = payment.get("mode_of_payment")

		# Phase 3 / Point 4: central payment security now also verifies that the
		# wallet mode is enabled, present on the POS Profile, and mapped to an
		# active leaf account in the same company. Wallet's own Point 2 rules
		# still decide which Receivable account is valid.
		payment_context = resolve_pos_payment_account(
			doc.pos_profile,
			mode,
			company=doc.company,
			allow_wallet=True,
			required_account_types=None,
		)
		if not payment_context.is_wallet_payment:
			frappe.throw(
				_("Mode of Payment {0} is not configured as a wallet payment method.").format(mode),
				frappe.ValidationError,
			)
		if payment_context.account != wallet_account:
			frappe.throw(
				_("Wallet payment method {0} is configured with a different account.").format(mode),
				frappe.ValidationError,
			)

		# The browser is never authoritative for the payment account.
		payment.account = wallet_account


def validate_wallet_payment(doc, method=None):
	"""Validate wallet payment on Sales Invoice using server-side values only."""
	if not cint(doc.get("is_pos")):
		return

	wallet_rows = _get_wallet_payment_rows(doc.get("payments") or [])
	if not wallet_rows:
		return

	if not doc.get("customer") or not doc.get("company") or not doc.get("pos_profile"):
		frappe.throw(_("Customer, company and POS Profile are required for wallet payment."))

	profile = require_pos_profile_access(doc.pos_profile, company=doc.company)
	require_customer_read(doc.customer, pos_profile=profile.name)

	pos_settings = get_pos_settings(profile.name)
	if not pos_settings:
		frappe.throw(_("POS Settings are required for wallet payment."), frappe.ValidationError)

	wallet = _get_active_wallet(doc.customer, profile.company)
	if not wallet:
		frappe.throw(_("No active wallet exists for this customer."), frappe.ValidationError)

	_validate_wallet_payment_configuration(doc, wallet_rows, pos_settings, wallet)

	# Sale wallet rows must spend credit; return rows may be negative and add
	# credit back, but a positive wallet withdrawal on a return is not allowed.
	for payment in wallet_rows:
		amount = flt(payment.get("amount") or 0)
		if cint(doc.get("is_return")):
			if amount > 0:
				frappe.throw(_("Wallet payment on a return invoice cannot be positive."))
		else:
			if amount < 0:
				frappe.throw(_("Wallet payment amount cannot be negative."))

	if cint(doc.get("is_return")):
		return

	wallet_amount = sum(max(0.0, flt(row.get("amount") or 0)) for row in wallet_rows)
	if wallet_amount <= 0:
		return

	payable_total = flt(doc.get("rounded_total") or doc.get("grand_total") or 0)
	if wallet_amount > payable_total + 0.005:
		frappe.throw(
			_("Wallet payment cannot exceed the invoice total."),
			frappe.ValidationError,
		)

	# Lock before checking the live balance.  Concurrent checkouts for the same
	# wallet then validate one after another rather than spending the same credit.
	_lock_wallet(wallet.name)
	wallet_balance = _get_customer_wallet_balance(
		doc.customer,
		profile.company,
		exclude_invoice=doc.get("name"),
	)
	if wallet_amount > wallet_balance + 0.005:
		frappe.throw(
			_("Insufficient wallet balance. Available: {0}, Requested: {1}").format(
				frappe.format_value(wallet_balance, {"fieldtype": "Currency"}),
				frappe.format_value(wallet_amount, {"fieldtype": "Currency"}),
			),
			title=_("Wallet Balance Error"),
		)


def _get_loyalty_credit_details(invoice):
	"""Return authoritative loyalty-to-wallet conversion details for an invoice."""
	if isinstance(invoice, str):
		doc = frappe.get_doc("Sales Invoice", invoice)
	else:
		doc = invoice

	if not doc or doc.doctype != "Sales Invoice" or cint(doc.docstatus) != 1:
		frappe.throw(_("A submitted Sales Invoice is required for loyalty conversion."))
	if cint(doc.get("is_return")):
		frappe.throw(_("Return invoices cannot create loyalty wallet credit."))

	# The earned Loyalty Point Entry is the authoritative source for which
	# program produced the points.  Do not trust the customer's current loyalty
	# program because it can be changed after the invoice was submitted.
	loyalty_entry = frappe.db.get_value(
		"Loyalty Point Entry",
		{
			"invoice_type": "Sales Invoice",
			"invoice": doc.name,
			"customer": doc.customer,
			"loyalty_points": [">", 0],
		},
		["name", "loyalty_points", "loyalty_program"],
		as_dict=True,
	)
	if (
		not loyalty_entry
		or flt(loyalty_entry.loyalty_points) <= 0
		or not loyalty_entry.loyalty_program
	):
		return None

	loyalty_program = loyalty_entry.loyalty_program
	program = frappe.db.get_value(
		"Loyalty Program",
		loyalty_program,
		["name", "company", "conversion_factor", "expense_account"],
		as_dict=True,
	)
	if not program or program.company != doc.company:
		return None

	conversion_factor = flt(program.conversion_factor)
	if conversion_factor <= 0:
		frappe.throw(
			_("Loyalty Program {0} has an invalid conversion factor.").format(loyalty_program),
			frappe.ValidationError,
		)

	credit_amount = flt(loyalty_entry.loyalty_points) * conversion_factor
	if credit_amount <= 0:
		return None

	return frappe._dict(
		invoice=doc.name,
		customer=doc.customer,
		company=doc.company,
		pos_profile=doc.get("pos_profile"),
		loyalty_program=loyalty_program,
		loyalty_entry=loyalty_entry.name,
		loyalty_points=flt(loyalty_entry.loyalty_points),
		conversion_factor=conversion_factor,
		credit_amount=credit_amount,
		expense_account=program.expense_account
		or frappe.get_cached_value("Company", doc.company, "default_expense_account"),
	)


def process_loyalty_to_wallet(doc, method=None):
	"""Convert points earned by a submitted invoice to wallet credit.

	The invoice, Loyalty Point Entry and Loyalty Program are read again from the
	server.  No point count, conversion factor or credit amount comes from the UI.
	"""
	if not cint(doc.get("is_pos")) or cint(doc.get("is_return")):
		return

	pos_settings = get_pos_settings(doc.get("pos_profile"))
	if not pos_settings:
		return
	if not cint(pos_settings.get("enable_loyalty_program")) or not cint(pos_settings.get("loyalty_to_wallet")):
		return

	details = _get_loyalty_credit_details(doc)
	if not details:
		return

	configured_program = pos_settings.get("default_loyalty_program")
	if configured_program and configured_program != details.loyalty_program:
		return

	# Keep the existing minimum-spend behavior, but evaluate it from the server's
	# Loyalty Program rules and the submitted invoice total.
	lp_doc = frappe.get_doc("Loyalty Program", details.loyalty_program)
	tiers = sorted([d.as_dict() for d in (lp_doc.get("collection_rules") or [])], key=lambda r: flt(r.get("min_spent")))
	if tiers and not any(abs(flt(doc.grand_total)) >= flt(t.get("min_spent")) for t in tiers):
		return

	try:
		wallet = _get_or_create_wallet(
			details.customer,
			details.company,
			pos_settings=pos_settings,
			force_create=True,
		)
		if not wallet:
			return

		from pos_next.pos_next.doctype.wallet_transaction.wallet_transaction import create_wallet_credit

		transaction = create_wallet_credit(
			wallet=wallet.name if hasattr(wallet, "name") else wallet["name"],
			amount=details.credit_amount,
			source_type="Loyalty Program",
			remarks=_("Loyalty points conversion from {0}: {1} points = {2}").format(
				details.invoice,
				details.loyalty_points,
				frappe.format_value(details.credit_amount, {"fieldtype": "Currency"}),
			),
			reference_doctype="Sales Invoice",
			reference_name=details.invoice,
			submit=True,
		)

		if transaction:
			frappe.msgprint(
				_("Loyalty points converted to wallet: {0} points = {1}").format(
					details.loyalty_points,
					frappe.format_value(details.credit_amount, {"fieldtype": "Currency"}),
				),
				alert=True,
				indicator="green",
			)
	except Exception as exc:
		frappe.log_error(
			title="Loyalty to Wallet Conversion Error",
			message=f"Invoice: {doc.name}, Error: {exc}\n{frappe.get_traceback()}",
		)
		raise


def _validate_excluded_invoice(customer, company, exclude_invoice, pos_profile=None):
	"""Validate a client-supplied invoice exclusion before it changes a balance read."""
	if not exclude_invoice:
		return None

	invoice = frappe.db.get_value(
		"Sales Invoice",
		exclude_invoice,
		["name", "customer", "company", "pos_profile", "docstatus"],
		as_dict=True,
	)
	if not invoice or invoice.customer != customer or invoice.company != company:
		frappe.throw(_("Invoice exclusion is not valid for this wallet."), frappe.PermissionError)
	if pos_profile and invoice.pos_profile != pos_profile:
		frappe.throw(_("Invoice exclusion does not belong to this POS Profile."), frappe.PermissionError)
	return invoice.name


@frappe.whitelist()
def get_customer_wallet_balance(customer, company=None, exclude_invoice=None, pos_profile=None):
	"""Get the customer's available wallet balance after authorization."""
	company, profile = _authorize_wallet_context(customer, company, pos_profile=pos_profile)
	exclude_invoice = _validate_excluded_invoice(
		customer,
		company,
		exclude_invoice,
		pos_profile=profile.name if profile else None,
	)
	return _get_customer_wallet_balance(customer, company, exclude_invoice=exclude_invoice)


@frappe.whitelist()
def get_customer_wallet(customer, company=None, pos_profile=None):
	"""Get wallet details for a customer after authorization."""
	company, _profile = _authorize_wallet_context(customer, company, pos_profile=pos_profile)
	wallet = _get_active_wallet(customer, company)
	if wallet:
		wallet["balance"] = _get_customer_wallet_balance(customer, company)
	return wallet


def create_wallet_on_customer_insert(doc, method=None):
	"""Create a wallet automatically only when the configured POS profile allows it."""
	company = frappe.get_cached_value("Global Defaults", "Global Defaults", "default_company")
	if not company:
		return

	pos_profile = frappe.db.get_value("POS Profile", {"company": company, "disabled": 0}, "name")
	if not pos_profile:
		return

	pos_settings = get_pos_settings(pos_profile)
	if not pos_settings or not cint(pos_settings.get("auto_create_wallet")):
		return

	try:
		_get_or_create_wallet(doc.name, company, pos_settings=pos_settings, force_create=True)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"Wallet auto-create failed for {doc.name}")


def _validate_wallet_account(account, company):
	if not account:
		return False
	row = frappe.db.get_value(
		"Account", account, ["company", "account_type", "is_group", "disabled"], as_dict=True
	)
	return bool(
		row
		and row.company == company
		and row.account_type == "Receivable"
		and not cint(row.is_group)
		and not cint(row.disabled)
	)


def _get_or_create_wallet(customer, company, pos_settings=None, force_create=False):
	"""Internal wallet creation helper.  Caller must already be authorized."""
	wallet = frappe.db.get_value(
		"Wallet",
		{"customer": customer, "company": company},
		["name", "customer", "company", "account", "status"],
		as_dict=True,
	)

	# When a POS Settings row is supplied, its wallet account is authoritative.
	# Never silently fall back to another Receivable account because that would
	# make loyalty credits and POS wallet payments post to different ledgers.
	configured_wallet_account = pos_settings.get("wallet_account") if pos_settings else None
	if pos_settings:
		if not _validate_wallet_account(configured_wallet_account, company):
			frappe.throw(
				_("Please configure a valid Receivable wallet account for company {0}.").format(company),
				frappe.ValidationError,
			)
		if wallet and wallet.account != configured_wallet_account:
			frappe.throw(
				_("The customer's wallet account does not match the POS wallet account."),
				frappe.ValidationError,
			)

	if wallet:
		return wallet

	if not pos_settings:
		pos_profile = frappe.db.get_value("POS Profile", {"company": company, "disabled": 0}, "name")
		if pos_profile:
			pos_settings = get_pos_settings(pos_profile)
			configured_wallet_account = pos_settings.get("wallet_account") if pos_settings else None

	if not force_create and (not pos_settings or not cint(pos_settings.get("auto_create_wallet"))):
		return None

	wallet_account = configured_wallet_account
	if pos_settings and not _validate_wallet_account(wallet_account, company):
		frappe.throw(
			_("Please configure a valid Receivable wallet account for company {0}.").format(company),
			frappe.ValidationError,
		)

	# Legacy/internal calls without POS Settings may still discover a sensible
	# company Receivable account, but public POS flows always pass settings.
	if not pos_settings and not _validate_wallet_account(wallet_account, company):
		wallet_account = frappe.db.get_value(
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

	if not pos_settings and not _validate_wallet_account(wallet_account, company):
		wallet_account = frappe.get_cached_value("Company", company, "default_receivable_account")

	if not _validate_wallet_account(wallet_account, company):
		frappe.throw(
			_("Please configure a valid Receivable wallet account for company {0}.").format(company),
			frappe.ValidationError,
		)

	try:
		wallet_doc = frappe.get_doc(
			{
				"doctype": "Wallet",
				"customer": customer,
				"company": company,
				"account": wallet_account,
				"status": "Active",
			}
		)
		wallet_doc.insert(ignore_permissions=True)
		return wallet_doc
	except frappe.DuplicateEntryError:
		return frappe.db.get_value(
			"Wallet",
			{"customer": customer, "company": company},
			["name", "customer", "company", "account", "status"],
			as_dict=True,
		)


@frappe.whitelist()
def get_or_create_wallet(customer, company, pos_profile=None):
	"""Public compatibility API; creation policy comes only from POS Settings."""
	company, profile = _authorize_wallet_context(customer, company, pos_profile=pos_profile)
	pos_settings = get_pos_settings(profile.name) if profile else None
	return _get_or_create_wallet(customer, company, pos_settings=pos_settings, force_create=False)


def get_pos_settings(pos_profile):
	"""Get wallet/loyalty settings for a POS Profile."""
	if not pos_profile:
		return None
	return frappe.db.get_value(
		"POS Settings",
		{"pos_profile": pos_profile, "enabled": 1},
		[
			"enable_loyalty_program",
			"default_loyalty_program",
			"wallet_account",
			"auto_create_wallet",
			"loyalty_to_wallet",
		],
		as_dict=True,
	)


@frappe.whitelist()
def get_wallet_payment_methods(pos_profile):
	"""Get wallet-enabled payment methods for an authorized POS Profile."""
	require_pos_profile_access(pos_profile)
	payment_methods = frappe.get_all(
		"POS Payment Method",
		filters={"parent": pos_profile, "parenttype": "POS Profile"},
		fields=["mode_of_payment", "default"],
	)
	wallet_methods = []
	for method in payment_methods:
		mode = frappe.db.get_value(
			"Mode of Payment",
			method.mode_of_payment,
			["enabled", "is_wallet_payment"],
			as_dict=True,
		)
		if mode and cint(mode.enabled) and cint(mode.is_wallet_payment):
			wallet_methods.append(
				{
					"mode_of_payment": method.mode_of_payment,
					"default": method.default,
					"is_wallet_payment": True,
				}
			)
	return wallet_methods


@frappe.whitelist()
def get_wallet_info(customer, company, pos_profile=None):
	"""Get wallet information for the POS UI from a trusted server context."""
	company, profile = _authorize_wallet_context(customer, company, pos_profile=pos_profile)
	result = {
		"wallet_enabled": False,
		"wallet_exists": False,
		"wallet_balance": 0.0,
		"wallet_account": None,
		"wallet_name": None,
		"auto_create": False,
		"loyalty_program": None,
		"loyalty_to_wallet": False,
	}

	if not profile:
		return result

	pos_settings = get_pos_settings(profile.name)
	if pos_settings:
		result["wallet_enabled"] = cint(pos_settings.get("enable_loyalty_program"))
		result["wallet_account"] = pos_settings.get("wallet_account")
		result["auto_create"] = cint(pos_settings.get("auto_create_wallet"))
		result["loyalty_program"] = pos_settings.get("default_loyalty_program")
		result["loyalty_to_wallet"] = cint(pos_settings.get("loyalty_to_wallet"))

	if not result["wallet_enabled"]:
		return result

	wallet = _get_active_wallet(customer, company)
	if wallet:
		result["wallet_exists"] = True
		result["wallet_name"] = wallet.name
		result["wallet_balance"] = _get_customer_wallet_balance(customer, company)
	elif result["auto_create"]:
		new_wallet = _get_or_create_wallet(customer, company, pos_settings=pos_settings, force_create=True)
		if new_wallet:
			result["wallet_exists"] = True
			result["wallet_name"] = new_wallet.name if hasattr(new_wallet, "name") else new_wallet.get("name")
			result["wallet_balance"] = 0.0

	return result


@frappe.whitelist()
def create_manual_wallet_credit(customer, company, amount, remarks=None, pos_profile=None):
	"""Create an explicitly authorized manual wallet adjustment."""
	frappe.has_permission("Wallet Transaction", "create", throw=True)
	company, profile = _authorize_wallet_context(customer, company, pos_profile=pos_profile)

	amount = flt(amount)
	if amount <= 0:
		frappe.throw(_("Amount must be greater than zero"))

	pos_settings = get_pos_settings(profile.name) if profile else None
	wallet = _get_or_create_wallet(customer, company, pos_settings=pos_settings, force_create=True)
	if not wallet:
		frappe.throw(_("Could not create wallet for customer {0}").format(customer))

	from pos_next.pos_next.doctype.wallet_transaction.wallet_transaction import create_wallet_credit

	transaction = create_wallet_credit(
		wallet=wallet.name if hasattr(wallet, "name") else wallet["name"],
		amount=amount,
		source_type="Manual Adjustment",
		remarks=remarks or _("Manual wallet credit"),
		submit=True,
	)
	return transaction.name
