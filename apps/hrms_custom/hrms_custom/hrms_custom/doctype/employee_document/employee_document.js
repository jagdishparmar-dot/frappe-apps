frappe.ui.form.on("Employee Document", {
	refresh(frm) {
		if (frm.is_new() || !frappe.user.has_role(["System Manager", "HR Admin", "HR Executive"])) return;

		if (frm.doc.status !== "Verified") {
			frm.add_custom_button(__("Verify"), () => review(frm, "Verified")).addClass("btn-primary");
		}
		if (frm.doc.status !== "Rejected") {
			frm.add_custom_button(__("Reject"), () => {
				frappe.prompt(
					{ fieldname: "remarks", fieldtype: "Small Text", label: __("Reason (shown to the employee)"), reqd: 1 },
					(values) => review(frm, "Rejected", values.remarks),
					__("Reject document"),
					__("Reject")
				);
			});
		}
		if (frm.doc.file) {
			frm.add_custom_button(__("Open File"), () => window.open(frm.doc.file, "_blank"));
		}
	},
});

function review(frm, status, remarks) {
	frappe.call({
		method: "hrms_custom.api.documents.verify_document",
		args: { document: frm.doc.name, status, remarks },
		freeze: true,
		callback(r) {
			if (r.success) {
				frappe.show_alert({ message: r.message, indicator: status === "Verified" ? "green" : "orange" });
				frm.reload_doc();
			}
		},
		error(r) {
			const body = r.responseJSON || {};
			frappe.msgprint({ title: __("Could not update"), message: body.message || __("Something went wrong"), indicator: "red" });
		},
	});
}
