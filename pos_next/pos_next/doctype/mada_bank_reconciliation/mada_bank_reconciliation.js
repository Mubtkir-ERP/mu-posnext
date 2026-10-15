// Copyright (c) 2026, MUBTKIR and contributors
// For license information, please see license.txt

frappe.ui.form.on("Mada Bank Reconciliation", {
    refresh(frm) {
        if (frm.is_new()) {
            return;
        }

        frm.add_custom_button(__("Run Matching"), () => {
            if (!frm.doc.statement_rows || !frm.doc.statement_rows.length) {
                frappe.msgprint(__("أضف صفوف كشف البنك أولًا."));
                return;
            }
            frappe.dom.freeze(__("جاري المطابقة..."));
            frm.call("run_matching")
                .then((r) => {
                    frappe.dom.unfreeze();
                    const m = r.message || {};
                    frappe.show_alert({
                        message: __("تمت المطابقة: {0} مطابق · {1} لم تنزل · {2} فرق مبلغ · {3} زائد في البنك", [
                            m.matched || 0,
                            m.not_in_bank || 0,
                            m.mismatch || 0,
                            m.extra || 0,
                        ]),
                        indicator: "green",
                    }, 10);
                    frm.reload_doc();
                })
                .catch(() => frappe.dom.unfreeze());
        }).addClass("btn-primary");

        frm.add_custom_button(__("عرض الموازنات غير المنزّلة"), () => {
            frappe.set_route("List", "Mada Settlement", { status: "Not in Bank" });
        });
    },
});
