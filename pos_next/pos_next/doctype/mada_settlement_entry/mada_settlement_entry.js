// Copyright (c) 2026, MUBTKIR and contributors
// For license information, please see license.txt

frappe.ui.form.on("Mada Settlement Entry", {
    refresh(frm) {
        if (frm.is_new()) {
            return;
        }
        frm.add_custom_button(__("Create Settlements"), () => {
            if (!frm.doc.devices || !frm.doc.devices.length) {
                frappe.msgprint(__("أضف جهازًا واحدًا على الأقل."));
                return;
            }
            frappe.dom.freeze(__("جاري الإنشاء..."));
            frm.call("create_settlements")
                .then((r) => {
                    frappe.dom.unfreeze();
                    const n = (r.message && r.message.created) || 0;
                    frappe.show_alert({ message: __("تم إنشاء {0} موازنة", [n]), indicator: "green" }, 7);
                    frm.reload_doc();
                })
                .catch(() => frappe.dom.unfreeze());
        }).addClass("btn-primary");
    },
});
