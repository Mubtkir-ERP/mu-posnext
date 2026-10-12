# POSNext 1.21.0 — Phase 3 Save/Sync Integrity + Profile Cache + Resilient Shift Close

## Save and synchronization integrity
- Added a persistent idempotency key to normal online Sales Invoice submission, not only offline invoices. A lost HTTP response can now be retried without creating a second submitted sale.
- Kept the existing offline invoice mapping and hardened concurrent Offline Invoice Sync record creation.
- Added a single-flight sync coordinator so multiple reconnect listeners cannot run overlapping invoice/shift sync jobs.
- Partial payments now accept a persistent request ID, lock the Sales Invoice row, and return the previously-created Payment Entries on retry.
- Cash disbursements now accept a persistent request ID, lock the opening shift, and return the existing Journal Entry on retry.
- Manual wallet credit now supports request IDs and wallet-row locking; invoice-backed wallet/loyalty operations retain their existing reference-based idempotency.
- Removed transaction-breaking manual commits from partial-payment status updates and referral-code business flows.

## Cache and settings isolation
- POS Settings are cached per POS Profile and only reused for the exact same profile when offline.
- Switching POS Profile clears operational item/customer/price/stock/payment/sales-person/offer caches while preserving queued invoices, queued shift closes, drafts and history.
- Payment Methods, Sales Persons and Offers now use profile-scoped compound IndexedDB keys to prevent cross-profile overwrites.
- Removed/disabled payment methods and sales persons are replaced atomically per profile instead of lingering in cache.
- POS tax rules are cached per profile and can be safely reused during weak/offline connectivity.

## Resilient shift close
- Shift closing can be saved locally when the server is offline or connection quality is poor.
- Counted closing amounts are persisted in IndexedDB; the server recalculates all expected totals and transactions during sync.
- Queued invoices are always synchronized before the shift-close request. A close is deferred while any invoice for the shift remains unresolved.
- The server shift-close endpoint is idempotent and row-locked: a retry after a lost response returns the existing POS Closing Shift instead of creating another.
- A locally closed shift is not resurrected after refresh. Opening a new shift is blocked until the previous close has synchronized.
- Pending close data is automatically synchronized when connectivity returns and old completed queue rows are cleaned up.

## Safety
- No change to normal ERPNext Sales Invoice behavior outside POSNext.
- No client-provided closing totals are trusted by the server; only counted amounts are accepted and all transaction/payment/tax data is rebuilt server-side.
