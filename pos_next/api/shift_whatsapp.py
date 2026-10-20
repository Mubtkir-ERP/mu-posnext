# -*- coding: utf-8 -*-
# Copyright (c) 2026, POS Next and contributors
# For license information, please see license.txt

"""Send the shift-closing print format to the supervisor over WhatsApp.

On POS Closing Shift submit, the configured closing Print Format is rendered to
a PDF and delivered as a WhatsApp document to the supervisor number set on the
POS Profile. Entirely best-effort: a missing number, a disabled toggle, or a
WhatsApp failure must never block closing the shift.
"""

import frappe
from frappe import _
from frappe.utils import cint


def _settings(pos_profile):
	"""Read the shift-WhatsApp config from the POS Profile, defensively.

	These are newer custom fields; a site whose columns have not been migrated
	yet simply behaves as "disabled" instead of raising.
	"""
	cfg = frappe._dict({"enabled": 0, "mobile": None, "print_format": None})
	for field, key in (
		("mu_shift_whatsapp_enabled", "enabled"),
		("mu_shift_whatsapp_mobile", "mobile"),
		("mu_shift_whatsapp_print_format", "print_format"),
	):
		try:
			cfg[key] = frappe.db.get_value("POS Profile", pos_profile, field)
		except Exception:
			cfg[key] = None
	return cfg


def notify_shift_close(doc, method=None):
	"""doc_events hook: WhatsApp the closing print format to the supervisor."""
	try:
		pos_profile = doc.get("pos_profile")
		if not pos_profile:
			return

		cfg = _settings(pos_profile)
		if not cint(cfg.get("enabled")) or not cfg.get("mobile"):
			return

		# Render the shift-closing print format to a PDF (uses the configured
		# format, or the DocType's default when left empty).
		print_format = cfg.get("print_format") or None
		pdf = frappe.get_print(
			"POS Closing Shift", doc.name, print_format=print_format, as_pdf=True
		)

		# Persist as a temporary PUBLIC file — Evolution/Meta must fetch it over
		# HTTP. The ``wa-temp-`` prefix is cleaned up automatically after 48h.
		safe = f"POS-Closing-{doc.name}.pdf".replace("/", "-")
		temp_name = f"wa-temp-{frappe.generate_hash(length=8)}-{safe}"
		file_doc = frappe.get_doc(
			{"doctype": "File", "file_name": temp_name, "content": pdf, "is_private": 0}
		).insert(ignore_permissions=True)

		cashier = doc.get("user") or frappe.session.user
		caption = _("POS Shift Closing Details {0} — Cashier: {1}").format(doc.name, cashier)

		# Build and queue the outgoing WhatsApp document message via the app's
		# central router (same mechanism the scheduled-report feature uses).
		from frappe_whatsapp.utils.messaging import (
			get_default_channel,
			normalize_number,
			resolve_instance_name,
		)

		data = {
			"doctype": "WhatsApp Message",
			"type": "Outgoing",
			"to": normalize_number(cfg.get("mobile")),
			"message": caption,
			"message_type": "Manual",
			"content_type": "document",
			"attach": file_doc.file_url,
			"channel": get_default_channel(),
		}
		if data["channel"] == "Evolution":
			data["send_from_instance"] = resolve_instance_name(
				None, user=doc.get("owner") or frappe.session.user
			)
		frappe.get_doc(data).insert(ignore_permissions=True)
	except Exception:
		# Never block closing the shift because of a notification problem.
		frappe.log_error(frappe.get_traceback(), "Shift close WhatsApp failed")
