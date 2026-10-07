# POSNext 1.19.5 — Phase 3 Security Point 4

This release develops only **Point 4: Cash disbursement and payment-account integrity**.

## Hardened payment methods and accounts

- Added `pos_next.api.payment_security` as the central authority for standard POS payment methods and their GL accounts.
- A Mode of Payment must be enabled and explicitly listed on the active POS Profile.
- Standard payment accounts are taken only from `Mode of Payment Account` for the POS Profile company. The old fallback that guessed another company Cash/Bank account is not used in POS flows.
- The configured GL account must be an active leaf account in the same company. Standard POS payments must settle to Cash/Bank accounts.
- Browser-provided account values are never authoritative. Invoice rows are pinned to the configured account, and partial-payment requests that try to override the account are rejected.
- Invoice draft creation and final submit both re-run payment validation to prevent an account/method swap between the two steps.

## Partial payments

- Partial Payment Entries use the invoice's stored POS Profile and company as the source of truth.
- The selected Mode of Payment must be enabled and configured on that profile.
- Wallet payment methods cannot be routed through the generic Payment Entry flow.
- The POS Profile must have Partial Payment enabled; direct API calls cannot bypass that setting.
- A client-supplied payment account must match the server-resolved account exactly.

## Opening shift

- Opening balances accept only enabled non-wallet payment methods configured on the selected POS Profile.
- Each method must have a valid company Cash/Bank account mapping.
- Duplicate payment methods and negative opening balances are rejected.

## Cash disbursement

- Cash Disbursement must be enabled in POS Settings before the API can create a Journal Entry.
- The cash Mode of Payment is taken from the POS Profile (or the first enabled Cash-type method on that profile) and must map to an active Cash account for the same company.
- The debit account comes only from `POS Settings.cash_disbursement_account`; the browser cannot substitute another account.
- The debit account must be an active leaf Asset/Expense account in the same company and cannot be Receivable, Payable, Cash, or Bank.
- The account endpoint no longer exposes the company's full chart of accounts to a cashier; it returns only configured safe disbursement accounts.
- POS Settings validates the cash/disbursement account wiring before the configuration can be saved.

## Configuration protection

- Cash-disbursement enable/account fields require native POS Profile write permission even when edited through generic document APIs; unrelated POS Settings keep their existing access behavior.
- The Cash Disbursement Account selector is filtered to safe company accounts in Desk.
- Disabled Modes of Payment are no longer returned by the standard POS payment-method API or wallet payment-method listing.
- The Sales Invoice validate hook enforces payment-account pinning even for generic document saves, and POSNext Cashier no longer receives direct Payment Entry create/write/submit permission; partial payments continue through the guarded POS API.

## Explicitly not changed

Negative Stock (Point 5), transaction idempotency/locking beyond existing protections (Point 6), settings-cache redesign, cleanup, and later Phase 3 points are not part of this release.
