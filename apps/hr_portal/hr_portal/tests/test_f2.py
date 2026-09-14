from __future__ import annotations

import frappe
from frappe.tests import IntegrationTestCase

from hr_portal.lib.attendance_shift import (
	build_shift_occurrence,
	compute_punch_in_status,
	finalize_attendance_on_punch_out,
	resolve_punch_in_occurrence,
	shift_from_employee_fallback,
	zoned_datetime_to_utc_ms,
)
from hr_portal.services.punch_service import process_punch


def _work_shift(**kwargs):
	base = shift_from_employee_fallback("09:00", "18:00", 15)
	data = base.__dict__.copy()
	data.update(kwargs)
	from hr_portal.lib.attendance_shift import WorkShift

	return WorkShift(**data)


class TestF2ShiftLogic(IntegrationTestCase):
	def test_general_on_time_punch_in_status(self):
		shift = _work_shift(start_time="09:00", end_time="18:00", late_grace_minutes=15)
		date_iso = "2026-07-28"
		occurrence = build_shift_occurrence(shift, date_iso, "Asia/Kolkata")
		in_ms = zoned_datetime_to_utc_ms(date_iso, "09:00", "Asia/Kolkata")
		self.assertEqual(compute_punch_in_status(in_ms, occurrence), "PRESENT")

	def test_general_late_punch_in_status(self):
		shift = _work_shift(start_time="09:00", end_time="18:00", late_grace_minutes=15)
		date_iso = "2026-07-28"
		occurrence = build_shift_occurrence(shift, date_iso, "Asia/Kolkata")
		in_ms = zoned_datetime_to_utc_ms(date_iso, "09:20", "Asia/Kolkata")
		self.assertEqual(compute_punch_in_status(in_ms, occurrence), "LATE")

	def test_cross_midnight_finalize(self):
		shift = _work_shift(
			start_time="16:00",
			end_time="00:30",
			crosses_midnight=True,
			shift_type="cross_midnight",
			full_day_minutes=510,
			half_day_minutes=255,
			overtime_after_minutes=510,
		)
		date_iso = "2026-07-28"
		occurrence = build_shift_occurrence(shift, date_iso, "Asia/Kolkata")
		in_ms = zoned_datetime_to_utc_ms(date_iso, "16:00", "Asia/Kolkata")
		out_ms = zoned_datetime_to_utc_ms("2026-07-29", "00:30", "Asia/Kolkata")
		result = finalize_attendance_on_punch_out("PRESENT", in_ms, out_ms, occurrence)
		self.assertEqual(result.status, "PRESENT")
		self.assertGreaterEqual(result.total_minutes, 500)

	def test_half_day_finalize(self):
		shift = _work_shift(
			start_time="09:00",
			end_time="18:00",
			full_day_minutes=540,
			half_day_minutes=270,
			overtime_after_minutes=540,
		)
		date_iso = "2026-07-28"
		occurrence = build_shift_occurrence(shift, date_iso, "Asia/Kolkata")
		in_ms = zoned_datetime_to_utc_ms(date_iso, "09:00", "Asia/Kolkata")
		out_ms = zoned_datetime_to_utc_ms(date_iso, "13:00", "Asia/Kolkata")
		result = finalize_attendance_on_punch_out("PRESENT", in_ms, out_ms, occurrence)
		self.assertEqual(result.status, "HALF_DAY")

	def test_early_punch_in_window(self):
		shift = _work_shift(start_time="08:00", end_time="16:30")
		now_ms = zoned_datetime_to_utc_ms("2026-07-28", "06:00", "Asia/Kolkata")
		occurrence = resolve_punch_in_occurrence(shift, now_ms, "Asia/Kolkata")
		self.assertIsNotNone(occurrence)
		self.assertEqual(occurrence.shift_date_iso, "2026-07-28")


class TestF2PunchFlow(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.db.commit()

	def setUp(self):
		self._created: list[tuple[str, str]] = []
		self.site = frappe.get_doc(
			{
				"doctype": "HR Site",
				"site_name": "F2 Test Site",
				"status": "Active",
				"latitude": 19.077,
				"longitude": 72.998,
				"radius_meters": 500,
			}
		)
		self.site.insert(ignore_permissions=True)
		self._created.append(("HR Site", self.site.name))

		self.shift = frappe.get_doc(
			{
				"doctype": "HR Shift",
				"shift_name": "F2 General",
				"code": "F2GEN",
				"status": "Active",
				"shift_type": "general",
				"start_time": "06:00",
				"end_time": "23:59",
				"punch_in_before_minutes": 720,
				"punch_in_after_minutes": 720,
				"punch_out_before_minutes": 720,
				"punch_out_after_minutes": 720,
			}
		)
		self.shift.insert(ignore_permissions=True)
		self._created.append(("HR Shift", self.shift.name))

		self.employee = frappe.get_doc(
			{
				"doctype": "HR Employee",
				"employee_code": "F2EMP",
				"employee_name": "F2 Employee",
				"email": "f2.emp@example.com",
				"status": "Active",
				"portal_role": "HR Employee",
				"attendance_policy": "geofenced",
				"primary_site": self.site.name,
				"default_shift": self.shift.name,
				"work_shift_start": "09:00",
				"work_shift_end": "18:00",
			}
		)
		self.employee.insert(ignore_permissions=True)
		self._created.append(("HR Employee", self.employee.name))
		frappe.db.commit()

	def tearDown(self):
		for doctype in ("HR Attendance", "HR Regularization"):
			for row in frappe.get_all(doctype, filters={"employee": self.employee.name}, pluck="name"):
				if frappe.db.exists(doctype, row):
					frappe.delete_doc(doctype, row, force=1)
		for doctype, name in reversed(self._created):
			if frappe.db.exists(doctype, name):
				frappe.delete_doc(doctype, name, force=1)
		frappe.db.commit()

	def test_punch_in_out_inside_geofence(self):
		date_iso = frappe.utils.today()
		now_ms = zoned_datetime_to_utc_ms(date_iso, "06:05", "Asia/Kolkata")
		punch_in = process_punch(
			self.employee.name,
			"in",
			19.077,
			72.998,
			now_ms=now_ms,
		)
		self.assertIn("Punched in", punch_in["message"])
		self.assertEqual(punch_in["record"]["status"], "PRESENT")

		out_ms = now_ms + 8 * 60 * 60 * 1000
		punch_out = process_punch(
			self.employee.name,
			"out",
			19.077,
			72.998,
			now_ms=out_ms,
		)
		self.assertIn("Punched out", punch_out["message"])
		self.assertGreater(punch_out["record"]["totalMinutes"], 400)

	def test_outside_geofence_rejected(self):
		now_ms = zoned_datetime_to_utc_ms(frappe.utils.today(), "10:00", "Asia/Kolkata")
		with self.assertRaises(Exception):
			process_punch(self.employee.name, "in", 0.0, 0.0, now_ms=now_ms)
