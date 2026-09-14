from __future__ import annotations

import csv
import io
from datetime import timedelta

import frappe
from frappe.utils import add_days, getdate, today


def _yesterday_iso() -> str:
	return str(add_days(today(), -1))


def _rows_for_date(date_iso: str) -> list[list]:
	records = frappe.get_all(
		"HR Attendance",
		filters={"date_iso": date_iso},
		fields=[
			"employee",
			"date_iso",
			"status",
			"clock_in_time",
			"clock_out_time",
			"total_minutes",
			"location_name",
		],
		order_by="employee asc",
		limit=5000,
	)
	rows: list[list] = []
	for rec in records:
		emp = frappe.db.get_value(
			"HR Employee", rec.employee, ["employee_name", "employee_code"], as_dict=True
		) or {}
		rows.append(
			[
				emp.get("employee_name") or rec.employee,
				emp.get("employee_code") or "",
				rec.date_iso,
				rec.status,
				rec.clock_in_time or "",
				rec.clock_out_time or "",
				rec.total_minutes or 0,
				rec.location_name or "",
			]
		)
	return rows


def send_daily_report() -> None:
	settings = frappe.get_single("HR Settings")
	if not settings.enabled:
		return
	recipient = (settings.contact_email or "").strip()
	if not recipient:
		return

	date_iso = _yesterday_iso()
	buffer = io.StringIO()
	writer = csv.writer(buffer)
	writer.writerow(["Employee", "Code", "Date", "Status", "In", "Out", "Minutes", "Location"])
	writer.writerows(_rows_for_date(date_iso))

	frappe.sendmail(
		recipients=[recipient],
		subject=f"Daily attendance report — {date_iso}",
		message=f"Attached CSV covers attendance for {date_iso}.",
		attachments=[
			{
				"fname": f"attendance-{date_iso}.csv",
				"fcontent": buffer.getvalue(),
			}
		],
		now=True,
	)
