# POSNext 1.19.9 — Manual Sales Invoice Hook Fix

## Fix
Frappe `doc_events` handlers are invoked with both the document and event method.
`validate_and_pin_invoice_payments` was registered as a Sales Invoice `validate` hook but accepted only one positional argument, causing:

`TypeError: validate_and_pin_invoice_payments() takes 1 positional argument but 2 were given`

The hook now accepts `method=None`.

The existing guard remains unchanged: payment pinning only applies when both `is_pos` and `is_created_using_pos` are true. A normal Desk Sales Invoice may select a POS Profile and remain on ERPNext's standard flow.
