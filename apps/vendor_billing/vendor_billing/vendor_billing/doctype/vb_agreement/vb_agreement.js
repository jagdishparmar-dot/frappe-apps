frappe.ui.form.on("VB Agreement", {
	refresh(frm) {
		if (frm.is_new()) return;
		if (frm.doc.docstatus === 0) {
			frm.dashboard.set_headline(__("Draft — Submit to issue this agreement to the vendor portal."));
		}
		if (frm.doc.docstatus === 1 && frm.has_perm("write") && frm.doc.status !== "Terminated") {
			frm.add_custom_button(__("Terminate"), () => {
				frappe.prompt(
					{ fieldtype: "Small Text", fieldname: "remarks", label: __("Remarks"), reqd: 1 },
					(values) => {
						frm.set_value("status", "Terminated");
						if (values.remarks) {
							frm.set_value("remarks", values.remarks);
						}
						frm.save("Update");
					},
					__("Terminate agreement")
				);
			});
		}
		if (!frm.doc.archived && frm.has_perm("write") && frm.doc.docstatus === 1) {
			frm.add_custom_button(__("Archive"), () => {
				frappe.prompt(
					{ fieldtype: "Small Text", fieldname: "remarks", label: __("Remarks"), reqd: 1 },
					(values) => {
						frappe.call({
							method: "vendor_billing.desk.archive_doc",
							args: { doctype: "VB Agreement", name: frm.doc.name, remarks: values.remarks },
							callback() {
								frm.reload_doc();
							},
						});
					},
					__("Archive agreement")
				);
			});
		} else if (frm.doc.archived && frm.has_perm("write")) {
			frm.add_custom_button(__("Restore"), () => {
				frappe.call({
					method: "vendor_billing.desk.restore_doc",
					args: { doctype: "VB Agreement", name: frm.doc.name },
					callback() {
						frm.reload_doc();
					},
				});
			});
		}
	},
});
