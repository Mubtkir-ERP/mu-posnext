# Copyright (c) 2026, Solvfast and contributors
# For license information, please see license.txt
"""Kitchen ticket routing and multi-method printing for POS Next.

Supports:
- Station resolution from Item.mu_kitchen_station (override) -> Item Group.custom_kitchen_station
- Multiple printing methods per station: QZ Tray, Network IP (ESC/POS), Browser Print
- RTL Arabic/English kitchen ticket formatting with modifiers & notes
"""

import json
import socket

import frappe
from frappe import _
from frappe.utils import cint, format_datetime, now_datetime
from pos_next.api.security import require_pos_profile_access


@frappe.whitelist()
def get_kitchen_tickets(pos_profile, items, invoice_name=None, order_note=None, customer_name=None, order_number=None, order_type=None):
	require_pos_profile_access(pos_profile)
	items = json.loads(items) if isinstance(items, str) else (items or [])
	if not items:
		return []

	printer_map = _get_station_printer_map(pos_profile)
	item_codes = list({(it.get("item_code")) for it in items if it.get("item_code")})
	station_by_item = _get_item_station_map(item_codes)

	groups = {}
	for it in items:
		station = station_by_item.get(it.get("item_code")) or ""
		groups.setdefault(station, []).append(it)

	when = format_datetime(now_datetime(), "yyyy-MM-dd HH:mm")
	tickets = []
	for station, lines in groups.items():
		cfg = printer_map.get(station)
		if not cfg:
			continue
		station_title = _resolve_station_title(station)
		custom_print_format = cfg.get("print_format") or ""
		html = None
		if custom_print_format and invoice_name and frappe.db.exists("Sales Invoice", invoice_name):
			try:
				html = frappe.get_print(
					"Sales Invoice",
					invoice_name,
					print_format=custom_print_format,
					as_pdf=False,
				)
			except Exception as exc:
				frappe.log_error(
					title="Kitchen Custom Print Format Error",
					message=f"Failed to render Print Format '{custom_print_format}' for {invoice_name}: {exc}",
				)
		if not html:
			html = _render_ticket(station_title, lines, when, invoice_name, order_note, customer_name, order_number, order_type)
		tickets.append({
			"station": station,
			"station_title": station_title,
			"print_method": cfg.get("print_method") or "QZ Tray",
			"printer_name": cfg.get("printer_name") or "",
			"printer_ip": cfg.get("printer_ip") or "",
			"printer_port": cint(cfg.get("printer_port")) or 9100,
			"print_format": custom_print_format,
			"html": html,
			"lines": lines,
			"when": when,
		})

	return tickets


def _resolve_station_title(station_id):
	if not station_id:
		return _("Kitchen")
	if frappe.db.exists("DocType", "POS Kitchen Station"):
		title = frappe.db.get_value("POS Kitchen Station", station_id, "station_name")
		if title:
			return title
	return station_id


def _get_station_printer_map(pos_profile):
	if not pos_profile:
		return {}
	fields = ["kitchen_station", "printer_name"]
	for col in ("printer", "print_method", "printer_ip", "printer_port", "print_format"):
		if frappe.db.has_column("POS Kitchen Printer", col):
			fields.append(col)

	rows = frappe.get_all(
		"POS Kitchen Printer",
		filters={"parent": pos_profile, "parenttype": "POS Profile", "parentfield": "mu_kitchen_printers"},
		fields=fields,
	)
	printer_ids = list({r.get("printer") for r in rows if r.get("printer")})
	printer_docs = {}
	if printer_ids and frappe.db.exists("DocType", "POS Printer"):
		for p in frappe.get_all(
			"POS Printer",
			filters={"name": ["in", printer_ids]},
			fields=["name", "printer_name", "ip_address", "port"],
		):
			printer_docs[p.name] = p

	result = {}
	for r in rows:
		if not r.kitchen_station:
			continue
		p_doc = printer_docs.get(r.get("printer")) or {}
		p_name = p_doc.get("printer_name") or r.get("printer_name") or ""
		p_ip = p_doc.get("ip_address") or r.get("printer_ip") or ""
		p_port = cint(p_doc.get("port") or r.get("printer_port")) or 9100
		method = r.get("print_method") or "QZ Tray"
		if method == "QZ Tray" and not p_name:
			continue
		if method == "Network IP (ESC/POS)" and not p_ip:
			continue
		result[r.kitchen_station] = {
			"print_method": method,
			"printer_name": p_name,
			"printer_ip": p_ip,
			"printer_port": p_port,
			"print_format": r.get("print_format") or "",
		}
	return result


def _get_item_station_map(item_codes):
	"""item_code -> kitchen station (Item.mu_kitchen_station override, then Item Group.custom_kitchen_station)."""
	if not item_codes:
		return {}
	fields = ["name", "item_group"]
	has_override = frappe.db.has_column("Item", "mu_kitchen_station")
	if has_override:
		fields.append("mu_kitchen_station")

	item_rows = frappe.get_all("Item", filters={"name": ["in", item_codes]}, fields=fields)
	groups = list({r.item_group for r in item_rows if r.item_group})
	station_by_group = {}
	if groups:
		grp_rows = frappe.get_all(
			"Item Group",
			filters={"name": ["in", groups]},
			fields=["name", "custom_kitchen_station"],
		)
		station_by_group = {r.name: (r.custom_kitchen_station or "") for r in grp_rows}

	return {
		r.name: (r.get("mu_kitchen_station") if has_override and r.get("mu_kitchen_station") else station_by_group.get(r.item_group, ""))
		for r in item_rows
	}


