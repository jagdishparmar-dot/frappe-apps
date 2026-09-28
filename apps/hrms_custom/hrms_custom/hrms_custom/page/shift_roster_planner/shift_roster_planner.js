frappe.pages["shift-roster-planner"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Shift Roster Planner"),
		single_column: true,
	});
	wrapper.roster_planner = new hrms.ShiftRosterPlanner(wrapper);
};

frappe.pages["shift-roster-planner"].refresh = function (wrapper) {
	if (wrapper.roster_planner) {
		wrapper.roster_planner.refresh();
	}
};

frappe.provide("hrms");

hrms.ShiftRosterPlanner = class ShiftRosterPlanner {
	constructor(wrapper) {
		this.wrapper = wrapper;
		this.page = wrapper.page;
		this.$body = $("<div class='roster-planner'>").appendTo(this.page.main);
		this.data = null;
		this.make_filters();
		this.load();
	}

	make_filters() {
		const today = frappe.datetime.now_date();
		this.month = this.page.add_field({
			fieldname: "month",
			label: __("Month"),
			fieldtype: "Data",
			default: today.slice(0, 7),
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
		this.page.set_primary_action(__("Save roster"), () => this.save());
		this.page.add_inner_button(__("Reload"), () => this.load());
	}

	refresh() {
		if (!this.data) {
			this.load();
		}
	}

	load() {
		const month = (this.month.get_value() || "").trim();
		if (!/^\d{4}-\d{2}$/.test(month)) {
			frappe.msgprint(__("Month must be YYYY-MM"));
			return;
		}
		frappe
			.call({
				method: "hrms_custom.api.shift.get_roster",
				args: {
					month,
					company: this.company.get_value() || "",
					department: this.department.get_value() || "",
				},
			})
			.then((r) => {
				if (r.exc || r.success === false) {
					frappe.msgprint({
						title: __("Could not load roster"),
						message: r.message || __("Something went wrong"),
						indicator: "red",
					});
					return;
				}
				this.data = r.data || (r.message && r.message.data) || r.message || {};
				this.render();
			});
	}

	render() {
		const data = this.data || {};
		const days = data.days || [];
		const employees = data.employees || [];
		const types = data.shift_types || [];
		const cells = data.cells || {};

		if (!employees.length) {
			this.$body.html(
				`<div class="text-muted" style="padding: 1.5rem;">${__(
					"No active employees match these filters."
				)}</div>`
			);
			return;
		}

		const options = [`<option value="">—</option>`]
			.concat(
				types.map(
					(s) =>
						`<option value="${frappe.utils.escape_html(s.name)}">${frappe.utils.escape_html(
							s.name
						)}</option>`
				)
			)
			.join("");

		const head = days
			.map((day) => {
				const klass = day.is_holiday ? "holiday" : "";
				const title = day.holiday ? day.holiday.description : "";
				return `<th class="${klass}" title="${frappe.utils.escape_html(title)}">
					<div>${frappe.utils.escape_html(day.date.slice(8))}</div>
					<div class="text-muted" style="font-weight:normal">${frappe.utils.escape_html(day.weekday)}</div>
				</th>`;
			})
			.join("");

		const rows = employees
			.map((emp) => {
				const emp_cells = cells[emp.name] || {};
				const tds = days
					.map((day) => {
						const cell = emp_cells[day.date] || {};
						const source = cell.source || "";
						return `<td class="${day.is_holiday ? "holiday" : ""}">
							<select class="form-control roster-cell" data-employee="${frappe.utils.escape_html(
								emp.name
							)}" data-date="${day.date}" data-source="${source}">
								${options}
							</select>
						</td>`;
					})
					.join("");
				return `<tr>
					<td class="sticky">
						<div>${frappe.utils.escape_html(emp.employee_name || emp.name)}</div>
						<div class="text-muted">${frappe.utils.escape_html(emp.name)}</div>
					</td>
					${tds}
				</tr>`;
			})
			.join("");

		this.$body.html(`
			<div class="roster-planner-meta text-muted">
				${__("Pick a shift for each day, then Save. Clearing a cell removes the roster override.")}
			</div>
			<div class="roster-planner-wrap">
				<table class="roster-planner-table">
					<thead>
						<tr>
							<th class="sticky">${__("Employee")}</th>
							${head}
						</tr>
					</thead>
					<tbody>${rows}</tbody>
				</table>
			</div>
		`);

		this.$body.find("select.roster-cell").each((_, el) => {
			const $el = $(el);
			const emp = $el.data("employee");
			const date = $el.data("date");
			const cell = (cells[emp] || {})[date];
			if (cell && cell.shift_type) {
				$el.val(cell.shift_type);
			}
		});
	}

	save() {
		if (!this.data) {
			return;
		}
		const entries = [];
		this.$body.find("select.roster-cell").each((_, el) => {
			const $el = $(el);
			entries.push({
				employee: $el.data("employee"),
				date: $el.data("date"),
				shift_type: $el.val() || "",
			});
		});
		frappe.call({
			method: "hrms_custom.api.shift.bulk_assign_roster",
			args: { entries },
			freeze: true,
			freeze_message: __("Saving roster"),
			callback: (r) => {
				if (r.exc || r.success === false) {
					frappe.msgprint({
						title: __("Could not save"),
						message: r.message || __("Something went wrong"),
						indicator: "red",
					});
					return;
				}
				const stats = r.data || {};
				frappe.show_alert({
					message: r.message || __("Saved {0}, cleared {1}", [stats.saved || 0, stats.cleared || 0]),
					indicator: "green",
				});
				this.load();
			},
			error: (r) => {
				const body = r.responseJSON || {};
				frappe.msgprint({
					title: __("Could not save"),
					message: body.message || __("Something went wrong"),
					indicator: "red",
				});
			},
		});
	}
};
