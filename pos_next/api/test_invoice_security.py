# Copyright (c) 2026, POS Next and contributors

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pos_next.api import invoices


def _raise(message, *args, **kwargs):
    raise RuntimeError(str(message))


class TestInvoiceSecurity(unittest.TestCase):
    @patch("pos_next.api.invoices.frappe.throw", side_effect=_raise)
    def test_rejects_arbitrary_doctype(self, _mock_throw):
        with self.assertRaisesRegex(RuntimeError, "not allowed from POS"):
            invoices._authorize_pos_transaction(
                {
                    "doctype": "Journal Entry",
                    "pos_profile": "POS-A",
                    "posa_pos_opening_shift": "SHIFT-1",
                }
            )

    @patch("pos_next.api.invoices.require_shift_access")
    @patch("pos_next.api.invoices.require_pos_profile_access")
    def test_authorization_uses_profile_and_shift_context(
        self, mock_profile_access, mock_shift_access
    ):
        profile = SimpleNamespace(name="POS-A", company="Company A")
        shift = SimpleNamespace(name="SHIFT-1", pos_profile="POS-A", company="Company A")
        mock_profile_access.return_value = profile
        mock_shift_access.return_value = shift

        doctype, result_profile, result_shift = invoices._authorize_pos_transaction(
            {
                "doctype": "Sales Invoice",
                "pos_profile": "POS-A",
                "company": "Company A",
                "posa_pos_opening_shift": "SHIFT-1",
            }
        )

        self.assertEqual(doctype, "Sales Invoice")
        self.assertIs(result_profile, profile)
        self.assertIs(result_shift, shift)
        mock_profile_access.assert_called_once_with("POS-A", company="Company A")
        mock_shift_access.assert_called_once_with(
            "SHIFT-1",
            pos_profile="POS-A",
            company="Company A",
            require_open=True,
        )

    @patch("pos_next.api.invoices.frappe.throw", side_effect=_raise)
    @patch("pos_next.api.invoices.require_shift_access")
    @patch("pos_next.api.invoices.require_pos_profile_access")
    def test_existing_document_cannot_switch_profile(
        self, mock_profile_access, _mock_shift_access, _mock_throw
    ):
        mock_profile_access.return_value = SimpleNamespace(name="POS-A", company="Company A")
        existing = Mock()
        existing.doctype = "Sales Invoice"
        existing.docstatus = 0
        existing.get.side_effect = lambda key: {
            "pos_profile": "POS-B",
            "company": "Company A",
            "posa_pos_opening_shift": "SHIFT-OLD",
        }.get(key)
        existing.pos_profile = "POS-B"
        existing.company = "Company A"

        with self.assertRaisesRegex(RuntimeError, "another POS Profile"):
            invoices._authorize_pos_transaction(
                {
                    "doctype": "Sales Invoice",
                    "pos_profile": "POS-A",
                    "posa_pos_opening_shift": "SHIFT-1",
                },
                existing_doc=existing,
            )