def _render_ticket(station_title, lines, when, invoice_name, order_note, customer_name=None, order_number=None, order_type=None):
	rows_html = []
	for it in lines:
		qty = cint(it.get("qty")) or it.get("qty") or 1
		name = frappe.utils.escape_html(it.get("item_name") or it.get("item_code") or "")
		rows_html.append(f'<div class="ln"><span class="q">{qty}×</span> <span class="nm">{name}</span></div>')
		summary = it.get("modifier_summary")
		if summary:
			rows_html.append(f'<div class="mod">▪ {frappe.utils.escape_html(summary)}</div>')
		note = it.get("item_note")
		if note:
			rows_html.append(f'<div class="note">📝 {frappe.utils.escape_html(note)}</div>')

	order_note_html = f'<div class="onote">📝 {frappe.utils.escape_html(order_note)}</div>' if order_note else ""
	cust_html = f'<div class="meta">{frappe.utils.escape_html(customer_name)}</div>' if customer_name else ""
	order_num_html = f'<div class="ord">طلب #{cint(order_number)}</div>' if cint(order_number) else ""
	order_type_label = "🍽️ محلي (Dine-In)" if order_type == "Dine-In" else ("🛍️ سفري (Takeaway)" if order_type == "Takeaway" else "")
	order_type_html = f'<div class="otype">{order_type_label}</div>' if order_type_label else ""
	header_id = frappe.utils.escape_html(invoice_name or "")
	station_esc = frappe.utils.escape_html(station_title or _("Kitchen"))

	return f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head><meta charset="utf-8"><style>
body{{font-family:Tahoma,Arial,sans-serif;width:72mm;margin:0;padding:4mm;color:#000;font-size:13px;}}
.hd{{text-align:center;border-bottom:2px dashed #000;padding-bottom:6px;margin-bottom:8px;}}
.st{{font-size:18px;font-weight:bold;}}
.ord{{font-size:22px;font-weight:bold;margin:4px 0;border:2px solid #000;display:inline-block;padding:2px 10px;border-radius:6px;}}
.otype{{font-size:14px;font-weight:bold;margin-top:3px;}}
.meta{{font-size:12px;margin-top:3px;}}
.ln{{font-size:15px;font-weight:bold;margin:6px 0 2px;}}
.q{{display:inline-block;min-width:26px;}}
.mod{{font-size:12px;padding-right:14px;color:#222;margin-bottom:2px;}}
.note,.onote{{font-size:12px;padding-right:14px;font-style:italic;margin-bottom:4px;}}
.onote{{border-top:1px dashed #000;padding-top:6px;margin-top:8px;}}
</style></head>
<body>
<div class="hd">
  <div class="st">{station_esc}</div>
  {order_num_html}
  {order_type_html}
  <div class="meta">{header_id} • {when}</div>
  {cust_html}
</div>
{''.join(rows_html)}
{order_note_html}
</body></html>"""


@frappe.whitelist()
def print_network_ticket(printer_ip, printer_port=9100, station_title=None, invoice_name=None, lines=None, customer_name=None, order_note=None, order_number=None, order_type=None):
	"""Send raw ESC/POS kitchen ticket over TCP to a local network thermal printer."""
	if not printer_ip:
		frappe.throw(_("Printer IP Address is required."))
	port = cint(printer_port) or 9100
	items = json.loads(lines) if isinstance(lines, str) else (lines or [])

	parts = [
		b"\x1b@",        # Initialize printer
		b"\x1b\x61\x01", # Center align
		(f"{station_title or 'Kitchen'}\n").encode("utf-8", "replace"),
	]
	if cint(order_number):
		parts.append((f"ORDER #{cint(order_number)}\n").encode("utf-8", "replace"))
	if order_type:
		parts.append((f"[{order_type}]\n").encode("utf-8", "replace"))
	parts.append((f"{invoice_name or ''}  {format_datetime(now_datetime(), 'yyyy-MM-dd HH:mm')}\n").encode("utf-8", "replace"))
	if customer_name:
		parts.append((f"{customer_name}\n").encode("utf-8", "replace"))
	parts.append(b"--------------------------------\n")
	parts.append(b"\x1b\x61\x02")  # Right align for Arabic/RTL

	for it in items:
		qty = cint(it.get("qty")) or it.get("qty") or 1
		name = it.get("item_name") or it.get("item_code") or ""
		parts.append((f"{qty}x {name}\n").encode("utf-8", "replace"))
		if it.get("modifier_summary"):
			parts.append((f"  - {it.get('modifier_summary')}\n").encode("utf-8", "replace"))
		if it.get("item_note"):
			parts.append((f"  * {it.get('item_note')}\n").encode("utf-8", "replace"))

	if order_note:
		parts.append(b"--------------------------------\n")
		parts.append((f"Note: {order_note}\n").encode("utf-8", "replace"))

	parts.append(b"\n\n\n\x1dV\x41\x03")  # Feed & cut
	payload = b"".join(parts)

	with socket.create_connection((printer_ip.strip(), port), timeout=5) as sock:
		sock.sendall(payload)

	return {"status": "ok", "printer_ip": printer_ip, "printer_port": port}
