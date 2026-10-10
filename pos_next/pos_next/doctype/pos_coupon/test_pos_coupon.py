# Copyright (c) 2021, Youssef Restom and Contributors
# See license.txt

import unittest
from unittest.mock import Mock, patch

from pos_next.pos_next.doctype.pos_coupon.pos_coupon import (
    _get_coupon_usage_count,
    _get_customer_coupon_usage_count,
    apply_coupon_discount,
)


class TestPOSCoupon(unittest.TestCase):
    @patch("pos_next.pos_next.doctype.pos_coupon.pos_coupon.frappe.get_meta")
    @patch("pos_next.pos_next.doctype.pos_coupon.pos_coupon.frappe.db")
    def test_one_use_coupon_counts_all_submitted_sales_doctypes(self, mock_db, mock_get_meta):
        def table_exists(doctype):
            return doctype in {"Sales Invoice", "POS Invoice", "Sales Order"}

        def count(doctype, filters=None):
            counts = {"Sales Invoice": 1, "POS Invoice": 2, "Sales Order": 1}
            return counts[doctype]

        mock_db.table_exists.side_effect = table_exists
        mock_db.count.side_effect = count
        mock_get_meta.return_value = Mock(has_field=Mock(return_value=True))

        used_count = _get_customer_coupon_usage_count("Customer A", "save10")

        self.assertEqual(used_count, 4)
        for doctype in ("Sales Invoice", "POS Invoice", "Sales Order"):
            mock_db.count.assert_any_call(
                doctype,
                filters={"customer": "Customer A", "coupon_code": "SAVE10", "docstatus": 1},
            )

    @patch("pos_next.pos_next.doctype.pos_coupon.pos_coupon.frappe.get_meta")
    @patch("pos_next.pos_next.doctype.pos_coupon.pos_coupon.frappe.db")
    def test_coupon_usage_skips_doctypes_without_coupon_field(self, mock_db, mock_get_meta):
        mock_db.table_exists.return_value = True
        mock_db.count.return_value = 4

        def get_meta(doctype):
            if doctype == "Sales Invoice":
                return Mock(has_field=Mock(return_value=True))
            return Mock(has_field=Mock(return_value=False))

        mock_get_meta.side_effect = get_meta

        used_count = _get_coupon_usage_count("save10")

        self.assertEqual(used_count, 4)
        mock_db.count.assert_called_once_with(
            "Sales Invoice",
            filters={"coupon_code": "SAVE10", "docstatus": 1},
        )

    def test_coupon_discount_is_clamped_to_base_and_maximum(self):
        coupon = Mock(
            apply_on="Net Total",
            min_amount=0,
            discount_type="Percentage",
            discount_percentage=50,
            discount_amount=0,
            max_amount=30,
        )

        result = apply_coupon_discount(coupon, cart_total=200, net_total=100)

        self.assertTrue(result["valid"])
        self.assertEqual(result["base_amount"], 100)
        self.assertEqual(result["discount"], 30)
    def test_erpnext_coupon_uses_linked_transaction_pricing_rule(self):
        coupon = Mock(doctype="Coupon Code")
        rule = Mock(
            apply_on="Transaction",
            min_amt=0,
            max_amt=0,
            apply_discount_on="Grand Total",
            price_or_product_discount="Price",
            rate_or_discount="Discount Percentage",
            discount_percentage=10,
            discount_amount=0,
            name="PRLE-TEST",
        )

        result = apply_coupon_discount(
            coupon,
            cart_total=230,
            net_total=200,
            pricing_rule=rule,
        )

        self.assertTrue(result["valid"])
        self.assertEqual(result["discount"], 23)
        self.assertEqual(result["source"], "ERPNext")
        self.assertEqual(result["pricing_rule"], "PRLE-TEST")

