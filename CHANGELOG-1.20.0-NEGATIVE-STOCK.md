# POSNext 1.20.0 — Negative Stock

Phase 3 / Point 5 aligns POSNext with ERPNext negative-stock rules.

- Global policy: `Stock Settings.allow_negative_stock`.
- Item exception: `Item.allow_negative_stock`.
- POS Settings no longer toggles global Stock Settings.
- Cart/UI checks use cached global + item policy for immediate feedback.
- Server re-checks current Item/Bin data before submission.
- ERPNext submit remains the final authority for stock ledger, reservation, serial and batch rules.
- Duplicate invoice rows are aggregated before availability comparison.
- Product Bundle availability respects negative-stock-enabled components.
