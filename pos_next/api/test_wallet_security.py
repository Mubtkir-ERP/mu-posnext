# Copyright (c) 2026, POS Next and contributors

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pos_next.api import wallet
from pos_next.pos_next.doctype.wallet_transaction import wallet_transaction


def _raise(message, *args, **kwargs):
    raise RuntimeError(str(message))


class PaymentRow(dict):
    """Small dict/attribute hybrid matching Frappe child-row behavior used by tests."""

    __getattr__ = dict.get

    def __setattr__(self, key, value):
        self[key] = value


class TestWalletSecurity(unittest.TestCase):
    @patch("pos_next.api.wallet.frappe.get_all", return_value=[])
    def test_pending_wallet_payments_reserve_drafts_only(self, mock_get_all):
        self.assertEqual(wallet.get_pending_wallet_payments("CUST-1", "Company A"), 0)
        filters = mock_get_all.call_args.kwargs["filters"]
        self.assertEqual(filters["docstatus"], 0)
        self.assertEqual(filters["company"], "Company A")
        self.assertNotIn("outstanding_amount", filters)

    @patch("pos_next.api.wallet.frappe.throw", side_effect=_raise)
    @patch("pos_next.api.wallet._get_mode_account", return_value=None)
    @patch("pos_next.api.wallet.frappe.get_all", return_value=["Wallet"])
    def test_wallet_payment_requires_company_account_mapping(
        self, _mock_get_all, _mock_account, _mock_throw
    ):
        doc = SimpleNamespace(pos_profile="POS-A", company="Company A")
        payment = PaymentRow(mode_of_payment="Wallet", amount=25, account="Injected")
        with self.assertRaisesRegex(RuntimeError, "no account configured"):
            wallet._validate_wallet_payment_configuration(
                doc,
                [payment],
                {"enable_loyalty_program": 1, "wallet_account": "Wallet Receivable - A"},
                SimpleNamespace(account="Wallet Receivable - A"),
            )

    @patch("pos_next.api.wallet._get_mode_account", return_value="Wallet Receivable - A")
    @patch("pos_next.api.wallet.frappe.get_all", return_value=["Wallet"])
    def test_wallet_payment_account_is_server_pinned(self, _mock_get_all, _mock_account):
        doc = SimpleNamespace(pos_profile="POS-A", company="Company A")
        payment = PaymentRow(mode_of_payment="Wallet", amount=25, account="Injected")
        wallet._validate_wallet_payment_configuration(
            doc,
            [payment],
            {"enable_loyalty_program": 1, "wallet_account": "Wallet Receivable - A"},
            SimpleNamespace(account="Wallet Receivable - A"),
        )
        self.assertEqual(payment.account, "Wallet Receivable - A")

    @patch("pos_next.api.wallet.frappe.throw", side_effect=_raise)
    @patch("pos_next.api.wallet.frappe.db.get_value")
    def test_arbitrary_invoice_cannot_be_excluded_from_balance(self, mock_get_value, _mock_throw):
        mock_get_value.return_value = SimpleNamespace(
            name="SINV-2",
            customer="OTHER-CUSTOMER",
            company="Company A",
            pos_profile="POS-A",
            docstatus=0,
        )
        with self.assertRaisesRegex(RuntimeError, "not valid for this wallet"):
            wallet._validate_excluded_invoice(
                "CUST-1", "Company A", "SINV-2", pos_profile="POS-A"
            )


    @patch("pos_next.api.wallet.frappe.db.get_value")
    def test_loyalty_credit_uses_server_entry_and_program_factor(self, mock_get_value):
        invoice = Mock()
        invoice.doctype = "Sales Invoice"
        invoice.docstatus = 1
        invoice.name = "SINV-1"
        invoice.customer = "CUST-1"
        invoice.company = "Company A"
        invoice.get.side_effect = lambda key: {"is_return": 0, "pos_profile": "POS-A"}.get(key)

        def get_value(doctype, name_or_filters=None, fieldname=None, **kwargs):
            if doctype == "Loyalty Point Entry":
                return SimpleNamespace(
                    name="LPE-1",
                    loyalty_points=40,
                    loyalty_program="LOYALTY-A",
                )
            if doctype == "Loyalty Program":
                return SimpleNamespace(
                    name="LOYALTY-A",
                    company="Company A",
                    conversion_factor=0.25,
                    expense_account="Loyalty Expense - A",
                )
            raise AssertionError(f"Unexpected lookup: {doctype}")

        mock_get_value.side_effect = get_value
        details = wallet._get_loyalty_credit_details(invoice)

        self.assertEqual(details.loyalty_program, "LOYALTY-A")
        self.assertEqual(details.loyalty_points, 40)
        self.assertAlmostEqual(details.conversion_factor, 0.25)
        self.assertAlmostEqual(details.credit_amount, 10.0)
        self.assertFalse(any(call.args and call.args[0] == "Customer" for call in mock_get_value.call_args_list))

    @patch("pos_next.pos_next.doctype.wallet_transaction.wallet_transaction.frappe.throw", side_effect=_raise)
    def test_direct_loyalty_conversion_endpoint_is_disabled(self, _mock_throw):
        with self.assertRaisesRegex(RuntimeError, "Direct loyalty-to-wallet conversion is disabled"):
            wallet_transaction.credit_loyalty_points_to_wallet(
                "CUST-1", "Company A", loyalty_points=999999, conversion_factor=999
            )

    @patch("pos_next.pos_next.doctype.wallet_transaction.wallet_transaction.create_wallet_credit")
    @patch("pos_next.api.wallet.get_pos_settings", return_value={"wallet_account": "Wallet - A"})
    @patch("pos_next.api.wallet._get_or_create_wallet")
    @patch("pos_next.pos_next.doctype.wallet_transaction.wallet_transaction.frappe.db.get_value")
    def test_return_credit_ignores_client_amount(
        self, mock_get_value, mock_get_wallet, _mock_settings, mock_create_credit
    ):
        mock_get_value.return_value = SimpleNamespace(
            customer="CUST-1",
            company="Company A",
            grand_total=-125.50,
            is_return=1,
            return_against="SINV-1",
            pos_profile="POS-A",
            docstatus=1,
        )
        mock_get_wallet.return_value = SimpleNamespace(name="WALLET-1")
        mock_create_credit.return_value = SimpleNamespace(name="WT-1")

        wallet_transaction.credit_return_to_wallet("SINV-RET-1", amount=1.0)

        self.assertAlmostEqual(mock_create_credit.call_args.kwargs["amount"], 125.50)
        self.assertEqual(mock_create_credit.call_args.kwargs["reference_name"], "SINV-RET-1")


if __name__ == "__main__":
    unittest.main()
