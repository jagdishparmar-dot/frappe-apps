frappe.ui.form.on("Profile Update Request", {
	refresh(frm) {
		if (!frm.is_new() || frm.doc.employee || frappe.user.has_role(["System Manager", "HR Admin", "HR Executive"])) {
			return;
		}
		if (frappe.boot.hrms_session_employee) frm.set_value("employee", frappe.boot.hrms_session_employee);
	},
});
