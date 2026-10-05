# -*- coding: utf-8 -*-
# Copyright (c) 2024, POS Next and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import json
import frappe
from frappe import _
from frappe.utils import nowdate, nowtime, get_datetime
from pos_next.api.utilities import get_wallet_payment_modes
from pos_next.api.security import require_pos_profile_access, require_shift_access


@frappe.whitelist()
def get_opening_dialog_data():
	"""Get data required for opening shift dialog"""
	data = {}

	# Get POS Profiles where current user is defined in POS Profile User table
	pos_profiles_data = frappe.db.sql(
		"""
		SELECT DISTINCT p.name, p.company, p.currency, p.warehouse, p.selling_price_list
		FROM `tabPOS Profile` p
		INNER JOIN `tabPOS Profile User` u ON u.parent = p.name
		WHERE p.disabled = 0 AND u.user = %s
		ORDER BY p.name
		""",
		frappe.session.user,
		as_dict=1,
	)

	data["pos_profiles_data"] = pos_profiles_data

	# Derive companies from accessible POS Profiles
	company_names = []
	for profile in pos_profiles_data:
		if profile.company and profile.company not in company_names:
			company_names.append(profile.company)
	data["companies"] = [{"name": c} for c in company_names]

	# Get payment methods for POS profiles (exclude wallet payment methods)
	pos_profiles_list = [p.name for p in pos_profiles_data]

	if pos_profiles_list:
		# Exclude wallet payment modes from opening balance
		wallet_modes = get_wallet_payment_modes()

		payment_filters = {"parent": ["in", pos_profiles_list]}
		if wallet_modes:
			payment_filters["mode_of_payment"] = ["not in", wallet_modes]

		data["payments_method"] = frappe.get_list(
			"POS Payment Method",
			filters=payment_filters,
			fields=["*"],
			limit_page_length=0,
			order_by="parent",
			ignore_permissions=True,
		)

		# Set currency from pos profile
		for mode in data["payments_method"]:
			mode["currency"] = frappe.get_cached_value("POS Profile", mode["parent"], "currency")
	else:
		data["payments_method"] = []

	return data


@frappe.whitelist()
def check_opening_shift(user=None):
	"""Check if the current user has an open shift.

	A caller cannot inspect another cashier's shift through this endpoint.
	"""
	requested_user = user or frappe.session.user
	if requested_user != frappe.session.user and frappe.session.user != "Administrator" and "System Manager" not in frappe.get_roles(frappe.session.user):
		frappe.throw(_("You cannot inspect another user's POS shift."), frappe.PermissionError)
	user = requested_user

	open_shifts = frappe.db.get_all(
		"POS Opening Shift",
		filters={
			"user": user,
			"pos_closing_shift": ["is", "not set"],
			"docstatus": 1,
			"status": "Open",
		},
		fields=["name", "pos_profile", "period_start_date"],
		order_by="period_start_date desc",
	)

	if not open_shifts:
		return None

	# Get the latest open shift
	shift_data = open_shifts[0]
	data = {}
	data["pos_opening_shift"] = frappe.get_doc("POS Opening Shift", shift_data["name"])
	data["pos_profile"] = frappe.get_doc("POS Profile", shift_data["pos_profile"])
	data["company"] = frappe.get_doc("Company", data["pos_profile"].company)
	# Include server timestamp so frontend can compute shift duration
	# without timezone mismatch (period_start_date is in server timezone)
	data["server_now"] = str(get_datetime())

	return data


@frappe.whitelist()
def create_opening_shift(pos_profile, company, balance_details):
	"""Create a new POS Opening Shift"""
	balance_details = json.loads(balance_details) if isinstance(balance_details, str) else balance_details

	# Authorize the cashier against the profile and never trust company from the client.
	profile = require_pos_profile_access(pos_profile, company=company)
	company = profile.company

	# Check if user already has an open shift
	existing_shift = check_opening_shift(frappe.session.user)
	if existing_shift:
		frappe.throw(_("You already have an open shift: {0}").format(existing_shift["pos_opening_shift"].name))

	new_pos_opening = frappe.get_doc(
		{
			"doctype": "POS Opening Shift",
			"period_start_date": get_datetime(),
			"posting_date": nowdate(),
			"posting_time": nowtime(),
			"user": frappe.session.user,
			"pos_profile": pos_profile,
			"company": company,
			"status": "Open",
		}
	)

	# Add balance details only for payment modes configured on this profile.
	allowed_modes = set(
		frappe.get_all(
			"POS Payment Method",
			filters={"parent": pos_profile, "parenttype": "POS Profile"},
			pluck="mode_of_payment",
		)
	)
	formatted_balance_details = []
	for detail in balance_details or []:
		mode = detail.get("mode_of_payment")
		if not mode or mode not in allowed_modes:
			frappe.throw(
				_("Mode of Payment {0} is not configured for POS Profile {1}.").format(mode or "", pos_profile),
				frappe.PermissionError,
			)
		formatted_balance_details.append({
			"mode_of_payment": mode,
			"amount": detail.get("opening_amount", 0)
		})

	new_pos_opening.set("balance_details", formatted_balance_details)
	# Bounded permission bypass after profile/user/company authorization above.
	new_pos_opening.flags.ignore_permissions = True
	try:
		new_pos_opening.insert(ignore_permissions=True)
		new_pos_opening.submit()
	finally:
		new_pos_opening.flags.ignore_permissions = False

	data = {}
	data["pos_opening_shift"] = new_pos_opening.as_dict()
	data["pos_profile"] = frappe.get_doc("POS Profile", pos_profile)
	data["company"] = frappe.get_doc("Company", company)

	return data


@frappe.whitelist()
def get_closing_shift_data(opening_shift):
	"""Get data for closing shift for the current cashier only."""
	from pos_next.pos_next.doctype.pos_closing_shift.pos_closing_shift import make_closing_shift_from_opening

	try:
		require_shift_access(opening_shift, require_open=True)
		# Get the trusted opening shift document
		opening_shift_doc = frappe.get_doc("POS Opening Shift", opening_shift)

		# Convert to dict with proper datetime serialization
		opening_shift_dict = opening_shift_doc.as_dict()
		opening_shift_json = json.dumps(opening_shift_dict, default=str)

		# Create closing shift from opening shift (returns a dict)
		closing_data = make_closing_shift_from_opening(opening_shift_json)

		# Ensure datetime values are JSON serializable
		return json.loads(json.dumps(closing_data, default=str))
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Closing Shift Data Error")
		frappe.throw(_("Error getting closing shift data: {0}").format(str(e)))


@frappe.whitelist()
def submit_closing_shift(closing_shift):
	"""Submit a POS Closing Shift after validating the session context."""
	from pos_next.pos_next.doctype.pos_closing_shift.pos_closing_shift import submit_closing_shift as submit_shift

	try:
		payload = json.loads(closing_shift) if isinstance(closing_shift, str) else dict(closing_shift or {})
		if payload.get("doctype") not in (None, "", "POS Closing Shift"):
			frappe.throw(_("Invalid document type for POS closing."), frappe.PermissionError)
		opening_shift = payload.get("pos_opening_shift")
		require_shift_access(
			opening_shift,
			pos_profile=payload.get("pos_profile"),
			company=payload.get("company"),
			require_open=True,
		)
		result = submit_shift(json.dumps(payload))
		return {"name": result, "status": "success"}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Submit Closing Shift Error")
		frappe.throw(_("Error submitting closing shift: {0}").format(str(e)))
