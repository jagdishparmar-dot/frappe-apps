frappe.ui.form.on("Employee", {
	refresh(frm) {
		render_profile_header(frm);
		if (frm.is_new()) return;

		const status = frm.doc.onboarding_status;
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

const STATUS_COLORS = {
	Active: "green",
	Inactive: "gray",
	Suspended: "orange",
	Left: "red",
};

const ONBOARDING_COLORS = {
	Invited: "blue",
	"Pending Verification": "orange",
	Verified: "green",
};

function render_profile_header(frm) {
	const field = frm.get_field("profile_header");
	if (!field) return;
	frm.toggle_display("profile_header", !frm.is_new());
	if (frm.is_new()) {
		field.$wrapper.empty();
		return;
	}

	const doc = frm.doc;
	const name = frappe.utils.escape_html(doc.employee_name || "");
	const id = frappe.utils.escape_html(doc.name || "");
	const meta = [doc.designation, doc.department].filter(Boolean).map((value) => frappe.utils.escape_html(value));
	const chips = [
		chip(doc.status, STATUS_COLORS[doc.status] || "gray"),
		doc.onboarding_status ? chip(doc.onboarding_status, ONBOARDING_COLORS[doc.onboarding_status] || "gray") : "",
	].join("");

	field.$wrapper.html(`
		<div class="employee-profile-header">
			${photo_html(doc)}
			<div class="employee-profile-header__main">
				<div class="employee-profile-header__name">${name}</div>
				<div class="employee-profile-header__id">${id}</div>
				${meta.length ? `<div class="employee-profile-header__meta">${meta.join(" · ")}</div>` : ""}
				<div class="employee-profile-header__chips">${chips}</div>
			</div>
			<div class="employee-profile-header__links">
				<button type="button" class="btn btn-default btn-sm" data-route="documents">${__("Documents")}</button>
				<button type="button" class="btn btn-default btn-sm" data-route="attendance">${__("Attendance")}</button>
				<button type="button" class="btn btn-default btn-sm" data-route="leave">${__("Leave")}</button>
			</div>
		</div>
	`);
	field.$wrapper.find("[data-route]").on("click", (event) => open_shortcut(frm, event.currentTarget.dataset.route));
}

function photo_html(doc) {
	if (doc.image) {
		const src = frappe.utils.escape_html(doc.image);
		const alt = frappe.utils.escape_html(doc.employee_name || "");
		return `<img class="employee-profile-header__photo" src="${src}" alt="${alt}">`;
	}
	return `<div class="employee-profile-header__photo employee-profile-header__initials">${frappe.utils.escape_html(initials(doc))}</div>`;
}

function initials(doc) {
	const first = (doc.first_name || "").trim();
	const last = (doc.last_name || "").trim();
	if (first && last) return (first[0] + last[0]).toUpperCase();
	const name = (doc.employee_name || "").replace(/\s+/g, "");
	return (name.slice(0, 2) || "?").toUpperCase();
}

function chip(label, color) {
	return `<span class="indicator-pill ${color}">${frappe.utils.escape_html(label)}</span>`;
}

function open_shortcut(frm, route) {
	if (route === "documents") {
		frappe.route_options = { employee: frm.doc.name };
		frappe.set_route("List", "Employee Document");
		return;
	}
	if (route === "attendance") {
		frappe.route_options = {
			employee: frm.doc.name,
			company: frm.doc.company,
			month: frappe.datetime.now_date().slice(0, 7),
		};
		frappe.set_route("query-report", "Attendance Summary");
		return;
	}
	frappe.route_options = { employee: frm.doc.name };
	frappe.set_route("List", "Leave Application");
}

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
				frappe.msgprint({
					title: __("Invite failed"),
					message: body.message || __("Something went wrong"),
					indicator: "red",
				});
			},
		});

	if (frm.is_dirty()) {
		frm.save().then(run);
	} else {
		run();
	}
}

frappe.dom.set_style(`
.employee-profile-header {
	display: flex;
	gap: 16px;
	align-items: center;
	margin-bottom: 16px;
	padding: 16px;
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius-lg);
	background: var(--card-bg);
}
.employee-profile-header__photo {
	width: 64px;
	height: 64px;
	border-radius: 8px;
	object-fit: cover;
	flex: 0 0 64px;
}
.employee-profile-header__initials {
	display: flex;
	align-items: center;
	justify-content: center;
	background: var(--control-bg);
	color: var(--text-muted);
	font-weight: 600;
}
.employee-profile-header__main { flex: 1; min-width: 0; }
.employee-profile-header__name { font-size: 18px; font-weight: 600; }
.employee-profile-header__id,
.employee-profile-header__meta { color: var(--text-muted); }
.employee-profile-header__chips { display: flex; gap: 8px; margin-top: 8px; }
.employee-profile-header__links { display: flex; gap: 8px; flex-wrap: wrap; }
`, "employee-profile-header-style");
