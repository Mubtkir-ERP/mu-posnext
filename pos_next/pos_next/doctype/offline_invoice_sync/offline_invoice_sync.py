# -*- coding: utf-8 -*-
# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class OfflineInvoiceSync(Document):
    """
    Tracks offline invoice synchronization to prevent duplicate submissions.

    Each record maps an offline_id (generated client-side) to a Sales Invoice,
    allowing the system to detect and prevent duplicate sync attempts.
    """

    def before_insert(self):
        """Only stamp synced_at after an invoice has actually been synced."""
        if self.status == "Synced" and not self.synced_at:
            self.synced_at = frappe.utils.now_datetime()

    @staticmethod
    def create_sync_record(offline_id, sales_invoice=None, pos_profile=None, customer=None, status="Synced"):
        """
        Create or update a sync record for an offline invoice with deadlock protection.

        Uses an InnoDB savepoint to insert directly without gap locks, and gracefully
        converges on the existing row if a duplicate key (1062) occurs.
        """
        if not offline_id:
            return None

        import uuid

        save_point = "offline_sync_" + uuid.uuid4().hex
        frappe.db.savepoint(save_point)

        try:
            doc = frappe.get_doc({
                "doctype": "Offline Invoice Sync",
                "offline_id": offline_id,
                "sales_invoice": sales_invoice or "",
                "pos_profile": pos_profile,
                "customer": customer,
                "status": status,
            })
            doc.flags.ignore_permissions = True
            doc.insert()
            frappe.db.release_savepoint(save_point)
            return doc

        except frappe.UniqueValidationError as error:
            cause = error.__cause__
            if cause is None and len(error.args) >= 3:
                cause = error.args[2]

            args = getattr(cause, "args", ())
            message = str(args[1]) if len(args) > 1 else ""
            key = message.rsplit("for key '", 1)[-1].rstrip("'")
            key = key.strip("`").split(".")[-1]

            if not (
                len(args) > 1
                and args[0] == 1062
                and "for key '" in message
                and key == "offline_id"
            ):
                raise

            frappe.db.rollback(save_point=save_point)
            frappe.db.release_savepoint(save_point)

            existing = frappe.db.get_value(
                "Offline Invoice Sync",
                {"offline_id": offline_id},
                ["name", "sales_invoice", "status", "pos_profile", "customer"],
                as_dict=True,
                for_update=True,
            )

            if not existing:
                frappe.throw(
                    frappe._("Offline invoice sync reservation conflict could not be resolved."),
                    exc=frappe.ValidationError,
                )

            sync_doc = frappe.get_doc("Offline Invoice Sync", existing.name)
            changed = False

            if sales_invoice and sync_doc.sales_invoice != sales_invoice:
                sync_doc.sales_invoice = sales_invoice
                changed = True
            if pos_profile and sync_doc.pos_profile != pos_profile:
                sync_doc.pos_profile = pos_profile
                changed = True
            if customer and sync_doc.customer != customer:
                sync_doc.customer = customer
                changed = True
            if status and sync_doc.status != status:
                sync_doc.status = status
                changed = True

            if status == "Synced":
                sync_doc.synced_at = frappe.utils.now_datetime()
                changed = True

            if changed:
                sync_doc.flags.ignore_permissions = True
                sync_doc.save()

            return sync_doc

    @staticmethod
    def get_state(offline_id):
        """Return the complete server-side state for an offline identifier."""
        if not offline_id:
            return {
                "exists": False,
                "synced": False,
                "sales_invoice": None,
                "status": None,
            }

        existing = frappe.db.get_value(
            "Offline Invoice Sync",
            {"offline_id": offline_id},
            ["name", "sales_invoice", "status", "pos_profile", "customer"],
            as_dict=True,
            for_update=True,
        )

        if not existing:
            return {
                "exists": False,
                "synced": False,
                "sales_invoice": None,
                "status": None,
            }

        is_synced = bool(existing.status == "Synced" and existing.sales_invoice)
        if is_synced and existing.sales_invoice:
            inv = frappe.db.get_value(
                "Sales Invoice",
                existing.sales_invoice,
                ["name", "docstatus"],
                as_dict=True,
                for_update=True,
            )
            is_synced = bool(inv and inv.docstatus == 1)

        return {
            "exists": True,
            "synced": is_synced,
            "sales_invoice": existing.sales_invoice or None,
            "status": existing.status,
            "name": existing.name,
            "pos_profile": existing.pos_profile,
            "customer": existing.customer,
        }

    @staticmethod
    def is_synced(offline_id):
        """Backward-compatible helper used by older callers."""
        state = OfflineInvoiceSync.get_state(offline_id)
        return {
            "synced": state.get("synced", False),
            "sales_invoice": state.get("sales_invoice"),
            "status": state.get("status"),
        }
