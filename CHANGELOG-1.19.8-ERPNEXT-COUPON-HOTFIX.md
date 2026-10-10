# POSNext 1.19.8 — ERPNext Coupon Code Hotfix

- ERPNext `Coupon Code` is checked before legacy `POS Coupon`.
- The cashier enters the real coupon code stored in ERPNext.
- The server resolves it to the canonical Coupon Code document name used by Sales Invoice/Sales Order.
- Linked transaction Pricing Rule values are used to calculate the discount; browser discount values are ignored.
- ERPNext core owns native coupon `used` counter updates, preventing double counting.
- Legacy POS Coupon is retained only as fallback compatibility.
