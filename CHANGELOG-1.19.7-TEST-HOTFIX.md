# POSNext 1.19.7 — Test Hotfix

This hotfix addresses issues found during acceptance testing of 1.19.6.

- Item max-discount validation now runs when **Update Product** is pressed.
- Backend validation at checkout remains in place as a security backstop.
- Payment rows are temporarily removed while ERPNext fills missing values, preventing the informational payment-refresh message from being treated as a request failure.
- Offline sync uses the same corrected path.
- Offline error text placeholder is fixed.
- Invalid coupon codes remain a normal validation result; no coupon state is applied unless validation succeeds.
