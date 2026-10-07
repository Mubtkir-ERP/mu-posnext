# POSNext 1.19.2 — Phase 3 Security Point 1

This release develops only **Point 1: permissions and authorization**.

## Hardened

- POS Profile access is validated centrally before profile-bound data is returned.
- POS Settings/profile updates cannot be performed against another cashier's profile.
- Warehouse/stock/batch/serial lookups are limited to companies accessible through the cashier's POS Profiles.
- POS-linked Sales Invoice / Sales Order reads are authorized using the document's trusted database POS Profile/company, not caller-provided values.
- Partial-payment and credit-sale document access now uses the same POS authorization boundary.
- Existing `submit_closing_shift`, `update_invoice`, and `submit_invoice` protections remain intact.

## Explicitly not changed

Wallet/Loyalty, coupons/discount calculations, negative-stock redesign, payment-account resolution, and financial cleanup are left for later points.
