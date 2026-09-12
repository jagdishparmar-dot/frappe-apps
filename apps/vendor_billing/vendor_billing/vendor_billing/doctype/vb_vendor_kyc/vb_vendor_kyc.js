frappe.ui.form.on("VB Vendor KYC", {
	refresh(frm) {
		if (frm.doc.kyc_status === "pending_verification" || frm.doc.docstatus === 1) {
			frm.disable_save();
		}
		if (frm.doc.kyc_status === "pending_verification") {
			frm.dashboard.set_headline(__("Under review — identity fields are locked until Verify or Reject."));
		}
		if (frm.doc.docstatus === 1) {
			frm.dashboard.set_headline(__("Verified KYC is frozen. Bank updates must go through a profile change request."));
		}
		if (frm.doc.kyc_status === "pending_verification" && frm.has_perm("write")) {
			frm.add_custom_button(__("Verify"), () => {
				frappe.call({
					method: "vendor_billing.desk.verify_kyc",
					args: { kyc: frm.doc.name },
					callback() {
						frm.reload_doc();
					},
				});
			});
			frm.add_custom_button(__("Reject"), () => {
				frappe.prompt(
					{ fieldtype: "Small Text", fieldname: "remarks", label: __("Remarks"), reqd: 1 },
					(values) => {
						frappe.call({
							method: "vendor_billing.desk.reject_kyc",
							args: { kyc: frm.doc.name, remarks: values.remarks },
							callback() {
								frm.reload_doc();
							},
						});
					},
					__("Reject KYC")
				);
			});
		}
	},
});
