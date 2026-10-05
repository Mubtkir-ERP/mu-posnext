# POSNext 1.19.0 — Phase 3A

This build contains only the first half of phase 3: authorization and core POS security.

## Implemented

- Centralized POS Profile, company and opening-shift authorization.
- Invoice/order create/update/submit protection, including existing draft ownership checks.
- Offline invoice idempotent retry remains supported after shift closure for an already-synced invoice.
- Draft invoice listing/deletion/cleanup scoped to the current cashier and POS context.
- Invoice Management search still spans all POS invoices in the selected profile company, but requires access to that profile.
- Return list/prepare flows restricted to the authorized company/current shift.
- Opening shift creation checks profile/company/user and configured payment modes.
- Closing shift submission rejects arbitrary DocTypes and rebuilds transactions/payments/taxes on the server; only counted closing amounts are accepted from the browser.
- Cash disbursement APIs validate current shift/profile/company before creating or cancelling Journal Entries.
- Customer search/details/create/update are protected by POS Profile/Customer permissions; Customer updates no longer use a broad ignore_permissions save.

## Not included yet (Phase 3B)

Wallet, Loyalty-to-Wallet, Coupons, Negative Stock redesign, strict payment-account resolution, and the remaining financial transaction cleanup are intentionally unchanged in this build.
