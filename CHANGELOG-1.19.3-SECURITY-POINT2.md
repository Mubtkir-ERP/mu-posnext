# POSNext 1.19.3 — Phase 3 Security Point 2

This release develops only **Point 2: Wallet / Loyalty monetary integrity**.

## Hardened

- Wallet APIs now authorize customer, company, and POS Profile context before returning or mutating wallet data.
- Wallet balances are calculated from the server-side GL and reserve only unposted draft wallet payments.
- Wallet spends are serialized with a wallet-row lock to reduce concurrent double-spend risk.
- Wallet payment account and payment method are derived from ERPNext configuration; browser-supplied account values are not trusted.
- Loyalty credits are calculated from the submitted invoice's Loyalty Point Entry and Loyalty Program conversion factor on the server.
- The old direct endpoint that accepted caller-provided loyalty points/conversion factors is disabled.
- Reference-backed loyalty/refund credits are idempotent so request retries cannot create duplicate credits.
- Return credit amounts come only from the submitted return invoice.
- Wallet/Loyalty configuration is validated against the POS Profile company.

## Compatibility

- Existing public read wrappers remain available but delegate to the guarded canonical Wallet API.
- The POS frontend API contract for `get_wallet_info` is unchanged.

## Explicitly not changed

Coupon/discount rules, cash disbursement, negative-stock behavior, cache/settings redesign, and later Phase 3 points are not part of this release.
