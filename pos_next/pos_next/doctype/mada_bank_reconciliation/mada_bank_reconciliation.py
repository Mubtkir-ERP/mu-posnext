# Copyright (c) 2026, MUBTKIR and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate


class MadaBankReconciliation(Document):
    @frappe.whitelist()
    def run_matching(self):
        """
        يطابق صفوف كشف البنك مع سجلات 'Mada Settlement' عبر رقم الموازنة.
        المنطق:
          - رقم الموازنة موجود في الطرفين + المبلغ متساوٍ  -> Matched
          - رقم موجود لكن المبلغ مختلف                      -> Amount Mismatch
          - موازنة مسجّلة بلا صف بنكي                        -> Not in Bank
          - صف بنكي بلا موازنة مسجّلة                         -> Extra in Bank (عدّ فقط)
        """
        matched = not_in_bank = mismatch = extra = 0

        # فهرسة صفوف البنك حسب رقم الموازنة (قد يتكرر الرقم فيُجمع)
        bank_by_no = {}
        for row in (self.statement_rows or []):
            key = (row.settlement_no or "").strip()
            if not key:
                continue
            bank_by_no.setdefault(key, []).append(row)

        # جلب الموازنات ضمن الفترة
        filters = {}
        if self.from_date:
            filters["settlement_date"] = [">=", getdate(self.from_date)]
        settlements = frappe.get_all(
            "Mada Settlement",
            filters=filters,
            fields=["name", "settlement_no", "amount", "settlement_date"],
        )

        settlement_nos = set()
        for s in settlements:
            if self.to_date and getdate(s.settlement_date) > getdate(self.to_date):
                continue

            key = (s.settlement_no or "").strip()
            settlement_nos.add(key)
            rows = bank_by_no.get(key)

            if not rows:
                frappe.db.set_value(
                    "Mada Settlement",
                    s.name,
                    {
                        "status": "Not in Bank",
                        "bank_amount": 0,
                        "difference": -flt(s.amount),
                        "bank_matched_on": None,
                    },
                )
                not_in_bank += 1
                continue

            bank_amount = sum(flt(r.amount) for r in rows)
            diff = flt(bank_amount) - flt(s.amount)
            status = "Matched" if abs(diff) < 0.005 else "Amount Mismatch"

            frappe.db.set_value(
                "Mada Settlement",
                s.name,
                {
                    "status": status,
                    "bank_amount": bank_amount,
                    "difference": diff,
                    "bank_matched_on": self.reconciliation_date,
                },
            )
            if status == "Matched":
                matched += 1
            else:
                mismatch += 1

        # صفوف بنكية بلا موازنة مقابلة
        for key, rows in bank_by_no.items():
            if key not in settlement_nos:
                extra += len(rows)

        self.db_set("matched_count", matched)
        self.db_set("not_in_bank_count", not_in_bank)
        self.db_set("mismatch_count", mismatch)
        self.db_set("extra_count", extra)
        frappe.db.commit()

        return {
            "matched": matched,
            "not_in_bank": not_in_bank,
            "mismatch": mismatch,
            "extra": extra,
        }
