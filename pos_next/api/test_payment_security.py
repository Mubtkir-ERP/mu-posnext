# Copyright (c) 2026, POS Next and contributors

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pos_next.api import payment_security


def _raise(message, *args, **kwargs):
    raise RuntimeError(str(message))


class PaymentRow(dict):
    __getattr__ = dict.get

    def __setattr__(self, key, value):
        self[key] = value


class InvoiceDoc(dict):
    __getattr__ = dict.get


class TestPaymentSecurity(unittest.TestCase):
    @patch("pos_next.api.payment_security.resolve_pos_payment_account")
    @patch("pos_next.api.payment_security._get_mode_details")
    def test_standard_payment_account_is_pinned_server_side(self, mock_mode, mock_resolve):
        mock_mode.return_value = SimpleNamespace(is_wallet_payment=0)
        mock_resolve.return_value = SimpleNamespace(account="Cash - A")
        payment = PaymentRow(mode_of_payment="Cash", amount=100, account="Injected - A")
        doc = InvoiceDoc(
            is_pos=1,
            is_created_using_pos=1,
            pos_profile="POS-A",
            company="Company A",
            payments=[payment],
        )

        payment_security.validate_and_pin_invoice_payments(doc)

        self.assertEqual(payment.account, "Cash - A")
        mock_resolve.assert_called_once_with(
            "POS-A", "Cash", company="Company A", allow_wallet=False
        )

    @patch("pos_next.api.payment_security.resolve_pos_payment_account")
    @patch("pos_next.api.payment_security._get_mode_details")
    def test_wallet_row_is_left_to_wallet_security(self, mock_mode, mock_resolve):
        mock_mode.return_value = SimpleNamespace(is_wallet_payment=1)
        payment = PaymentRow(mode_of_payment="Wallet", amount=25, account="Wallet - A")
        doc = InvoiceDoc(
            is_pos=1,
            is_created_using_pos=1,
            pos_profile="POS-A",
            company="Company A",
            payments=[payment],
        )

        payment_security.validate_and_pin_invoice_payments(doc)
        mock_resolve.assert_not_called()

    @patch("pos_next.api.payment_security.resolve_pos_payment_account")
    @patch("pos_next.api.payment_security._get_mode_details")
    def test_normal_sales_invoice_with_pos_profile_is_not_intercepted(self, mock_mode, mock_resolve):
        """Desk Sales Invoice may be Paid + POS Profile without being created by POSNext."""
        payment = PaymentRow(mode_of_payment="Cash", amount=100, account="Desk Cash - A")
        doc = InvoiceDoc(
            is_pos=1,
            is_created_using_pos=0,
            pos_profile="POS-A",
            company="Company A",
            payments=[payment],
        )

        payment_security.validate_and_pin_invoice_payments(doc)

        self.assertEqual(payment.account, "Desk Cash - A")
        mock_mode.assert_not_called()
        mock_resolve.assert_not_called()

    @patch("pos_next.api.payment_security.frappe.throw", side_effect=_raise)
    def test_client_cannot_override_payment_account(self, _mock_throw):
        with self.assertRaisesRegex(RuntimeError, "cannot be overridden"):
            payment_security.validate_requested_payment_account(
                "Cash - A", "Other Cash - A"
            )


if __name__ == "__main__":
    unittest.main()
