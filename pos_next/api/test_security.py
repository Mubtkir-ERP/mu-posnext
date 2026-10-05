# Copyright (c) 2026, POS Next and contributors

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pos_next.api import security


def _raise(message, *args, **kwargs):
    raise RuntimeError(str(message))


class TestPOSSecurity(unittest.TestCase):
    @patch("pos_next.api.security.frappe.throw", side_effect=_raise)
    @patch("pos_next.api.security._require_authenticated", return_value="cashier@example.com")
    @patch("pos_next.api.security.user_has_pos_profile_access", return_value=True)
    @patch("pos_next.api.security.frappe.db.get_value")
    def test_profile_company_mismatch_is_rejected(
        self, mock_get_value, _mock_access, _mock_auth, _mock_throw
    ):
        mock_get_value.return_value = SimpleNamespace(
            name="POS-A", company="Company A", disabled=0, currency="SAR", warehouse="WH-A"
        )
        with self.assertRaisesRegex(RuntimeError, "belongs to company"):
            security.require_pos_profile_access("POS-A", company="Company B")

    @patch("pos_next.api.security.frappe.throw", side_effect=_raise)
    @patch("pos_next.api.security._is_privileged_pos_admin", return_value=False)
    @patch("pos_next.api.security._require_authenticated", return_value="cashier@example.com")
    @patch("pos_next.api.security.require_pos_profile_access")
    @patch("pos_next.api.security.frappe.db.get_value")
    def test_shift_owned_by_another_cashier_is_rejected(
        self, mock_get_value, _mock_profile, _mock_auth, _mock_admin, _mock_throw
    ):
        mock_get_value.return_value = SimpleNamespace(
            name="SHIFT-1",
            user="other@example.com",
            pos_profile="POS-A",
            company="Company A",
            status="Open",
            docstatus=1,
            pos_closing_shift=None,
            period_start_date="2026-10-05 10:00:00",
        )
        with self.assertRaisesRegex(RuntimeError, "belongs to another user"):
            security.require_shift_access("SHIFT-1")

    @patch("pos_next.api.security._is_privileged_pos_admin", return_value=False)
    @patch("pos_next.api.security._require_authenticated", return_value="cashier@example.com")
    @patch("pos_next.api.security.require_pos_profile_access")
    @patch("pos_next.api.security.frappe.db.get_value")
    def test_open_shift_returns_trusted_context(
        self, mock_get_value, _mock_profile, _mock_auth, _mock_admin
    ):
        row = SimpleNamespace(
            name="SHIFT-1",
            user="cashier@example.com",
            pos_profile="POS-A",
            company="Company A",
            status="Open",
            docstatus=1,
            pos_closing_shift=None,
            period_start_date="2026-10-05 10:00:00",
        )
        mock_get_value.return_value = row
        result = security.require_shift_access(
            "SHIFT-1", pos_profile="POS-A", company="Company A"
        )
        self.assertIs(result, row)
