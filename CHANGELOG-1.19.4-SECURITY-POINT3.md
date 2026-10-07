# POSNext 1.19.4 — Phase 3 Security Point 3

This release develops only **Point 3: Coupons and discount integrity**.

## Hardened

- Coupon validation is now tied to the authenticated POS Profile and its company.
- Coupon preview returns only the fields needed by POS and calculates the preview discount on the server.
- Checkout ignores browser-supplied coupon discount amounts and recalculates the coupon from ERPNext invoice totals.
- Coupon validity, customer/company restriction, minimum amount, expiry, maximum-use, and one-use-per-customer checks run again immediately before submit.
- A database row lock serializes concurrent use of the same coupon, preventing two cashiers from consuming the final use simultaneously.
- Coupon usage is derived from submitted Sales Invoice / POS Invoice / Sales Order records and the `used` counter is synchronized without manual commits.
- Cancelling a Sales Invoice or Sales Order synchronizes the coupon usage counter automatically.
- Manual invoice-level discounts are rejected when disabled in POS Settings and are checked against `max_discount_allowed` on the server.
- Manual item discounts are rejected when disabled and are checked against both POS Settings and Item `max_discount`.
- Claimed Pricing Rules are re-evaluated by ERPNext; forged or no-longer-applicable rule names are rejected.
- Promotional item discount values are replaced with ERPNext-calculated values rather than trusting the browser.
- Free items are accepted only when ERPNext returns the same free item from an active selected offer.
- Discounted item lines use the server price-list rate when available, preventing a forged browser `price_list_rate` from amplifying the discount.
- Coupon gift-card listing no longer trusts a caller-supplied company and is scoped to the authorized POS Profile.

## Compatibility

- The coupon dialog now sends `pos_profile` and uses the server-calculated preview amount.
- Invoice checkout keeps the existing two-step draft/submit flow and offline idempotency behavior.
- Existing Pricing Rule and promotional-scheme UI remains supported, including standalone non-coupon Pricing Rules.

## Explicitly not changed

Cash disbursement/account validation (Point 4), negative stock (Point 5), transaction idempotency/locking beyond coupon usage (Point 6), settings-cache redesign, and later Phase 3 points are not part of this release.
