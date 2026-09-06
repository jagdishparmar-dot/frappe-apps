// Copyright (c) 2026, Vendor Directory and contributors
// For license information, please see license.txt

frappe.ui.form.on("Vendor", {
	refresh(frm) {
		const is_admin =
			frappe.user.has_role("System Manager") || frappe.user.has_role("Vendor Manager");

		if (frm.is_new() || !is_admin) {
			return;
		}

		frm.add_custom_button(__("Create Portal User"), () => {
			frappe.prompt(
				[
					{
						fieldname: "login_id",
						label: __("Login ID (Email)"),
						fieldtype: "Data",
						reqd: 1,
						default: frm.doc.portal_login_id || frm.doc.email || "",
					},
					{
						fieldname: "password",
						label: __("Temporary Password"),
						fieldtype: "Password",
						reqd: 1,
					},
				],
				(values) => {
					frappe.call({
						method: "vendor_directory.api.portal.create_portal_user",
						args: {
							vendor: frm.doc.name,
							login_id: values.login_id,
							password: values.password,
						},
						freeze: true,
						callback(r) {
							frm.reload_doc();
							if (r.message) {
								frappe.msgprint(r.message.message || __("Portal user created"));
							}
						},
					});
				},
				__("Create Portal User"),
				__("Create")
			);
		});

		const kyc = frm.doc.kyc_status;
		if (["Pending Review", "Under Review", "Draft", "Rejected"].includes(kyc)) {
			frm.add_custom_button(
				__("Mark Under Review"),
				() => {
					frappe.call({
						method: "vendor_directory.api.portal.set_kyc_status",
						args: { vendor: frm.doc.name, kyc_status: "Under Review" },
						freeze: true,
						callback() {
							frm.reload_doc();
						},
					});
				},
				__("KYC")
			);

			frm.add_custom_button(
				__("Mark KYC Verified"),
				() => {
					frappe.call({
						method: "vendor_directory.api.portal.set_kyc_status",
						args: { vendor: frm.doc.name, kyc_status: "Verified" },
						freeze: true,
						callback() {
							frm.reload_doc();
						},
					});
				},
				__("KYC")
			);

			frm.add_custom_button(
				__("Reject KYC"),
				() => {
					frappe.prompt(
						[
							{
								fieldname: "kyc_remarks",
								label: __("Rejection remarks"),
								fieldtype: "Small Text",
								reqd: 1,
							},
						],
						(values) => {
							frappe.call({
								method: "vendor_directory.api.portal.set_kyc_status",
								args: {
									vendor: frm.doc.name,
									kyc_status: "Rejected",
									kyc_remarks: values.kyc_remarks,
								},
								freeze: true,
								callback() {
									frm.reload_doc();
								},
							});
						},
						__("Reject KYC"),
						__("Reject")
					);
				},
				__("KYC")
			);
		}
	},
});
