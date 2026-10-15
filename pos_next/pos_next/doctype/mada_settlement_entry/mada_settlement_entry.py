# Copyright (c) 2026, MUBTKIR and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class MadaSettlementEntry(Document):
    @frappe.whitelist()
    def create_settlements(self):
        """ينشئ سجل Mada Settlement مستقل لكل جهاز في الجدول."""
        created = 0
        for row in (self.devices or []):
            if not row.terminal or not row.settlement_no or not flt(row.amount):
                continue
            if row.created_settlement and frappe.db.exists("Mada Settlement", row.created_settlement):
                continue

            doc = frappe.new_doc("Mada Settlement")
            doc.settlement_date = self.entry_date
            doc.terminal = row.terminal
            doc.settlement_no = row.settlement_no
            doc.amount = row.amount
            doc.source = "Standalone"
            doc.insert(ignore_permissions=True)

            frappe.db.set_value(
                "Mada Settlement Entry Row", row.name, "created_settlement", doc.name
            )
            created += 1

        self.db_set("created_count", created)
        frappe.db.commit()

        if not created:
            frappe.msgprint(_("لم يتم إنشاء أي سجل (ربما أُنشئت سابقًا أو الصفوف ناقصة)."))
        return {"created": created}
