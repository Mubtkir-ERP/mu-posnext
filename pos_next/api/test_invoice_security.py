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
