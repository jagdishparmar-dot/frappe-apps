import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import get_datetime, getdate, now_datetime

from hrms_custom.api.attendance import get_punch_status, punch
from hrms_custom.tests.utils import call, get_test_company, make_employee_user

USER = "punch.tester@example.com"
UNMAPPED_USER = "punch.unmapped@example.com"
LOCATION = "_Test HRC HQ"
HQ_LAT, HQ_LNG = 23.0225, 72.5714
INSIDE = {"latitude": 23.0230, "longitude": 72.5714}  # ~55 m from center
OUTSIDE = {"latitude": 23.0300, "longitude": 72.5714}  # ~830 m from center


class TestPunchAPI(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = get_test_company()
		cls.employee = make_employee_user(USER, cls.company, "Punch")
		cls.unmapped_employee = make_employee_user(UNMAPPED_USER, cls.company, "Unmapped")

		if not frappe.db.exists("Geofence Location", LOCATION):
			frappe.get_doc(
				{
					"doctype": "Geofence Location",
					"location_name": LOCATION,
					"company": cls.company,
					"latitude": HQ_LAT,
					"longitude": HQ_LNG,
					"radius_meters": 200,
				}
			).insert()
		if not frappe.db.exists("Employee Geofence Map", {"employee": cls.employee}):
			frappe.get_doc(
				{"doctype": "Employee Geofence Map", "employee": cls.employee, "geofence_location": LOCATION}
			).insert()
		# Endpoint error paths roll back the transaction, so fixtures must be committed.
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		for employee in (cls.employee, cls.unmapped_employee):
			frappe.db.delete("Employee Checkin", {"employee": employee})
			for name in frappe.get_all("Shift Assignment", filters={"employee": employee}, pluck="name"):
				frappe.delete_doc("Shift Assignment", name, force=True, ignore_permissions=True)
		frappe.db.delete("Employee Geofence Map", {"employee": cls.employee})
		frappe.db.set_value("Company", cls.company, "geofence_policy", None)
		frappe.db.set_value("Employee", cls.employee, "geofence_policy", None)
		frappe.db.commit()
		super().tearDownClass()

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Employee Checkin", {"employee": self.employee})
		self.set_policy(None)
		self.set_employee_policy(None)
		frappe.db.commit()
		frappe.set_user(USER)

	def tearDown(self):
		frappe.set_user("Administrator")

	def set_policy(self, policy):
		frappe.db.set_value("Company", self.company, "geofence_policy", policy)

	def set_employee_policy(self, policy):
		frappe.db.set_value("Employee", self.employee, "geofence_policy", policy)

	def checkins(self):
		return frappe.get_all(
			"Employee Checkin",
			filters={"employee": self.employee},
			fields=["name", "log_type", "time", "is_within_geofence", "is_auto_closed", "client_captured_at"],
			order_by="time asc, creation asc",
		)

	def test_punch_in_inside_geofence(self):
		status, body = call(punch, punch_type="IN", device_id="test-device", **INSIDE)

		self.assertEqual(status, 200, body)
		self.assertTrue(body["success"])
		self.assertEqual(body["data"]["current_status"], "IN")
		self.assertEqual(body["data"]["geofence_location"], LOCATION)
		self.assertTrue(body["data"]["is_within_geofence"])
		[row] = self.checkins()
		self.assertEqual(row.log_type, "IN")
		self.assertEqual(row.is_within_geofence, 1)

	def test_outside_geofence_rejected_by_default(self):
		status, body = call(punch, punch_type="IN", **OUTSIDE)

		self.assertEqual(status, 400)
		self.assertFalse(body["success"])
		self.assertEqual(body["message"], "Outside allowed location")
		self.assertEqual(body["data"]["nearest_location"], LOCATION)
		self.assertEqual(self.checkins(), [])

	def test_outside_geofence_flagged_when_company_policy_is_flag(self):
		frappe.set_user("Administrator")
		self.set_policy("Flag")
		frappe.db.commit()
		frappe.set_user(USER)

		status, body = call(punch, punch_type="IN", **OUTSIDE)

		self.assertEqual(status, 200, body)
		self.assertFalse(body["data"]["is_within_geofence"])
		self.assertIn("flagged", body["message"])
		[row] = self.checkins()
		self.assertEqual(row.is_within_geofence, 0)

	def test_employee_flag_overrides_company_reject(self):
		frappe.set_user("Administrator")
		self.set_policy("Reject")
		self.set_employee_policy("Flag")
		frappe.db.commit()
		frappe.set_user(USER)

		status, body = call(punch, punch_type="IN", **OUTSIDE)

		self.assertEqual(status, 200, body)
		self.assertFalse(body["data"]["is_within_geofence"])
		[row] = self.checkins()
		self.assertEqual(row.is_within_geofence, 0)

	def test_employee_reject_overrides_company_flag(self):
		frappe.set_user("Administrator")
		self.set_policy("Flag")
		self.set_employee_policy("Reject")
		frappe.db.commit()
		frappe.set_user(USER)

		status, body = call(punch, punch_type="IN", **OUTSIDE)

		self.assertEqual(status, 400, body)
		self.assertEqual(body["message"], "Outside allowed location")
		self.assertEqual(self.checkins(), [])

	def test_blank_employee_policy_inherits_company(self):
		frappe.set_user("Administrator")
		self.set_policy("Flag")
		self.set_employee_policy(None)
		frappe.db.commit()
		frappe.set_user(USER)

		status, body = call(punch, punch_type="IN", **OUTSIDE)
		self.assertEqual(status, 200, body)
		self.assertFalse(body["data"]["is_within_geofence"])

	def test_second_in_auto_closes_open_in(self):
		call(punch, punch_type="IN", **INSIDE)
		first_in = self.checkins()[0]
		frappe.db.set_value("Employee Checkin", first_in.name, "time", get_datetime("2026-01-05 09:00:00"))
		frappe.db.commit()

		status, body = call(punch, punch_type="IN", **INSIDE)

		self.assertEqual(status, 200, body)
		self.assertTrue(body["data"]["auto_closed_checkin"])
		rows = self.checkins()
		self.assertEqual([r.log_type for r in rows], ["IN", "OUT", "IN"])
		auto_out = rows[1]
		self.assertEqual(auto_out.name, body["data"]["auto_closed_checkin"])
		self.assertEqual(auto_out.is_auto_closed, 1)
		# The auto OUT credits zero time.
		self.assertEqual(auto_out.time, get_datetime("2026-01-05 09:00:00"))

	def test_out_without_in_is_rejected(self):
		status, body = call(punch, punch_type="OUT", **INSIDE)

		self.assertEqual(status, 400)
		self.assertEqual(body["message"], "You are not punched in")

	def test_in_then_out(self):
		call(punch, punch_type="IN", **INSIDE)
		status, body = call(punch, punch_type="OUT", **INSIDE)

		self.assertEqual(status, 200, body)
		self.assertEqual(body["data"]["current_status"], "OUT")
		self.assertEqual([r.log_type for r in self.checkins()], ["IN", "OUT"])

	def test_server_time_is_used_not_client_time(self):
		before = now_datetime().replace(microsecond=0)
		status, body = call(punch, punch_type="IN", captured_at="2020-01-01 08:00:00", **INSIDE)

		self.assertEqual(status, 200, body)
		[row] = self.checkins()
		self.assertGreaterEqual(get_datetime(row.time), before)
		self.assertEqual(get_datetime(row.client_captured_at), get_datetime("2020-01-01 08:00:00"))

	def test_validation_errors(self):
		cases = [
			({"punch_type": "IN"}, "Location is required"),
			({"punch_type": "IN", "latitude": "abc", "longitude": "72"}, "Invalid location"),
			({"punch_type": "IN", "latitude": 95, "longitude": 72}, "Invalid location"),
			({"punch_type": "BREAK", **INSIDE}, "punch_type must be IN or OUT"),
		]
		for kwargs, expected in cases:
			with self.subTest(kwargs=kwargs):
				status, body = call(punch, **kwargs)
				self.assertEqual(status, 400)
				self.assertIn(expected, body["message"])

	def test_employee_without_geofence(self):
		frappe.set_user(UNMAPPED_USER)
		status, body = call(punch, punch_type="IN", **INSIDE)

		self.assertEqual(status, 400)
		self.assertIn("No work location", body["message"])

	def test_guest_is_rejected(self):
		frappe.set_user("Guest")
		status, body = call(punch, punch_type="IN", **INSIDE)

		self.assertEqual(status, 401)
		self.assertFalse(body["success"])

	def test_punch_status(self):
		status, body = call(get_punch_status)
		self.assertEqual(status, 200, body)
		self.assertEqual(body["data"]["current_status"], "OUT")
		self.assertEqual(body["data"]["geofences"][0]["name"], LOCATION)
		self.assertEqual(body["data"]["geofence_policy"], "Reject")
		self.assertFalse(body["data"]["today_complete"])
		self.assertEqual(body["data"]["today_punches"], [])

		call(punch, punch_type="IN", **INSIDE)
		_, body = call(get_punch_status)
		self.assertEqual(body["data"]["current_status"], "IN")
		self.assertEqual(body["data"]["last_punch"]["punch_type"], "IN")
		self.assertEqual(body["data"]["today_punches"][0]["punch_type"], "IN")

	def test_completed_day_rejects_another_in_or_out(self):
		call(punch, punch_type="IN", **INSIDE)
		call(punch, punch_type="OUT", **INSIDE)
		# Error paths roll back the open transaction; persist the completed pair first.
		frappe.db.commit()

		for punch_type in ("IN", "OUT"):
			status, body = call(punch, punch_type=punch_type, **INSIDE)
			self.assertEqual(status, 400, body)
			self.assertIn("already punched", body["message"])
		self.assertEqual([row.log_type for row in self.checkins()], ["IN", "OUT"])

	def test_punch_status_includes_today_shift(self):
		frappe.set_user("Administrator")
		today = getdate()
		shift_name = "_Test Punch Day"
		if not frappe.db.exists("Shift Type", shift_name):
			frappe.get_doc(
				{
					"doctype": "Shift Type",
					"shift_name": shift_name,
					"company": self.company,
					"start_time": "09:00:00",
					"end_time": "18:00:00",
					"grace_minutes": 15,
				}
			).insert(ignore_permissions=True)
		for name in frappe.get_all("Shift Assignment", filters={"employee": self.employee}, pluck="name"):
			frappe.delete_doc("Shift Assignment", name, force=True, ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Shift Assignment",
				"employee": self.employee,
				"shift_type": shift_name,
				"start_date": today,
				"end_date": today,
				"status": "Active",
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()
		frappe.set_user(USER)

		status, body = call(get_punch_status)
		self.assertEqual(status, 200, body)
		self.assertEqual(body["data"]["today_shift"]["name"], shift_name)
		self.assertEqual(body["data"]["today_shift"]["start_time"], "09:00:00")

		call(punch, punch_type="IN", **INSIDE)
		call(punch, punch_type="OUT", **INSIDE)
		_, body = call(get_punch_status)
		self.assertTrue(body["data"]["today_complete"])
		self.assertEqual([row["punch_type"] for row in body["data"]["today_punches"]], ["IN", "OUT"])
		self.assertIsNotNone(body["data"]["worked_hours"])
