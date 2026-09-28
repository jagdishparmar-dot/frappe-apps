frappe.ui.form.on("Leave Application", {
	refresh(frm) {
		if (frm.is_new() || !frappe.user.has_role(["System Manager", "HR Admin", "HR Executive"])) return;
		if (frm.doc.status !== "Open") return;

		frm.add_custom_button(__("Approve"), () => review(frm, "Approved")).addClass("btn-primary");
		frm.add_custom_button(__("Reject"), () => {
			frappe.prompt(
				{ fieldname: "remarks", fieldtype: "Small Text", label: __("Reason (shown to the employee)"), reqd: 1 },
				(values) => review(frm, "Rejected", values.remarks),
				__("Reject leave"),
				__("Reject")
			);
		});
	},
});

function review(frm, status, remarks) {
	frappe.call({
		method: "hrms_custom.api.leave.review_leave",
		args: { application: frm.doc.name, status, remarks },
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
