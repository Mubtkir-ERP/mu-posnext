# مطابقة موازنات مدى — الميزة الكاملة (داخل mu-posnext)

تطبيق pos_next (module: POS Next). المطابقة تعمل end-to-end.

## DocTypes
- **Mada Terminal** — سجل الأجهزة
- **Mada Settlement** — سجل الموازنة (مستقل لكل جهاز، حالة تلقائية)
- **Mada Settlement Entry** — إدخال السائق: عدة أجهزة دفعة واحدة (زر Create Settlements)
- **Mada Bank Reconciliation** — رفع كشف البنك + مطابقة
- **Mada Reconciliation Settings** — مفاتيح التفعيل والمقارنة والبنك
- تقرير **Mada Reconciliation Status** — حالة كل الموازنات

## التدفق الكامل
1. فعّل الإعدادات في **Mada Reconciliation Settings**.
2. سجّل الأجهزة في **Mada Terminal**.
3. أدخل الموازنات: إمّا **Mada Settlement Entry** (عدة أجهزة)، أو تلقائيًا من **إقفال الوردية** (إذا فعّلت feed_from_closing_shift).
4. في **Mada Bank Reconciliation**: احفظ → ارفع ملف الكشف في حقل Bank Statement File → **رفع وتعبئة الكشف** (يستخرج رقم الموازنة بالـ regex) → **Run Matching**.
5. راجع النتائج في التقرير وفي قائمة Mada Settlement.

## تكامل إقفال الوردية
- patch يضيف جدول **Mada Settlements** داخل POS Closing Shift (حقول مخصّصة قابلة للفصل).
- عند اعتماد الإقفال (on_submit) تُنشأ سجلات مدى تلقائيًا؛ وعند الإلغاء تُحذف.
- عند جهاز واحد + تفعيل compare_pos_total يُعبّأ "إجمالي مدى في POS" من جدول تسوية المدفوعات.

## رفع كشف البنك
- يدعم Excel (.xlsx) و CSV. يكتشف الأعمدة تلقائيًا (عربي/إنجليزي: التاريخ/المبلغ/البيان/رقم الموازنة).
- يستخرج رقم الموازنة من البيان عبر settlement_regex في الإعدادات.
- يتعامل مع الأرقام العربية والفواصل العربية (٬ ٫).

## ملفات مُعدّلة على التطبيق القائم
- `hooks.py` — doc_events["POS Closing Shift"] (on_submit/on_cancel)
- `patches.txt` — إضافة patch مدى
- `workspace/posnext/posnext.json` — اختصارات وبطاقة مدى

## النشر
Push → **Build image (#)** → **Redeploy في Coolify** → **Migrate**. (Migrate وحده لا يكفي.)
