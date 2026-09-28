frappe.ui.form.on("Employee", {
	refresh(frm) {
		if (frm.is_new()) return;

		const status = frm.doc.onboarding_status;
		if (status) {
			const colors = { Invited: "blue", "Pending Verification": "orange", Verified: "green" };
			frm.dashboard.set_headline_alert(
				__("Onboarding: {0}", [__(status)]),
				colors[status] || "gray"
			);
		}

		const can_invite =
			frm.doc.status !== "Left" &&
			(!status || status === "Invited") &&
			!(frm.doc.status === "Active" && !status);
		if (can_invite && frappe.user.has_role(["System Manager", "HR Admin", "HR Executive"])) {
			frm.add_custom_button(status === "Invited" ? __("Resend Invite") : __("Invite to Onboard"), () =>
				invite(frm)
			);
		}

		if (status === "Pending Verification" && frm.perm[0].write) {
			frm.add_custom_button(__("Mark Verified & Activate"), () => {
				frappe.confirm(__("Mark onboarding verified and activate this employee?"), () => {
					frm.set_value("onboarding_status", "Verified");
					frm.set_value("status", "Active");
					frm.save();
				});
			});
		}
	},
});

function invite(frm) {
	const run = () =>
		frappe.call({
			method: "hrms_custom.api.onboarding.invite_employee",
			args: { employee: frm.doc.name },
			freeze: true,
			callback(r) {
				if (r.success) {
					frappe.show_alert(
						{ message: r.message, indicator: r.data.email_sent ? "green" : "orange" },
						r.data.email_sent ? 5 : 12
					);
					frm.reload_doc();
				}
			},
			error(r) {
				const body = r.responseJSON || {};
				frappe.msgprint({ title: __("Invite failed"), message: body.message || __("Something went wrong"), indicator: "red" });
			},
		});

	if (frm.is_dirty()) {
		frm.save().then(run);
	} else {
		run();
	}
}
