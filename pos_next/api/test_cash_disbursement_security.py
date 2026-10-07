# Copyright (c) 2026, POS Next and contributors

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pos_next.api import cash_disbursement


def _raise(message, *args, **kwargs):
    raise RuntimeError(str(message))


class TestCashDisbursementSecurity(unittest.TestCase):
    @patch("pos_next.api.cash_disbursement.frappe.throw", side_effect=_raise)
    @patch("pos_next.api.cash_disbursement.frappe.db.get_value")
    def test_disbursement_account_must_belong_to_company(self, mock_get_value, _mock_throw):
        mock_get_value.return_value = SimpleNamespace(
            name="Petty Expense - B",
            company="Company B",
            account_type="Expense Account",
            root_type="Expense",
            is_group=0,
            disabled=0,
        )
        with self.assertRaisesRegex(RuntimeError, "Invalid cash disbursement account"):
            cash_disbursement._validate_disbursement_account(
                "Petty Expense - B", "Company A", cash_account="Cash - A"
            )

    @patch("pos_next.api.cash_disbursement.frappe.throw", side_effect=_raise)
    @patch("pos_next.api.cash_disbursement.frappe.db.get_value")
    def test_party_account_is_rejected(self, mock_get_value, _mock_throw):
        mock_get_value.return_value = SimpleNamespace(
            name="Debtors - A",
            company="Company A",
            account_type="Receivable",
            root_type="Asset",
            is_group=0,
            disabled=0,
        )
        with self.assertRaisesRegex(RuntimeError, "Receivable, Payable, Cash, or Bank"):
            cash_disbursement._validate_disbursement_account(
                "Debtors - A", "Company A", cash_account="Cash - A"
            )

    @patch("pos_next.api.cash_disbursement.frappe.throw", side_effect=_raise)
    @patch("pos_next.api.cash_disbursement.frappe.db.get_value")
    def test_cash_account_cannot_be_disbursement_debit(self, mock_get_value, _mock_throw):
        mock_get_value.return_value = SimpleNamespace(
            name="Cash - A",
            company="Company A",
            account_type="Cash",
            root_type="Asset",
            is_group=0,
            disabled=0,
        )
        with self.assertRaisesRegex(RuntimeError, "cannot be the same"):
            cash_disbursement._validate_disbursement_account(
                "Cash - A", "Company A", cash_account="Cash - A"
            )


if __name__ == "__main__":
    unittest.main()
