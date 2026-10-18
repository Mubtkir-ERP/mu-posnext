# -*- coding: utf-8 -*-
# Copyright (c) 2026, POS Next and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, nowdate, cstr


def on_closing_shift_submit(doc, method=None):
    """
    Hook executed when POS Closing Shift is submitted.
    1. Executes automatic cash sweeping (Journal Entry).
    2. Creates draft van stock return (Material Transfer).
    """
    if not doc.pos_profile:
        return

    profile = frappe.get_cached_doc("POS Profile", doc.pos_profile)
    
    # 1. Automatic Cash Sweeping
    try:
        execute_cash_sweeping(doc, profile)
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), _("POS Cash Sweeping Failed"))
        frappe.msgprint(_("Warning: Automatic cash sweeping failed: {0}").format(str(e)), indicator="orange")

    # 2. Van Stock Return (Draft)
    try:
        execute_van_stock_return(doc, profile)
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), _("POS Van Stock Return Failed"))
        frappe.msgprint(_("Warning: Van stock return creation failed: {0}").format(str(e)), indicator="orange")


def execute_cash_sweeping(doc, profile):
    """
    Sweeps cash automatically upon shift close:
    - Driver Cash Account -> Shop Cash Account (if driver shift)
    - Shop Cash Account -> Main Cash / Bank Account (sweep to HQ)
    - Adjusts any shortage or excess to Cash Difference Account.
    - Also records non-taxable charges (delivery/dafour) in cash.
    """
    if not profile.get("mu_auto_sweep_cash"):
        return

    shop_cash = profile.get("mu_shop_cash_account")
    main_cash = profile.get("mu_main_cash_account")
    driver_cash = profile.get("mu_driver_cash_account")
    diff_account = profile.get("mu_cash_difference_account")
    non_taxable_income = profile.get("mu_non_taxable_income_account")

    if not shop_cash or not main_cash:
        return

    # Calculate actual cash collected in shift
    actual_cash_collected = 0.0
    expected_cash = 0.0
    cash_diff = 0.0

    for p in doc.get("payment_reconciliation") or []:
        # Check if row is cash
        is_cash = False
        if p.mode_of_payment:
            type_of_payment = frappe.db.get_value("Mode of Payment", p.mode_of_payment, "type")
            if type_of_payment == "Cash" or "cash" in p.mode_of_payment.lower() or "نقد" in p.mode_of_payment:
                is_cash = True
        if is_cash:
            actual_cash_collected += flt(p.closing_amount)
            expected_cash += flt(p.expected_amount)
            cash_diff += flt(p.difference)

    # Add non-taxable delivery/dafour amount collected
    non_taxable_amt = flt(doc.get("mu_non_taxable_amount") or 0)
    total_cash_to_sweep = actual_cash_collected + non_taxable_amt

    if total_cash_to_sweep <= 0 and cash_diff == 0:
        return

    company = doc.company or profile.company
    cost_center = profile.cost_center or frappe.get_cached_value("Company", company, "cost_center")

    # Step A: If this is a driver shift with a driver cash account, transfer from driver to shop
    if driver_cash and driver_cash != shop_cash and total_cash_to_sweep > 0:
        driver_je = frappe.new_doc("Journal Entry")
        driver_je.voucher_type = "Cash Entry"
        driver_je.company = company
        driver_je.posting_date = doc.posting_date or nowdate()
        driver_je.user_remark = _("Driver cash clearance for shift {0} ({1})").format(doc.name, doc.user)

        driver_je.append("accounts", {
            "account": shop_cash,
            "debit_in_account_currency": total_cash_to_sweep,
            "credit_in_account_currency": 0,
            "cost_center": cost_center
        })
        driver_je.append("accounts", {
            "account": driver_cash,
            "debit_in_account_currency": 0,
            "credit_in_account_currency": total_cash_to_sweep,
            "cost_center": cost_center
        })
        driver_je.insert(ignore_permissions=True)
        driver_je.submit()

    # Step B: Sweep from Shop Cash to Main HQ Cash / Bank Account
    je = frappe.new_doc("Journal Entry")
    je.voucher_type = "Cash Entry"
    je.company = company
    je.posting_date = doc.posting_date or nowdate()
    je.user_remark = _("Automatic cash sweep to Main Cash for shift {0} ({1})").format(doc.name, doc.user)

    # Debit Main Cash (HQ receives the cash)
    je.append("accounts", {
        "account": main_cash,
        "debit_in_account_currency": total_cash_to_sweep,
        "credit_in_account_currency": 0,
        "cost_center": cost_center
    })

    # Credit Shop Cash
    je.append("accounts", {
        "account": shop_cash,
        "debit_in_account_currency": 0,
        "credit_in_account_currency": total_cash_to_sweep,
        "cost_center": cost_center
    })

    # If there is non-taxable delivery/dafour revenue and an income account is set
    # record it as income offset against shop cash
    if non_taxable_amt > 0 and non_taxable_income:
        je.append("accounts", {
            "account": shop_cash,
            "debit_in_account_currency": non_taxable_amt,
            "credit_in_account_currency": 0,
            "cost_center": cost_center
        })
        je.append("accounts", {
            "account": non_taxable_income,
            "debit_in_account_currency": 0,
            "credit_in_account_currency": non_taxable_amt,
            "cost_center": cost_center
        })

    # If cash difference exists and diff_account is set
    if cash_diff != 0 and diff_account:
        if cash_diff < 0:
            # Shortage (عجز) -> Expense
            je.append("accounts", {
                "account": diff_account,
                "debit_in_account_currency": abs(cash_diff),
                "credit_in_account_currency": 0,
                "cost_center": cost_center
            })
            je.append("accounts", {
                "account": shop_cash,
                "debit_in_account_currency": 0,
                "credit_in_account_currency": abs(cash_diff),
                "cost_center": cost_center
            })
        else:
            # Excess (زيادة) -> Income
            je.append("accounts", {
                "account": shop_cash,
                "debit_in_account_currency": cash_diff,
                "credit_in_account_currency": 0,
                "cost_center": cost_center
            })
            je.append("accounts", {
                "account": diff_account,
                "debit_in_account_currency": 0,
                "credit_in_account_currency": cash_diff,
                "cost_center": cost_center
            })

    je.insert(ignore_permissions=True)
    je.submit()
    
    # Store link in closing shift
    frappe.db.set_value("POS Closing Shift", doc.name, "mu_cash_sweep_entry", je.name)
    frappe.msgprint(_("Automatic cash sweep Journal Entry created: {0}").format(je.name), indicator="green")


