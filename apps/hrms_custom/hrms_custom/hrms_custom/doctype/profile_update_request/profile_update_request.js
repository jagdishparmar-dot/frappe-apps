frappe.ui.form.on("Profile Update Request", {
	refresh(frm) {
		if (frm.is_new() || !frappe.user.has_role(["System Manager", "HR Admin", "HR Executive"])) return;
		if (frm.doc.status !== "Pending") return;

		frm.add_custom_button(__("Approve"), () => review(frm, "Approved")).addClass("btn-primary");
		frm.add_custom_button(__("Reject"), () => {
			frappe.prompt(
				{ fieldname: "remarks", fieldtype: "Small Text", label: __("Reason (shown to the employee)"), reqd: 1 },
				(values) => review(frm, "Rejected", values.remarks),
				__("Reject profile update"),
				__("Reject")
			);
		});
	},
});

function review(frm, status, remarks) {
	frappe.call({
		method: "hrms_custom.api.profile.review_profile_update",
		args: { request: frm.doc.name, status, remarks },
		freeze: true,
		callback(r) {
			if (r.success) {
				frappe.show_alert({ message: r.message, indicator: status === "Approved" ? "green" : "orange" });
				frm.reload_doc();
			}
		},
		error(r) {
			const body = r.responseJSON || {};
			frappe.msgprint({ title: __("Could not update"), message: body.message || __("Something went wrong"), indicator: "red" });
		},
	});
}
