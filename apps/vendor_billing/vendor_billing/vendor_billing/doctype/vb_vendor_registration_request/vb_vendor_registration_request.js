frappe.ui.form.on("VB Vendor Registration Request", {
	refresh(frm) {
		if (frm.doc.status !== "pending" || !frm.has_perm("write") || frm.doc.docstatus === 2) return;
		frm.dashboard.set_headline(__("Submitted request — Approve to create the vendor, or Reject to close it."));
		frm.add_custom_button(__("Approve"), () => {
			frappe.confirm(__("Create a vendor from this registration?"), () => {
				frappe.call({
					method: "vendor_billing.desk.review_registration",
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
						method: "vendor_billing.desk.review_registration",
						args: { name: frm.doc.name, action: "reject", remarks: values.remarks },
						callback() {
							frm.reload_doc();
						},
					});
				},
				__("Reject registration")
			);
		});
	},
});
