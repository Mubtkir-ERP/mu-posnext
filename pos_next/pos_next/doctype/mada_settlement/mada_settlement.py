# Copyright (c) 2026, MUBTKIR and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class MadaSettlement(Document):
    def validate(self):
        self.validate_duplicate()
        self.compute_unrecorded()

    def validate_duplicate(self):
        """رقم الموازنة فريد لكل جهاز."""
        if not self.settlement_no or not self.terminal:
            return

        duplicate = frappe.db.exists(
            "Mada Settlement",
            {
                "terminal": self.terminal,
                "settlement_no": self.settlement_no,
                "name": ["!=", self.name or ""],
            },
        )
        if duplicate:
            frappe.throw(
                _("A settlement with number {0} already exists for terminal {1} ({2}).").format(
                    frappe.bold(self.settlement_no),
                    frappe.bold(self.terminal),
                    duplicate,
                )
            )

    def compute_unrecorded(self):
        """الفرق بين مبلغ الموازنة وإجمالي مدى في POS (رقابة داخلية)."""
        settings = frappe.get_cached_doc("Mada Reconciliation Settings")
        if settings.compare_pos_total and flt(self.pos_mada_total):
            self.unrecorded_amount = flt(self.amount) - flt(self.pos_mada_total)
        else:
            self.unrecorded_amount = 0
