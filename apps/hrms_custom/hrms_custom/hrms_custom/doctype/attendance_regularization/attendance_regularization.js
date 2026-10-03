frappe.ui.form.on("Attendance Regularization", {
	date(frm) {
		if (!frm.doc.date || is_hr_user()) return;
		if (frm.doc.date === frappe.datetime.get_today()) {
			frappe.msgprint(__("You cannot regularize attendance for today"));
			frm.set_value("date", null);
		}
	},
	refresh(frm) {
		set_own_employee(frm);
		if (frm.is_new() || !frappe.user.has_role(["System Manager", "HR Admin", "HR Executive"])) return;
		if (frm.doc.status !== "Open") return;

		frm.add_custom_button(__("Approve"), () => review(frm, "Approved")).addClass("btn-primary");
		frm.add_custom_button(__("Reject"), () => {
			frappe.prompt(
				{ fieldname: "remarks", fieldtype: "Small Text", label: __("Reason (shown to the employee)"), reqd: 1 },
				(values) => review(frm, "Rejected", values.remarks),
				__("Reject regularization"),
				__("Reject")
			);
		});
	},
});

function is_hr_user() {
	return frappe.user.has_role(["System Manager", "HR Admin", "HR Executive"]);
}

function set_own_employee(frm) {
	if (!frm.is_new() || frm.doc.employee || frappe.user.has_role(["System Manager", "HR Admin", "HR Executive"])) return;
	if (frappe.boot.hrms_session_employee) frm.set_value("employee", frappe.boot.hrms_session_employee);
}

function review(frm, status, remarks) {
	frappe.call({
		method: "hrms_custom.api.regularization.review_regularization",
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
