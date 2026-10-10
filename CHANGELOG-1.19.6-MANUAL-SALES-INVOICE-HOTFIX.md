# POSNext 1.19.6 — Manual Sales Invoice Hotfix

This hotfix narrows Phase 3 Point 4 payment-account hardening to invoices actually created through a POS frontend.

## Behavior after this fix

- **Normal ERPNext Sales Invoice from Desk**, even when **Paid** is checked and a **POS Profile** is selected: POSNext payment-account pinning does not run. ERPNext handles the invoice normally.
- **Invoice created through POSNext**: `is_created_using_pos = 1` is set server-side and all Point 4 payment-account protections continue to run.

No other Phase 3 behavior is changed.
