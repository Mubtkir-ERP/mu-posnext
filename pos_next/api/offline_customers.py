"""Idempotent offline customer synchronization for POSNext."""

import re
import uuid

import frappe
from frappe import _

from pos_next.api.customers import create_customer


def _existing_result(offline_id):
    record = frappe.db.get_value(
        "Offline Customer Sync",
        {"offline_id": offline_id},
        ["status", "customer"],
        as_dict=True,
        for_update=True,
    )

    if record and record.status == "Synced" and record.customer:
        return {
            "offline_id": offline_id,
            "customer": record.customer,
            "already_synced": True,
        }

    frappe.throw(
        _("CUSTOMER_SYNC_IN_PROGRESS: Retry customer synchronization later."),
        frappe.ValidationError,
    )


@frappe.whitelist()
def sync_customer(offline_id, customer_data, pos_profile=None):
    """Create one Customer per stable offline ID, including on retries."""

    if not re.fullmatch(
        r"pos_customer_[0-9a-fA-F-]{36}",
        str(offline_id or ""),
    ):
        frappe.throw(_("Invalid offline customer ID"))

    if not frappe.has_permission("Customer", "create"):
        frappe.throw(
            _("You don't have permission to create customers"),
            frappe.PermissionError,
        )

    if isinstance(customer_data, str):
        customer_data = frappe.parse_json(customer_data)

    if not isinstance(customer_data, dict):
        frappe.throw(_("Invalid customer data"))

    customer_name = str(customer_data.get("customer_name") or "").strip()
    if not customer_name:
        frappe.throw(_("Customer Name is required"))

    if pos_profile and not frappe.db.exists("POS Profile", pos_profile):
        frappe.throw(_("Invalid POS Profile"))

    save_point = "offline_customer_" + uuid.uuid4().hex
    frappe.db.savepoint(save_point)

    try:
        reservation = frappe.get_doc({
            "doctype": "Offline Customer Sync",
            "offline_id": offline_id,
            "status": "Pending",
            "pos_profile": pos_profile,
        })
        reservation.flags.ignore_permissions = True
        reservation.insert()
        frappe.db.release_savepoint(save_point)

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
        return _existing_result(offline_id)

    customer = create_customer(
        customer_name=customer_name,
        mobile_no=customer_data.get("mobile_no"),
        email_id=customer_data.get("email_id"),
        customer_group=customer_data.get("customer_group"),
        territory=customer_data.get("territory"),
        pos_profile=pos_profile,
        custom_governorate=customer_data.get("custom_governorate"),
        custom_district=customer_data.get("custom_district"),
    )

    reservation.customer = customer["name"]
    reservation.status = "Synced"
    reservation.synced_at = frappe.utils.now_datetime()
    reservation.flags.ignore_permissions = True
    reservation.save()

    return {
        "offline_id": offline_id,
        "customer": customer["name"],
        "already_synced": False,
    }