def execute_van_stock_return(doc, profile):
    """
    Creates a draft Stock Entry (Material Transfer) for remaining items
    in the van warehouse back to the main shop warehouse.
    Remains Draft (docstatus=0) until verified by warehouse staff.
    """
    if not profile.get("mu_enable_van_stock_cycle"):
        return

    van_warehouse = profile.get("mu_van_warehouse")
    shop_warehouse = profile.get("mu_shop_warehouse")

    if not van_warehouse or not shop_warehouse or van_warehouse == shop_warehouse:
        return

    # Query current stock balance in van warehouse
    items = frappe.db.sql("""
        SELECT item_code, actual_qty, stock_uom
        FROM `tabBin`
        WHERE warehouse = %s AND actual_qty > 0
    """, (van_warehouse,), as_dict=True)

    if not items:
        return

    company = doc.company or profile.company

    stock_entry = frappe.new_doc("Stock Entry")
    stock_entry.purpose = "Material Transfer"
    stock_entry.stock_entry_type = "Material Transfer"
    stock_entry.company = company
    stock_entry.from_warehouse = van_warehouse
    stock_entry.to_warehouse = shop_warehouse
    stock_entry.posting_date = doc.posting_date or nowdate()
    stock_entry.remarks = _("Van Stock Return for shift {0} ({1}) - Pending Warehouse Confirmation").format(doc.name, doc.user)

    for it in items:
        stock_entry.append("items", {
            "item_code": it.item_code,
            "qty": flt(it.actual_qty),
            "uom": it.stock_uom or frappe.db.get_value("Item", it.item_code, "stock_uom"),
            "stock_uom": it.stock_uom or frappe.db.get_value("Item", it.item_code, "stock_uom"),
            "conversion_factor": 1.0,
            "s_warehouse": van_warehouse,
            "t_warehouse": shop_warehouse,
        })

    # Saved as DRAFT (docstatus=0) as requested!
    stock_entry.insert(ignore_permissions=True)
    
    frappe.db.set_value("POS Closing Shift", doc.name, "mu_stock_return_entry", stock_entry.name)
    frappe.msgprint(_("Draft Van Stock Return created: {0} (Pending verification)").format(stock_entry.name), indicator="blue")


@frappe.whitelist()
def create_morning_van_dispatch(pos_profile, items=None):
    """
    Creates morning stock dispatch from Shop Warehouse to Van Warehouse.
    Can be triggered at shift opening or on demand.
    """
    profile = frappe.get_cached_doc("POS Profile", pos_profile)
    if not profile.get("mu_enable_van_stock_cycle"):
        frappe.throw(_("Van stock cycle is not enabled in POS Profile {0}").format(pos_profile))

    van_warehouse = profile.get("mu_van_warehouse")
    shop_warehouse = profile.get("mu_shop_warehouse")

    if not van_warehouse or not shop_warehouse:
        frappe.throw(_("Please configure Shop Warehouse and Van Warehouse in POS Profile"))

    if not items:
        frappe.throw(_("No items specified for morning dispatch"))

    if isinstance(items, str):
        import json
        items = json.loads(items)

    stock_entry = frappe.new_doc("Stock Entry")
    stock_entry.purpose = "Material Transfer"
    stock_entry.stock_entry_type = "Material Transfer"
    stock_entry.company = profile.company
    stock_entry.from_warehouse = shop_warehouse
    stock_entry.to_warehouse = van_warehouse
    stock_entry.posting_date = nowdate()
    stock_entry.remarks = _("Morning Van Stock Dispatch for profile {0}").format(pos_profile)

    for it in items:
        stock_entry.append("items", {
            "item_code": it["item_code"],
            "qty": flt(it["qty"]),
            "s_warehouse": shop_warehouse,
            "t_warehouse": van_warehouse,
            "conversion_factor": 1.0
        })

    stock_entry.insert(ignore_permissions=True)
    stock_entry.submit()
    return {"status": "success", "stock_entry": stock_entry.name}