class TestDiscountSecurity(unittest.TestCase):
    def _profile(self):
        profile = Mock()
        profile.name = "POS-A"
        profile.company = "Company A"
        profile.get.side_effect = lambda key, default=None: {
            "currency": "SAR",
            "selling_price_list": "Standard Selling",
        }.get(key, default)
        return profile

    @patch("pos_next.api.invoices.frappe.throw", side_effect=_raise)
    @patch("pos_next.api.invoices._get_pos_discount_settings")
    def test_manual_item_discount_respects_server_setting(self, mock_settings, _mock_throw):
        mock_settings.return_value = SimpleNamespace(
            allow_user_to_edit_additional_discount=0,
            allow_user_to_edit_item_discount=0,
            allow_user_to_edit_rate=0,
            max_discount_allowed=0,
        )
        data = {
            "doctype": "Sales Invoice",
            "customer": "CUST-1",
            "items": [
                {
                    "item_code": "ITEM-1",
                    "qty": 1,
                    "rate": 90,
                    "price_list_rate": 100,
                    "discount_percentage": 10,
                    "discount_amount": 10,
                }
            ],
        }

        with self.assertRaisesRegex(RuntimeError, "Item discount is not allowed"):
            invoices._validate_and_normalize_requested_discounts(data, self._profile())

    @patch("pos_next.api.invoices.frappe.throw", side_effect=_raise)
    @patch("pos_next.api.invoices.apply_offers")
    @patch("pos_next.api.invoices._get_pos_discount_settings")
    def test_forged_pricing_rule_is_rejected(
        self, mock_settings, mock_apply_offers, _mock_throw
    ):
        mock_settings.return_value = SimpleNamespace(
            allow_user_to_edit_additional_discount=0,
            allow_user_to_edit_item_discount=1,
            allow_user_to_edit_rate=0,
            max_discount_allowed=0,
        )
        mock_apply_offers.return_value = {
            "items": [{"item_code": "ITEM-1", "pricing_rules": ""}],
            "free_items": [],
            "applied_pricing_rules": [],
        }
        data = {
            "doctype": "Sales Invoice",
            "customer": "CUST-1",
            "items": [
                {
                    "item_code": "ITEM-1",
                    "qty": 1,
                    "rate": 50,
                    "price_list_rate": 100,
                    "discount_percentage": 50,
                    "discount_amount": 50,
                    "pricing_rules": "FAKE-RULE",
                }
            ],
        }

        with self.assertRaisesRegex(RuntimeError, "Pricing rule.*no longer valid"):
            invoices._validate_and_normalize_requested_discounts(data, self._profile())

    @patch("pos_next.api.invoices.frappe.throw", side_effect=_raise)
    @patch("pos_next.api.invoices._get_pos_discount_settings")
    def test_manual_additional_discount_cannot_bypass_disabled_setting(
        self, mock_settings, _mock_throw
    ):
        mock_settings.return_value = SimpleNamespace(
            allow_user_to_edit_additional_discount=0,
            allow_user_to_edit_item_discount=1,
            allow_user_to_edit_rate=0,
            max_discount_allowed=0,
        )
        data = {
            "doctype": "Sales Invoice",
            "customer": "CUST-1",
            "discount_amount": 25,
            "items": [],
        }

        with self.assertRaisesRegex(RuntimeError, "Additional discount is not allowed"):
            invoices._validate_and_normalize_requested_discounts(data, self._profile())


class TestNegativeStockPolicy(unittest.TestCase):
    class _Row(dict):
        __getattr__ = dict.get

    @patch("pos_next.api.invoices._get_available_stock", return_value=10)
    @patch("pos_next.api.invoices._erpnext_allows_negative_stock", return_value=False)
    @patch("pos_next.api.invoices.frappe.get_all")
    @patch("pos_next.api.invoices.frappe.get_meta")
    def test_split_lines_are_aggregated_before_stock_check(
        self, mock_get_meta, mock_get_all, _mock_policy, _mock_available
    ):
        mock_get_meta.return_value.has_field.return_value = True
        mock_get_all.return_value = [
            self._Row(
                name="ITEM-1",
                is_stock_item=1,
                has_serial_no=0,
                has_batch_no=0,
                allow_negative_stock=0,
            )
        ]

        errors = invoices._collect_stock_errors(
            [
                {"item_code": "ITEM-1", "warehouse": "WH-A", "qty": 6, "conversion_factor": 1},
                {"item_code": "ITEM-1", "warehouse": "WH-A", "qty": 5, "conversion_factor": 1},
            ]
        )

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["requested_qty"], 11)
        self.assertEqual(errors[0]["available_qty"], 10)

    @patch("pos_next.api.invoices._erpnext_allows_negative_stock", return_value=True)
    @patch("pos_next.api.invoices.frappe.get_all")
    @patch("pos_next.api.invoices.frappe.get_meta")
    def test_item_level_negative_stock_bypasses_pos_early_block(
        self, mock_get_meta, mock_get_all, _mock_policy
    ):
        mock_get_meta.return_value.has_field.return_value = True
        mock_get_all.return_value = [
            self._Row(
                name="ITEM-1",
                is_stock_item=1,
                has_serial_no=0,
                has_batch_no=0,
                allow_negative_stock=1,
            )
        ]

        errors = invoices._collect_stock_errors(
            [{"item_code": "ITEM-1", "warehouse": "WH-A", "qty": 999, "conversion_factor": 1}]
        )
        self.assertEqual(errors, [])
