frappe.ui.form.on("VB Vendor", {
	refresh(frm) {
		if (frm.doc.token) {
			frm.add_custom_button(__("Copy Portal Link"), () => {
				frappe.call({
					method: "vendor_billing.desk.portal_share_url",
					args: { vendor: frm.doc.name },
					callback(r) {
						if (!r.message) return;
						frappe.utils.copy_to_clipboard(r.message);
						frappe.show_alert({ message: __("Portal link copied"), indicator: "green" });
					},
				});
			});
		}
		if (!frm.doc.archived && frm.has_perm("write")) {
			frm.add_custom_button(__("Archive"), () => {
				frappe.prompt(
					{ fieldtype: "Small Text", fieldname: "remarks", label: __("Remarks"), reqd: 1 },
					(values) => {
						frappe.call({
							method: "vendor_billing.desk.archive_doc",
							args: { doctype: "VB Vendor", name: frm.doc.name, remarks: values.remarks },
							callback() {
								frm.reload_doc();
							},
						});
					},
					__("Archive vendor")
				);
			});
		} else if (frm.doc.archived && frm.has_perm("write")) {
			frm.add_custom_button(__("Restore"), () => {
				frappe.call({
					method: "vendor_billing.desk.restore_doc",
					args: { doctype: "VB Vendor", name: frm.doc.name },
					callback() {
						frm.reload_doc();
					},
				});
			});
		}
	},
});
