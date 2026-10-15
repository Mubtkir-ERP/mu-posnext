# مطابقة موازنات مدى — المرحلة 1 (قابلة للتجربة)

ملفات تُضاف إلى تطبيق **pos_next** (module: POS Next). تُنشئ 4 DocTypes ومنطق المطابقة.

## المحتوى
| DocType | الوظيفة |
|---|---|
| **Mada Terminal** | سجل أجهزة مدى (المعرّف، الفرع، الحساب البنكي، المستخدم) |
| **Mada Settlement** | سجل الموازنة (التاريخ، الجهاز، رقم الموازنة، المبلغ، الحالة) — سجل مستقل لكل جهاز |
| **Mada Reconciliation Settings** | إعداد واحد للموقع (مفاتيح التفعيل والمقارنة) |
| **Mada Bank Reconciliation** | رفع صفوف كشف البنك + زر **Run Matching** |
| Mada Bank Reconciliation Row | جدول فرعي لصفوف الكشف |

## التركيب (بدون SSH)
1. انسخ مجلد `pos_next/pos_next/doctype/` من هذا الأرشيف فوق نفس المسار في مستودع تطبيق pos_next لديك (يضيف 5 مجلدات جديدة فقط، لا يستبدل شيئًا قائمًا).
2. ادفع التغييرات إلى المستودع (Git).
3. من لوحة **MUBTKIR Cloud** للموقع: **Apps → pos_next → Update**، ثم انتظر انتهاء **Migrate**.

> لا يوجد تعديل على `hooks.py` في هذه المرحلة. تكامل إقفال الوردية (التغذية التلقائية) يأتي في المرحلة 2 ويتطلب تعديل hooks + حقل على POS Closing Shift.

## خطوات التجربة
1. **Mada Reconciliation Settings**: افتحه وفعّل `تفعيل مطابقة موازنات مدى`. (فعّل `مقارنة إجمالي مدى في POS` فقط لمن يُدخل كل الفواتير.)
2. **Mada Terminal**: أنشئ جهازًا أو أكثر (Terminal ID = المعرّف على ورقة الموازنة).
3. **Mada Settlement**: أدخل موازنتين أو ثلاثًا (جهاز + رقم موازنة + مبلغ). الحالة تبدأ `Pending`.
4. **Mada Bank Reconciliation**: أنشئ سجلًا، حدّد `From/To Date`، والصق صفوف الكشف في الجدول (رقم الموازنة + المبلغ)، ثم **Run Matching**.
5. راجع النتائج: العدّادات في الأسفل، وحالة كل سجل في قائمة **Mada Settlement** (Matched / Not in Bank / Amount Mismatch).

## إظهارها في مساحة عمل نقاط البيع
من مساحة العمل **POSNext**: زر **Edit** → **Add Shortcut / Add Card** وأضف اختصارات لـ Mada Settlement و Mada Bank Reconciliation و Mada Reconciliation Settings. (يمكنني لاحقًا تسليمها جاهزة داخل workspace JSON.)

## منطق المطابقة
المفتاح = **رقم الموازنة**. لكل موازنة ضمن الفترة:
- رقم موجود في البنك + المبلغ متساوٍ → **Matched**
- رقم موجود + مبلغ مختلف → **Amount Mismatch**
- موازنة بلا صف بنكي → **Not in Bank** (هدفك الأساسي)
- صف بنكي بلا موازنة → **Extra in Bank** (عدّ فقط)
