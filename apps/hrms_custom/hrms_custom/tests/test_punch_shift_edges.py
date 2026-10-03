"""Punch-in / punch-out edges for day, midnight-crossing, and 12-hour shifts.

Each shift keeps punches from 4 hours before start until 4 hours after end.
Where that range would meet the next shift, an IN after the previous shift
ended belongs to the later shift, and an OUT up to the midpoint of the gap
stays with the earlier shift. Back-to-back shifts use a 30-minute margin.
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import get_datetime

from hrms_custom.api import attendance as attendance_api
from hrms_custom.tests.utils import get_test_company, make_employee_user
from hrms_custom.utils.reports import (
	employee_date_attendance_rows,
	employee_month_attendance,
	late_early_rows,
	live_attendance,
	log_search_window,
	monthly_attendance_grid_rows,
)

EMPLOYEE_USER = "edge.punch@example.com"


def _info(start, end, grace=15):
	return {
		"start_time": start,
		"end_time": end,
		"is_overnight": 1 if end < start else 0,
		"grace_minutes": grace,
		"early_exit_grace_minutes": 10,
	}


def _owns(day, shift, log_type, when, prev=None, nxt=None):
	lo, hi = log_search_window(day, shift, log_type, prev, nxt)
	stamp = get_datetime(when)
	return lo <= stamp <= hi


class TestPunchShiftEdges(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = get_test_company()
		cls.employee = make_employee_user(EMPLOYEE_USER, cls.company, "Edge Punch", mobile="9000018100")
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		cls._clear()
		frappe.db.commit()
		super().tearDownClass()

	@classmethod
	def _clear(cls):
		for name in frappe.get_all("Employee Checkin", filters={"employee": cls.employee}, pluck="name"):
			frappe.delete_doc("Employee Checkin", name, force=True, ignore_permissions=True)
		for name in frappe.get_all("Shift Assignment", filters={"employee": cls.employee}, pluck="name"):
			frappe.delete_doc("Shift Assignment", name, force=True, ignore_permissions=True)

	def setUp(self):
		frappe.set_user("Administrator")
		self._clear()
		frappe.db.set_value("Company", self.company, "holiday_list", None)
		frappe.db.commit()

	def _shift(self, name, start, end, grace=15, early=10, present=0, half=0):
		fields = {
			"company": self.company,
			"is_active": 1,
			"start_time": start,
			"end_time": end,
			"grace_minutes": grace,
			"early_exit_grace_minutes": early,
			"minimum_hours_present": present,
			"minimum_hours_half_day": half,
			"allow_flexible_hours": 0,
			"working_hours": 0,
		}
		if frappe.db.exists("Shift Type", name):
			doc = frappe.get_doc("Shift Type", name)
			doc.update(fields)
			doc.save(ignore_permissions=True)
			return doc.name
		return (
			frappe.get_doc({"doctype": "Shift Type", "shift_name": name, **fields})
			.insert(ignore_permissions=True)
			.name
		)

	def _assign(self, shift_type, start, end):
		frappe.get_doc(
			{
				"doctype": "Shift Assignment",
				"employee": self.employee,
				"shift_type": shift_type,
				"start_date": start,
				"end_date": end,
				"status": "Active",
			}
		).insert(ignore_permissions=True)

	def _punch(self, when, log_type="IN"):
		frappe.get_doc(
			{
				"doctype": "Employee Checkin",
				"employee": self.employee,
				"log_type": log_type,
				"time": when,
				"latitude": 23.0225,
				"longitude": 72.5714,
				"is_within_geofence": 1,
				"device_id": "edge-test",
			}
		).insert(ignore_permissions=True)

	def _rows(self, start, end):
		frappe.db.commit()
		rows = employee_date_attendance_rows(
			{"from_date": start, "to_date": end, "employee": self.employee}
		)
		return {row["date"]: row for row in rows}

	def _variances(self, start, end):
		rows = late_early_rows({"from_date": start, "to_date": end, "employee": self.employee})
		return {row["date"]: row for row in rows}

	def _expect(self, row, status, inn=None, out=None, minutes=None, late=0):
		self.assertIsNotNone(row, "missing attendance row")
		self.assertEqual(row["status"], status, row)
		self.assertEqual(row["is_late"], late, row)
		if inn is None:
			self.assertIsNone(row["in_time"], row)
		else:
			self.assertEqual(get_datetime(row["in_time"]), get_datetime(inn), row)
		if out is None:
			self.assertIsNone(row["out_time"], row)
		else:
			self.assertEqual(get_datetime(row["out_time"]), get_datetime(out), row)
		self.assertEqual(row["worked_minutes"], minutes, row)

	def _expect_variance(self, variances, day, late_minutes=0, early_minutes=0):
		row = variances.get(day)
		if not late_minutes and not early_minutes:
			self.assertIsNone(row, row)
			return
		self.assertIsNotNone(row, day)
		self.assertEqual(row["late_minutes"], late_minutes, row)
		self.assertEqual(row["early_minutes"], early_minutes, row)

	def test_windows_assign_boundary_punches_once(self):
		"""A punch on the shared edge belongs to exactly one of the two shifts."""
		night = _info("20:00:00", "08:00:00")
		day = _info("09:00:00", "18:00:00")
		twelve_day = _info("08:00:00", "20:00:00")
		claims = (
			# Gap: night ends 08:00, day starts 09:00. Split for OUTs is 08:30.
			("2026-06-16", night, "2026-06-17", day, "IN", "2026-06-17 08:00:00", "earlier"),
			("2026-06-16", night, "2026-06-17", day, "IN", "2026-06-17 08:00:01", "later"),
			("2026-06-16", night, "2026-06-17", day, "IN", "2026-06-17 08:55:00", "later"),
			("2026-06-16", night, "2026-06-17", day, "IN", "2026-06-17 09:00:00", "later"),
			("2026-06-16", night, "2026-06-17", day, "OUT", "2026-06-17 08:00:00", "earlier"),
			("2026-06-16", night, "2026-06-17", day, "OUT", "2026-06-17 08:05:00", "earlier"),
			("2026-06-16", night, "2026-06-17", day, "OUT", "2026-06-17 08:30:00", "earlier"),
			("2026-06-16", night, "2026-06-17", day, "OUT", "2026-06-17 08:30:01", "later"),
			("2026-06-16", night, "2026-06-17", day, "OUT", "2026-06-17 18:00:00", "later"),
			# Back-to-back 12-hour shifts share 08:00. Early IN / late OUT stay distinct.
			("2026-06-18", night, "2026-06-19", twelve_day, "IN", "2026-06-19 07:55:00", "later"),
			("2026-06-18", night, "2026-06-19", twelve_day, "IN", "2026-06-19 08:00:00", "later"),
			("2026-06-18", night, "2026-06-19", twelve_day, "OUT", "2026-06-19 08:00:00", "earlier"),
			("2026-06-18", night, "2026-06-19", twelve_day, "OUT", "2026-06-19 08:05:00", "earlier"),
			("2026-06-18", night, "2026-06-19", twelve_day, "OUT", "2026-06-19 20:00:00", "later"),
		)
		for earlier_day, earlier, later_day, later, log_type, when, owner in claims:
			with self.subTest(when=when, log_type=log_type, owner=owner):
				on_earlier = _owns(get_datetime(earlier_day).date(), earlier, log_type, when, nxt=later)
				on_later = _owns(get_datetime(later_day).date(), later, log_type, when, prev=earlier)
				self.assertNotEqual(on_earlier, on_later, f"{log_type} {when} claimed by both or neither")
				self.assertEqual(on_earlier, owner == "earlier", f"{log_type} {when}")

	def test_standard_day_boundaries(self):
		self._shift("Edge Day", "09:00:00", "18:00:00", present=8, half=4)
		self._assign("Edge Day", "2026-06-01", "2026-06-30")
		# day, in, out, status, late flag, worked minutes, late minutes, early minutes
		cases = (
			("2026-06-01", "09:00:00", "18:00:00", "Present", 0, 540, 0, 0),
			("2026-06-02", "08:55:00", "18:05:00", "Present", 0, 550, 0, 0),
			("2026-06-03", "09:15:00", "18:00:00", "Present", 0, 525, 0, 0),
			("2026-06-04", "09:16:00", "18:00:00", "Late", 1, 524, 1, 0),
			("2026-06-05", "09:00:00", "17:50:00", "Present", 0, 530, 0, 0),
			("2026-06-06", "09:00:00", "17:49:00", "Present", 0, 529, 0, 11),
			("2026-06-07", "09:40:00", "17:30:00", "Half Day", 1, 470, 25, 30),
			("2026-06-08", "09:00:00", "13:00:00", "Half Day", 0, 240, 0, 300),
			("2026-06-09", "09:00:00", "12:59:00", "Absent", 0, 239, 0, 301),
			("2026-06-10", "09:00:00", "17:00:00", "Present", 0, 480, 0, 60),
			("2026-06-11", "05:00:00", "18:00:00", "Present", 0, 780, 0, 0),
			("2026-06-13", "09:00:00", "22:00:00", "Present", 0, 780, 0, 0),
		)
		for day, inn, out, *_rest in cases:
			self._punch(f"{day} {inn}")
			self._punch(f"{day} {out}", "OUT")
		# One second outside the 4-hour slack is not this shift's punch.
		self._punch("2026-06-12 04:59:59")
		self._punch("2026-06-12 18:00:00", "OUT")
		self._punch("2026-06-14 09:00:00")
		self._punch("2026-06-14 22:00:01", "OUT")
		# Consecutive days must keep their own pair.
		self._punch("2026-06-15 09:00:00")
		self._punch("2026-06-15 18:00:00", "OUT")
		self._punch("2026-06-16 09:10:00")
		self._punch("2026-06-16 18:10:00", "OUT")

		rows = self._rows("2026-06-01", "2026-06-16")
		variances = self._variances("2026-06-01", "2026-06-16")
		for day, inn, out, status, late, minutes, late_minutes, early_minutes in cases:
			with self.subTest(day=day, status=status):
				self._expect(rows[day], status, f"{day} {inn}", f"{day} {out}", minutes, late)
				self._expect_variance(variances, day, late_minutes, early_minutes)

		self._expect(rows["2026-06-12"], "Absent")
		self._expect_variance(variances, "2026-06-12")
		self._expect(rows["2026-06-14"], "Present", "2026-06-14 09:00:00", None, None, 0)
		self._expect(rows["2026-06-15"], "Present", "2026-06-15 09:00:00", "2026-06-15 18:00:00", 540, 0)
		self._expect(rows["2026-06-16"], "Present", "2026-06-16 09:10:00", "2026-06-16 18:10:00", 540, 0)
		self._expect_variance(variances, "2026-06-16")

	def test_crossover_shift_boundaries(self):
		self._shift("Edge Cross", "22:00:00", "06:00:00", present=7, half=4)
		self._assign("Edge Cross", "2026-06-01", "2026-06-30")
		pairs = (
			("2026-06-01", "2026-06-01 22:00:00", "2026-06-02 06:00:00", "Present", 0, 480, 0, 0),
			("2026-06-02", "2026-06-02 21:55:00", "2026-06-03 06:05:00", "Present", 0, 490, 0, 0),
			("2026-06-03", "2026-06-03 22:15:00", "2026-06-04 06:00:00", "Present", 0, 465, 0, 0),
			("2026-06-04", "2026-06-04 22:16:00", "2026-06-05 06:00:00", "Late", 1, 464, 1, 0),
			("2026-06-05", "2026-06-05 22:00:00", "2026-06-06 05:50:00", "Present", 0, 470, 0, 0),
			("2026-06-06", "2026-06-06 22:00:00", "2026-06-07 05:49:00", "Present", 0, 469, 0, 11),
			("2026-06-07", "2026-06-07 22:00:00", "2026-06-08 02:00:00", "Half Day", 0, 240, 0, 240),
			("2026-06-08", "2026-06-08 18:00:00", "2026-06-09 06:00:00", "Present", 0, 720, 0, 0),
			("2026-06-10", "2026-06-10 22:00:00", "2026-06-11 10:00:00", "Present", 0, 720, 0, 0),
		)
		for _day, inn, out, *_rest in pairs:
			self._punch(inn)
			self._punch(out, "OUT")
		self._punch("2026-06-09 17:59:59")
		self._punch("2026-06-10 06:00:00", "OUT")
		self._punch("2026-06-11 22:00:00")
		self._punch("2026-06-12 10:00:01", "OUT")

		rows = self._rows("2026-06-01", "2026-06-12")
		variances = self._variances("2026-06-01", "2026-06-12")
		for day, inn, out, status, late, minutes, late_minutes, early_minutes in pairs:
			with self.subTest(day=day):
				self._expect(rows[day], status, inn, out, minutes, late)
				self._expect_variance(variances, day, late_minutes, early_minutes)
				# The morning after the shift starts is not a second attendance day.
				if day != "2026-06-01":
					continue
				self._expect(rows["2026-06-02"], "Present", pairs[1][1], pairs[1][2], 490, 0)

		self._expect(rows["2026-06-09"], "Absent")
		self._expect(rows["2026-06-11"], "Present", "2026-06-11 22:00:00", None, None, 0)

	def test_twelve_hour_day_boundaries(self):
		self._shift("Edge 12 Day", "08:00:00", "20:00:00", present=11, half=6)
		self._assign("Edge 12 Day", "2026-06-01", "2026-06-30")
		cases = (
			("2026-06-01", "08:00:00", "20:00:00", "Present", 0, 720, 0, 0),
			("2026-06-02", "07:55:00", "20:05:00", "Present", 0, 730, 0, 0),
			("2026-06-03", "08:15:00", "20:00:00", "Present", 0, 705, 0, 0),
			("2026-06-04", "08:16:00", "20:00:00", "Late", 1, 704, 1, 0),
			("2026-06-05", "08:00:00", "19:50:00", "Present", 0, 710, 0, 0),
			("2026-06-06", "08:00:00", "19:49:00", "Present", 0, 709, 0, 11),
			("2026-06-07", "08:00:00", "14:00:00", "Half Day", 0, 360, 0, 360),
			("2026-06-08", "08:00:00", "13:59:00", "Absent", 0, 359, 0, 361),
			("2026-06-09", "04:00:00", "20:00:00", "Present", 0, 960, 0, 0),
		)
		for day, inn, out, *_rest in cases:
			self._punch(f"{day} {inn}")
			self._punch(f"{day} {out}", "OUT")
		self._punch("2026-06-10 03:59:59")
		self._punch("2026-06-10 20:00:00", "OUT")
		self._punch("2026-06-11 08:00:00")
		self._punch("2026-06-12 00:00:00", "OUT")
		self._punch("2026-06-12 08:00:00")
		self._punch("2026-06-13 00:00:01", "OUT")

		rows = self._rows("2026-06-01", "2026-06-13")
		variances = self._variances("2026-06-01", "2026-06-13")
		for day, inn, out, status, late, minutes, late_minutes, early_minutes in cases:
			with self.subTest(day=day):
				self._expect(rows[day], status, f"{day} {inn}", f"{day} {out}", minutes, late)
				self._expect_variance(variances, day, late_minutes, early_minutes)
		self._expect(rows["2026-06-10"], "Absent")
		self._expect(rows["2026-06-11"], "Present", "2026-06-11 08:00:00", "2026-06-12 00:00:00", 960, 0)
		self._expect(rows["2026-06-12"], "Present", "2026-06-12 08:00:00", None, None, 0)

	def test_twelve_hour_night_crosses_midnight(self):
		self._shift("Edge 12 Night", "20:00:00", "08:00:00", present=11, half=6)
		self._assign("Edge 12 Night", "2026-06-01", "2026-06-30")
		pairs = (
			("2026-06-01", "2026-06-01 20:00:00", "2026-06-02 08:00:00", "Present", 0, 720, 0, 0),
			("2026-06-02", "2026-06-02 20:00:00", "2026-06-03 08:00:00", "Present", 0, 720, 0, 0),
			("2026-06-04", "2026-06-04 19:55:00", "2026-06-05 08:05:00", "Present", 0, 730, 0, 0),
			("2026-06-05", "2026-06-05 20:15:00", "2026-06-06 08:00:00", "Present", 0, 705, 0, 0),
			("2026-06-06", "2026-06-06 20:16:00", "2026-06-07 08:00:00", "Late", 1, 704, 1, 0),
			("2026-06-07", "2026-06-07 20:00:00", "2026-06-08 07:50:00", "Present", 0, 710, 0, 0),
			("2026-06-08", "2026-06-08 20:00:00", "2026-06-09 07:49:00", "Present", 0, 709, 0, 11),
			("2026-06-09", "2026-06-09 16:00:00", "2026-06-10 08:00:00", "Present", 0, 960, 0, 0),
			("2026-06-11", "2026-06-11 20:00:00", "2026-06-12 12:00:00", "Present", 0, 960, 0, 0),
		)
		for _day, inn, out, *_rest in pairs:
			self._punch(inn)
			self._punch(out, "OUT")
		self._punch("2026-06-10 15:59:59")
		self._punch("2026-06-11 08:00:00", "OUT")
		self._punch("2026-06-12 20:00:00")
		self._punch("2026-06-13 12:00:01", "OUT")

		rows = self._rows("2026-06-01", "2026-06-13")
		variances = self._variances("2026-06-01", "2026-06-13")
		for day, inn, out, status, late, minutes, late_minutes, early_minutes in pairs:
			with self.subTest(day=day):
				self._expect(rows[day], status, inn, out, minutes, late)
				self._expect_variance(variances, day, late_minutes, early_minutes)
		# Jun 3 has the morning OUT from Jun 2 and no IN of its own.
		self._expect(rows["2026-06-03"], "Absent")
		self._expect(rows["2026-06-10"], "Absent")
		self._expect(rows["2026-06-12"], "Present", "2026-06-12 20:00:00", None, None, 0)
		month = employee_month_attendance(self.employee, "2026-06")
		self.assertEqual(month["days"]["2026-06-01"]["status"], "Present")
		self.assertEqual(month["days"]["2026-06-01"]["out_time"], "2026-06-02 08:00:00")
		self.assertIsNone(month["days"]["2026-06-03"]["in_time"])

	def test_night_then_morning_shift_does_not_share_punches(self):
		self._shift("Edge 12 Night", "20:00:00", "08:00:00", present=11, half=6)
		self._shift("Edge Day", "09:00:00", "18:00:00", present=8, half=4)
		self._assign("Edge 12 Night", "2026-06-16", "2026-06-16")
		self._assign("Edge Day", "2026-06-17", "2026-06-17")
		self._punch("2026-06-16 20:00:00")
		self._punch("2026-06-17 08:05:00", "OUT")
		self._punch("2026-06-17 08:55:00")
		self._punch("2026-06-17 18:05:00", "OUT")
		# A later pair where only one shift was worked.
		self._assign("Edge 12 Night", "2026-06-22", "2026-06-22")
		self._assign("Edge Day", "2026-06-23", "2026-06-23")
		self._punch("2026-06-23 09:00:00")
		self._punch("2026-06-23 18:00:00", "OUT")
		self._assign("Edge 12 Night", "2026-06-24", "2026-06-24")
		self._assign("Edge Day", "2026-06-25", "2026-06-25")
		self._punch("2026-06-24 20:00:00")
		self._punch("2026-06-25 08:00:00", "OUT")

		rows = self._rows("2026-06-16", "2026-06-25")
		variances = self._variances("2026-06-16", "2026-06-25")
		self._expect(rows["2026-06-16"], "Present", "2026-06-16 20:00:00", "2026-06-17 08:05:00", 725, 0)
		self._expect(rows["2026-06-17"], "Present", "2026-06-17 08:55:00", "2026-06-17 18:05:00", 550, 0)
		self._expect_variance(variances, "2026-06-16")
		self._expect_variance(variances, "2026-06-17")
		self._expect(rows["2026-06-22"], "Absent")
		self._expect(rows["2026-06-23"], "Present", "2026-06-23 09:00:00", "2026-06-23 18:00:00", 540, 0)
		self._expect(rows["2026-06-24"], "Present", "2026-06-24 20:00:00", "2026-06-25 08:00:00", 720, 0)
		self._expect(rows["2026-06-25"], "Absent")

		live = live_attendance({"date": "2026-06-17", "employee": self.employee})
		self.assertEqual(live["employees"][0]["in_time"], "2026-06-17 08:55:00")
		self.assertEqual(live["employees"][0]["out_time"], "2026-06-17 18:05:00")
		grid = monthly_attendance_grid_rows({"month": "2026-06", "employee": self.employee})
		self.assertEqual(grid[0]["day_16"], "Present")
		self.assertEqual(grid[0]["day_17"], "Present")
		self.assertEqual(grid[0]["day_22"], "Absent")
		self.assertEqual(grid[0]["day_25"], "Absent")

	def test_back_to_back_twelve_hour_shifts(self):
		self._shift("Edge 12 Night", "20:00:00", "08:00:00", present=11, half=6)
		self._shift("Edge 12 Day", "08:00:00", "20:00:00", present=11, half=6)
		self._assign("Edge 12 Night", "2026-06-18", "2026-06-18")
		self._assign("Edge 12 Day", "2026-06-19", "2026-06-19")
		self._punch("2026-06-18 20:00:00")
		self._punch("2026-06-19 07:55:00")
		self._punch("2026-06-19 08:05:00", "OUT")
		self._punch("2026-06-19 20:00:00", "OUT")

		rows = self._rows("2026-06-18", "2026-06-19")
		self._expect(rows["2026-06-18"], "Present", "2026-06-18 20:00:00", "2026-06-19 08:05:00", 725, 0)
		self._expect(rows["2026-06-19"], "Present", "2026-06-19 07:55:00", "2026-06-19 20:00:00", 725, 0)
		self._expect_variance(self._variances("2026-06-18", "2026-06-19"), "2026-06-18")
		self._expect_variance(self._variances("2026-06-18", "2026-06-19"), "2026-06-19")

	def test_off_day_does_not_absorb_overnight_tail(self):
		self._shift("Edge 12 Night", "20:00:00", "08:00:00", present=11, half=6)
		self._assign("Edge 12 Night", "2026-06-20", "2026-06-20")
		self._punch("2026-06-20 20:00:00")
		self._punch("2026-06-21 08:00:00", "OUT")
		self._punch("2026-06-21 13:00:00")
		self._punch("2026-06-21 17:00:00", "OUT")
		# 11:00 is still inside the night's 4-hour tail. 12:00:01 is the next calendar day.
		self._assign("Edge 12 Night", "2026-06-22", "2026-06-22")
		self._punch("2026-06-23 11:00:00")
		self._assign("Edge 12 Night", "2026-06-24", "2026-06-24")
		self._punch("2026-06-25 12:00:01")

		rows = self._rows("2026-06-20", "2026-06-25")
		self._expect(rows["2026-06-20"], "Present", "2026-06-20 20:00:00", "2026-06-21 08:00:00", 720, 0)
		self._expect(rows["2026-06-21"], "Present", "2026-06-21 13:00:00", "2026-06-21 17:00:00", 240, 0)
		self._expect(rows["2026-06-22"], "Late", "2026-06-23 11:00:00", None, None, 1)
		self._expect(rows["2026-06-23"], "Absent")
		self._expect(rows["2026-06-24"], "Absent")
		self._expect(rows["2026-06-25"], "Present", "2026-06-25 12:00:01", None, None, 0)

	def test_calendar_boundary_and_month_split(self):
		self._shift("Edge Cross", "22:00:00", "06:00:00", present=7, half=4)
		self._shift("Edge 12 Night", "20:00:00", "08:00:00", present=11, half=6)
		self._assign("Edge Cross", "2026-03-31", "2026-03-31")
		self._punch("2026-03-31 22:00:00")
		self._punch("2026-04-01 06:00:00", "OUT")
		self._assign("Edge 12 Night", "2026-01-31", "2026-01-31")
		self._punch("2026-01-31 20:00:00")
		self._punch("2026-02-01 08:00:00", "OUT")
		frappe.db.commit()

		march = employee_month_attendance(self.employee, "2026-03")
		self.assertEqual(march["days"]["2026-03-31"]["status"], "Present")
		self.assertEqual(march["days"]["2026-03-31"]["in_time"], "2026-03-31 22:00:00")
		self.assertEqual(march["days"]["2026-03-31"]["out_time"], "2026-04-01 06:00:00")
		self.assertEqual(march["days"]["2026-03-31"]["worked_minutes"], 480)
		april = employee_month_attendance(self.employee, "2026-04")
		self.assertEqual(april["days"]["2026-04-01"]["status"], "Absent")
		self.assertIsNone(april["days"]["2026-04-01"]["in_time"])
		self.assertIsNone(april["days"]["2026-04-01"]["out_time"])

		january = employee_month_attendance(self.employee, "2026-01")
		self.assertEqual(january["days"]["2026-01-31"]["status"], "Present")
		self.assertEqual(january["days"]["2026-01-31"]["out_time"], "2026-02-01 08:00:00")
		self.assertEqual(january["days"]["2026-01-31"]["worked_minutes"], 720)
		february = employee_month_attendance(self.employee, "2026-02")
		self.assertEqual(february["days"]["2026-02-01"]["status"], "Absent")
		self.assertIsNone(february["days"]["2026-02-01"]["out_time"])

		grid = monthly_attendance_grid_rows({"month": "2026-03", "employee": self.employee})
		self.assertEqual(grid[0]["day_31"], "Present")
		april_grid = monthly_attendance_grid_rows({"month": "2026-04", "employee": self.employee})
		self.assertEqual(april_grid[0]["day_1"], "Absent")

	def test_active_date_hands_off_to_the_next_shift(self):
		self._shift("Edge Day", "09:00:00", "18:00:00", present=8, half=4)
		self._assign("Edge Day", "2026-06-17", "2026-06-17")
		self.assertEqual(self._state_at("2026-06-17 07:00:00")["date"], "2026-06-17")

		self._clear()
		self._shift("Edge 12 Night", "20:00:00", "08:00:00", present=11, half=6)
		self._shift("Edge Day", "09:00:00", "18:00:00", present=8, half=4)
		self._assign("Edge 12 Night", "2026-06-16", "2026-06-16")
		self._assign("Edge Day", "2026-06-17", "2026-06-17")
		self._punch("2026-06-16 20:00:00")
		frappe.db.commit()

		during = self._state_at("2026-06-17 01:00:00")
		self.assertEqual(during["date"], "2026-06-16")
		self.assertFalse(during["today_complete"])
		self.assertEqual(get_datetime(during["first_in"]["time"]), get_datetime("2026-06-16 20:00:00"))
		self.assertIsNone(during["last_out"])

		self._punch("2026-06-17 08:00:00", "OUT")
		frappe.db.commit()

		still_night = self._state_at("2026-06-17 08:00:00")
		self.assertEqual(still_night["date"], "2026-06-16")
		self.assertTrue(still_night["today_complete"])
		self.assertEqual(still_night["worked_minutes"], 720)

		handed_off = self._state_at("2026-06-17 08:00:01")
		self.assertEqual(handed_off["date"], "2026-06-17")
		self.assertFalse(handed_off["today_complete"])
		self.assertIsNone(handed_off["first_in"])
		self.assertIsNone(handed_off["last_out"])
		self.assertEqual(handed_off["today_punches"], [])

		later = self._state_at("2026-06-17 10:00:00")
		self.assertEqual(later["date"], "2026-06-17")
		self.assertFalse(later["today_complete"])
		self.assertEqual(later["today_shift"]["name"], "Edge Day")

	def _state_at(self, when, requested="2026-06-17"):
		with patch("hrms_custom.api.attendance.now_datetime", return_value=get_datetime(when)):
			return attendance_api.today_punch_state(self.employee, day=requested)
