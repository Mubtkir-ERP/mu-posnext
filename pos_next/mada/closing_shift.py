# Copyright (c) 2026, MUBTKIR and contributors
# For license information, please see license.txt
#
# تكامل مطابقة مدى مع إقفال الوردية.
# مربوط عبر hooks: doc_events["POS Closing Shift"].

import frappe
from frappe.utils import flt


def create_mada_settlements(doc, method=None):
    """عند اعتماد إقفال الوردية: ينشئ سجل Mada Settlement لكل جهاز في جدول مدى."""
    settings = frappe.get_cached_doc("Mada Reconciliation Settings")
    if not settings.enable_reconciliation or not settings.feed_from_closing_shift:
        return

    rows = doc.get("mu_mada_settlements") or []
    rows = [r for r in rows if r.terminal and r.settlement_no and flt(r.amount)]
    if not rows:
        return

    settlement_date = doc.get("posting_date") or doc.get("period_end_date")
    pos_mada_total = get_shift_mada_total(doc) if settings.compare_pos_total else 0
    single = len(rows) == 1

    for row in rows:
        if row.get("created_settlement") and frappe.db.exists("Mada Settlement", row.created_settlement):
            continue

        settlement = frappe.new_doc("Mada Settlement")
        settlement.settlement_date = settlement_date
        settlement.terminal = row.terminal
        settlement.settlement_no = row.settlement_no
        settlement.amount = row.amount
        settlement.source = "Closing Shift"
        settlement.pos_closing_shift = doc.name
        # عند وجود جهاز واحد فقط يمكن ربط إجمالي مدى في POS للمقارنة الرقابية
        if settings.compare_pos_total and single:
            settlement.pos_mada_total = pos_mada_total
        settlement.insert(ignore_permissions=True)

        frappe.db.set_value(
            "Mada Shift Settlement", row.name, "created_settlement", settlement.name
        )


def cancel_mada_settlements(doc, method=None):
    """عند إلغاء إقفال الوردية: يحذف سجلات مدى المُنشأة منه."""
    for row in (doc.get("mu_mada_settlements") or []):
        name = row.get("created_settlement")
        if name and frappe.db.exists("Mada Settlement", name):
            frappe.delete_doc("Mada Settlement", name, ignore_permissions=True, force=True)
            frappe.db.set_value("Mada Shift Settlement", row.name, "created_settlement", None)


def get_shift_mada_total(doc):
    """إجمالي مدى في النظام من جدول تسوية المدفوعات (طرق الدفع التي تحوي 'مدى' أو 'mada')."""
    total = 0
    for pay in (doc.get("payment_reconciliation") or []):
        mop = (pay.get("mode_of_payment") or "")
        if "mada" in mop.lower() or "مدى" in mop:
            total += flt(pay.get("closing_amount") or pay.get("expected_amount") or 0)
    return total
