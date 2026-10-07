# Copyright (c) 2026, Solvfast and contributors
# For license information, please see license.txt
"""Kitchen ticket routing for POS Next.

Groups the ordered items by their kitchen station (set on the Item Group as
`custom_kitchen_station`) and renders one compact ticket per station. Each
station is mapped to a printer in POS Settings (`kitchen_printers` table). The
frontend then sends each ticket's HTML to its printer via QZ Tray.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, format_datetime, now_datetime
from pos_next.api.security import require_pos_profile_access


@frappe.whitelist()
def get_kitchen_tickets(pos_profile, items, invoice_name=None, order_note=None):
	require_pos_profile_access(pos_profile)
	"""Return a list of {station, printer_name, html} tickets to print.

	Args:
		pos_profile: POS Profile name (to resolve station→printer map).
		items: JSON list of ordered lines, each:
			{item_code, item_name, qty, modifier_summary, item_note}
		invoice_name: optional invoice id to show on the ticket.
		order_note: optional whole-order note.
	"""
	items = json.loads(items) if isinstance(items, str) else (items or [])
	if not items:
		return []

	printer_map = _get_station_printer_map(pos_profile)

	# Resolve each item's station from its Item Group in one bulk query.
	item_codes = list({(it.get("item_code")) for it in items if it.get("item_code")})
	station_by_item = _get_item_station_map(item_codes)

	# Group lines by station
	groups = {}
	for it in items:
		station = station_by_item.get(it.get("item_code")) or ""
		groups.setdefault(station, []).append(it)

	when = format_datetime(now_datetime(), "yyyy-MM-dd HH:mm")
	tickets = []
	for station, lines in groups.items():
		printer_name = printer_map.get(station)
		# Skip stations with no configured printer (nothing to send).
		if not printer_name:
			continue
		html = _render_ticket(station, printer_name, lines, when, invoice_name, order_note)
		tickets.append({"station": station, "printer_name": printer_name, "html": html})

	return tickets


def _get_station_printer_map(pos_profile):
	"""station name -> printer name, from POS Settings.kitchen_printers."""
	settings_name = frappe.db.get_value("POS Settings", {"pos_profile": pos_profile}, "name")
	if not settings_name:
		return {}
	rows = frappe.get_all(
		"POS Kitchen Printer",
		filters={"parent": settings_name, "parenttype": "POS Settings"},
		fields=["kitchen_station", "printer_name"],
	)
	return {r.kitchen_station: r.printer_name for r in rows if r.kitchen_station and r.printer_name}


def _get_item_station_map(item_codes):
	"""item_code -> kitchen station (from its Item Group.custom_kitchen_station)."""
	if not item_codes:
		return {}
	item_rows = frappe.get_all(
		"Item", filters={"name": ["in", item_codes]}, fields=["name", "item_group"]
	)
	groups = list({r.item_group for r in item_rows if r.item_group})
	station_by_group = {}
	if groups:
		grp_rows = frappe.get_all(
			"Item Group",
			filters={"name": ["in", groups]},
			fields=["name", "custom_kitchen_station"],
		)
		station_by_group = {r.name: (r.custom_kitchen_station or "") for r in grp_rows}
	return {r.name: station_by_group.get(r.item_group, "") for r in item_rows}


def _render_ticket(station, printer_name, lines, when, invoice_name, order_note):
	rows_html = []
	# Order ETA = the slowest line on this ticket (kitchen cooks in parallel).
	max_prep = max((cint(it.get("prep_time")) for it in lines), default=0)
	for it in lines:
		qty = cint(it.get("qty")) or it.get("qty") or 1
		name = frappe.utils.escape_html(it.get("item_name") or it.get("item_code") or "")
		prep = cint(it.get("prep_time"))
		prep_html = f' <span class="pt">⏱{prep}د</span>' if prep else ""
		rows_html.append(
			f'<div class="ln"><span class="q">{qty}×</span> <span class="nm">{name}</span>{prep_html}</div>'
		)
		summary = it.get("modifier_summary")
		if summary:
			rows_html.append(f'<div class="mod">▪ {frappe.utils.escape_html(summary)}</div>')
		note = it.get("item_note")
		if note:
			rows_html.append(f'<div class="note">📝 {frappe.utils.escape_html(note)}</div>')

	order_note_html = ""
	if order_note:
		order_note_html = f'<div class="onote">📝 {frappe.utils.escape_html(order_note)}</div>'

	header_id = frappe.utils.escape_html(invoice_name or "")
	station_label = frappe.utils.escape_html(station or _("Kitchen"))
	eta_html = f'<div class="eta">⏱ {_("Ready in")} ~{max_prep} {_("min")}</div>' if max_prep else ""

	return f"""
<div class="kt">
	<style>
		.kt {{ font-family: 'Tajawal','Cairo',sans-serif; width: 100%; color:#000; }}
		.kt .st {{ font-size: 20px; font-weight: 900; text-align:center; border-bottom:2px dashed #000; padding-bottom:6px; margin-bottom:6px; }}
		.kt .meta {{ font-size: 11px; text-align:center; margin-bottom:4px; }}
		.kt .eta {{ font-size: 14px; font-weight: 900; text-align:center; margin-bottom:8px; }}
		.kt .ln {{ font-size: 16px; font-weight: 800; margin-top:6px; }}
		.kt .q {{ display:inline-block; min-width: 28px; }}
		.kt .pt {{ font-size: 12px; font-weight: 700; }}
		.kt .mod {{ font-size: 13px; font-weight:700; margin-inline-start:28px; }}
		.kt .note {{ font-size: 12px; font-style: italic; margin-inline-start:28px; }}
		.kt .onote {{ font-size: 13px; font-weight:700; border-top:1px dashed #000; margin-top:8px; padding-top:6px; }}
	</style>
	<div class="st">{station_label}</div>
	<div class="meta">{header_id} — {when}</div>
	{eta_html}
	{''.join(rows_html)}
	{order_note_html}
</div>
"""
