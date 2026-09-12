frappe.ui.form.on("VB Vendor Profile Change Request", {
	refresh(frm) {
		if (frm.doc.status !== "pending" || !frm.has_perm("write") || frm.doc.docstatus === 2) return;
		frm.dashboard.set_headline(__("Submitted request — Approve to apply, or Reject to close it."));
		frm.add_custom_button(__("Approve"), () => {
			frappe.confirm(__("Apply this profile change to the vendor?"), () => {
				frappe.call({
					method: "vendor_billing.desk.review_profile_change",
					args: { name: frm.doc.name, action: "approve" },
					callback() {
						frm.reload_doc();
					},
				});
			});
		});
		frm.add_custom_button(__("Reject"), () => {
			frappe.prompt(
				{ fieldtype: "Small Text", fieldname: "remarks", label: __("Remarks"), reqd: 1 },
				(values) => {
					frappe.call({
						method: "vendor_billing.desk.review_profile_change",
						args: { name: frm.doc.name, action: "reject", remarks: values.remarks },
						callback() {
							frm.reload_doc();
						},
					});
				},
				__("Reject profile change")
			);
		});
	},
});
