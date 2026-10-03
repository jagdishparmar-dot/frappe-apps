frappe.pages["live-attendance"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Live Attendance"),
		single_column: true,
	});
	wrapper.live_attendance = new hrms.LiveAttendance(wrapper);
};

frappe.pages["live-attendance"].refresh = function (wrapper) {
	if (wrapper.live_attendance) {
		wrapper.live_attendance.refresh();
	}
};

frappe.provide("hrms");

hrms.LiveAttendance = class LiveAttendance {
	constructor(wrapper) {
		this.wrapper = wrapper;
		this.page = wrapper.page;
		this.$body = $("<div class='live-attendance'>").appendTo(this.page.main);
		this.data = null;
		this._timer = null;
		this.make_filters();
		this.load();
		this.start_poll();
	}

	make_filters() {
		this.date = this.page.add_field({
			fieldname: "date",
			label: __("Date"),
			fieldtype: "Date",
			default: frappe.datetime.now_date(),
			reqd: 1,
			change: () => this.load(),
		});
		this.company = this.page.add_field({
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			change: () => this.load(),
		});
		this.department = this.page.add_field({
			fieldname: "department",
			label: __("Department"),
			fieldtype: "Link",
			options: "Department",
			change: () => this.load(),
		});
		this.page.set_primary_action(__("Reload"), () => this.load());
	}

	refresh() {
		this.start_poll();
		if (!this.data) {
			this.load();
		}
	}

	start_poll() {
		this.stop_poll();
		this._timer = setInterval(() => this.load({ silent: true }), 60000);
	}

	stop_poll() {
		if (this._timer) {
			clearInterval(this._timer);
			this._timer = null;
		}
	}

	load(opts) {
		const silent = opts && opts.silent;
		const date = this.date.get_value();
		if (!date) {
			frappe.msgprint(__("Date is required"));
			return;
		}
		frappe.call({
			method: "hrms_custom.api.attendance.get_live_attendance",
			args: {
				date,
				company: this.company.get_value() || "",
				department: this.department.get_value() || "",
			},
			freeze: !silent,
			freeze_message: __("Loading attendance"),
			callback: (r) => {
				if (r.exc || r.success === false) {
					if (!silent) {
						frappe.msgprint({
							title: __("Could not load attendance"),
							message: r.message || __("Something went wrong"),
							indicator: "red",
						});
					}
					return;
				}
				this.data = r.data || (r.message && r.message.data) || r.message || {};
				this.render();
			},
			error: (r) => {
				if (silent) {
					return;
				}
				const body = r.responseJSON || {};
				frappe.msgprint({
					title: __("Could not load attendance"),
					message: body.message || __("Something went wrong"),
					indicator: "red",
				});
			},
		});
	}

	render() {
		const data = this.data || {};
		const counts = data.counts || {};
		const employees = data.employees || [];
		const cards = [
			["present", __("Present"), counts.present || 0],
			["half-day", __("Half Day"), counts.half_day || 0],
			["absent", __("Absent"), counts.absent || 0],
			["late", __("Late"), counts.late || 0],
			["on-leave", __("On Leave"), counts.on_leave || 0],
			["week-off", __("Week Off"), counts.week_off || 0],
		]
			.map(
				([klass, label, value]) =>
					`<div class="live-attendance-card ${klass}">
						<div class="label">${frappe.utils.escape_html(label)}</div>
						<div class="value">${cint(value)}</div>
					</div>`
			)
			.join("");

		const rows = employees
			.map((emp) => {
				const status = emp.status || "Absent";
				const badge = status.toLowerCase().replace(/ /g, "-");
				const geo =
					emp.is_within_geofence === 0
						? `<div class="live-attendance-flag">${__("Outside geofence")}</div>`
						: "";
				const tag = emp.regularized
					? `<div class="live-attendance-flag">${__("Regularized")}</div>`
					: "";
				return `<tr>
					<td>
						<div>${frappe.utils.escape_html(emp.employee_name || emp.employee)}</div>
						<div class="text-muted">${frappe.utils.escape_html(emp.employee || "")}</div>
					</td>
					<td>${frappe.utils.escape_html(emp.department || "—")}</td>
					<td>${frappe.utils.escape_html(emp.shift_type || "—")}</td>
					<td><span class="live-attendance-badge ${badge}">${frappe.utils.escape_html(
						status
					)}</span>${tag}</td>
					<td>${this.punch_cell(emp, "in")}${geo}</td>
					<td>${this.punch_cell(emp, "out")}</td>
				</tr>`;
			})
			.join("");

		const table = employees.length
			? `<div class="live-attendance-wrap">
				<table class="live-attendance-table">
					<thead>
						<tr>
							<th>${__("Employee")}</th>
							<th>${__("Department")}</th>
							<th>${__("Shift")}</th>
							<th>${__("Status")}</th>
							<th>${__("In")}</th>
							<th>${__("Out")}</th>
						</tr>
					</thead>
					<tbody>${rows}</tbody>
				</table>
			</div>`
			: `<div class="text-muted" style="padding: 1.5rem;">${__(
					"No active employees match these filters."
				)}</div>`;

		this.$body.html(`
			<div class="live-attendance-meta text-muted">
				<span>${__("Counts use the same present / absent / late / on-leave rules as Attendance Summary.")}</span>
				<span>${__("Updated")} ${frappe.datetime.now_time()} · ${__("refreshes every 60s")}</span>
			</div>
			<div class="live-attendance-cards">${cards}</div>
			${table}
		`);
	}

	punch_cell(emp, side) {
		const effective = this.format_time(side === "in" ? emp.in_time : emp.out_time);
		if (!emp.regularized) {
			return frappe.utils.escape_html(effective);
		}
		const actual = this.format_time(side === "in" ? emp.actual_in_time : emp.actual_out_time);
		const corrected = this.format_time(
			side === "in" ? emp.regularized_in_time : emp.regularized_out_time
		);
		return `<div>${frappe.utils.escape_html(actual)} <span class="text-muted">${__("Actual")}</span></div>
			<div>${frappe.utils.escape_html(corrected)} <span class="text-muted">${__("Regularized")}</span></div>`;
	}

	format_time(value) {
		if (!value) {
			return "—";
		}
		const text = String(value);
		if (text.length >= 16) {
			return text.slice(11, 16);
		}
		if (text.length >= 5 && text.indexOf(":") === 2) {
			return text.slice(0, 5);
		}
		return text;
	}
};
