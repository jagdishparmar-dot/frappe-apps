import frappe
from frappe.tests import IntegrationTestCase

from hrms_custom.api import shift
from hrms_custom.tests.utils import TEST_COMPANY, call, get_test_company, make_employee_user

EMPLOYEE_USER = "roster.employee@example.com"
OTHER_USER = "roster.other@example.com"
HR_USER = "roster.hr@example.com"
DEPT_NAME = "Roster Planning"


class TestRosterApi(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = get_test_company()
		if not frappe.db.exists("Department", {"department_name": DEPT_NAME, "company": cls.company}):
			frappe.get_doc(
				{"doctype": "Department", "department_name": DEPT_NAME, "company": cls.company}
			).insert(ignore_permissions=True)
		cls.department = frappe.db.get_value(
			"Department", {"department_name": DEPT_NAME, "company": cls.company}, "name"
		)
		cls.employee = make_employee_user(EMPLOYEE_USER, cls.company, "Roster Emp", mobile="9000013000")
		cls.other = make_employee_user(OTHER_USER, cls.company, "Roster Other", mobile="9000013001")
		frappe.db.set_value("Employee", cls.employee, "department", cls.department)
		if not frappe.db.exists("User", HR_USER):
			frappe.get_doc(
				{"doctype": "User", "email": HR_USER, "first_name": "Roster HR", "send_welcome_email": 0}
			).insert(ignore_permissions=True).add_roles("HR Executive")
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		cls._clear_rosters()
		frappe.db.commit()
		super().tearDownClass()

	@classmethod
	def _clear_rosters(cls):
		for employee in (cls.employee, cls.other):
			for name in frappe.get_all("Shift Roster", filters={"employee": employee}, pluck="name"):
				frappe.delete_doc("Shift Roster", name, force=True, ignore_permissions=True)
			for name in frappe.get_all("Shift Assignment", filters={"employee": employee}, pluck="name"):
				frappe.delete_doc("Shift Assignment", name, force=True, ignore_permissions=True)

	def setUp(self):
		frappe.set_user("Administrator")
		self._clear_rosters()
		frappe.db.commit()

	def tearDown(self):
		frappe.set_user("Administrator")

	def make_shift(self, name, start="09:00:00", end="18:00:00", **kwargs):
		if frappe.db.exists("Shift Type", name):
			return name
		doc = frappe.get_doc(
			{
				"doctype": "Shift Type",
				"shift_name": name,
				"start_time": start,
				"end_time": end,
				"company": self.company,
				**kwargs,
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()
		return doc.name

	def assign(self, employee, shift_type, start, end=None):
		doc = frappe.get_doc(
			{
				"doctype": "Shift Assignment",
				"employee": employee,
				"shift_type": shift_type,
				"start_date": start,
				"end_date": end,
				"status": "Active",
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()
		return doc.name

	def test_employee_cannot_read_or_write_roster(self):
		frappe.set_user(EMPLOYEE_USER)
		self.assertEqual(call(shift.get_roster, month="2026-10")[0], 403)
		self.assertEqual(
			call(
				shift.bulk_assign_roster,
				entries=[{"employee": self.employee, "date": "2026-10-05", "shift_type": "Morning"}],
			)[0],
			403,
		)

	def test_hr_grid_filters_department_and_shows_assignment(self):
		morning = self.make_shift("Roster Morning", location=None, color="#112233")
		self.assign(self.employee, morning, "2026-10-01", "2026-10-31")

		frappe.set_user(HR_USER)
		status, body = call(shift.get_roster, month="2026-10", department=self.department, company=self.company)
		self.assertEqual(status, 200, body)
		names = [row["name"] for row in body["data"]["employees"]]
		self.assertIn(self.employee, names)
		self.assertNotIn(self.other, names)
		cell = body["data"]["cells"][self.employee]["2026-10-05"]
		self.assertEqual(cell["shift_type"], morning)
		self.assertEqual(cell["source"], "assignment")
		self.assertTrue(any(s["name"] == morning for s in body["data"]["shift_types"]))
		self.assertEqual(len(body["data"]["days"]), 31)

	def test_bulk_assign_overrides_assignment_on_calendar(self):
		morning = self.make_shift("Roster Default")
		night = self.make_shift("Roster Night", start="22:00:00", end="06:00:00")
		self.assign(self.employee, morning, "2026-10-01", "2026-10-31")

		frappe.set_user(HR_USER)
		status, body = call(
			shift.bulk_assign_roster,
			entries=[
				{"employee": self.employee, "date": "2026-10-05", "shift_type": night},
				{"employee": self.employee, "date": "2026-10-06", "shift_type": night},
			],
		)
		self.assertEqual(status, 200, body)
		self.assertEqual(body["data"]["saved"], 2)

		frappe.set_user(EMPLOYEE_USER)
		days = call(shift.my_shift_calendar, month="2026-10")[1]["data"]["days"]
		self.assertEqual(days["2026-10-05"]["shift"]["name"], night)
		self.assertEqual(days["2026-10-05"]["shift"]["source"], "roster")
		self.assertTrue(days["2026-10-05"]["shift"]["is_overnight"])
		self.assertEqual(days["2026-10-01"]["shift"]["name"], morning)
		self.assertEqual(days["2026-10-01"]["shift"]["source"], "assignment")

	def test_clearing_a_cell_restores_assignment(self):
		morning = self.make_shift("Roster Clear Day")
		night = self.make_shift("Roster Clear Night", start="22:00:00", end="06:00:00")
		self.assign(self.employee, morning, "2026-10-01", "2026-10-31")

		frappe.set_user(HR_USER)
		call(
			shift.bulk_assign_roster,
			entries=[{"employee": self.employee, "date": "2026-10-08", "shift_type": night}],
		)
		status, body = call(
			shift.bulk_assign_roster,
			entries=[{"employee": self.employee, "date": "2026-10-08", "shift_type": ""}],
		)
		self.assertEqual(status, 200, body)
		self.assertEqual(body["data"]["cleared"], 1)
		self.assertFalse(frappe.db.exists("Shift Roster", {"employee": self.employee, "date": "2026-10-08"}))

		frappe.set_user(EMPLOYEE_USER)
		days = call(shift.my_shift_calendar, month="2026-10")[1]["data"]["days"]
		self.assertEqual(days["2026-10-08"]["shift"]["name"], morning)
		self.assertEqual(days["2026-10-08"]["shift"]["source"], "assignment")

	def test_duplicate_employee_date_is_rejected(self):
		shift_name = self.make_shift("Roster Unique")
		frappe.get_doc(
			{
				"doctype": "Shift Roster",
				"employee": self.employee,
				"date": "2026-10-12",
				"shift_type": shift_name,
			}
		).insert(ignore_permissions=True)
		with self.assertRaises((frappe.ValidationError, frappe.DuplicateEntryError)):
			frappe.get_doc(
				{
					"doctype": "Shift Roster",
					"employee": self.employee,
					"date": "2026-10-12",
					"shift_type": shift_name,
				}
			).insert(ignore_permissions=True)

	def test_invalid_month_and_unknown_shift(self):
		frappe.set_user(HR_USER)
		self.assertEqual(call(shift.get_roster, month="2026-13")[0], 400)
		self.assertEqual(call(shift.bulk_assign_roster, entries=[])[0], 400)
		self.assertEqual(
			call(
				shift.bulk_assign_roster,
				entries=[{"employee": self.employee, "date": "2026-10-05", "shift_type": "No Such Shift"}],
			)[0],
			400,
		)

	def test_workspace_sidebar_lists_hrms_tasks(self):
		labels = {row.label for row in frappe.get_doc("Workspace Sidebar", "HRMS").items}
		for expected in (
			"Employees",
			"Employee",
			"Employee Document",
			"Attendance",
			"Employee Checkin",
			"Attendance Regularization",
			"Live Attendance",
			"Shifts",
			"Shift Roster Planner",
			"Shift Roster",
			"Shift Type",
			"Shift Assignment",
			"Holiday List",
			"Onboarding Checklist",
			"Profile Update Request",
			"Locations",
			"Geofence Location",
			"Setup",
			"Company",
			"Vendor",
			"Leave",
			"Leave Application",
			"Leave Type",
			"Leave Allocation",
			"Reports",
			"Attendance Summary",
			"Employee Date-wise Attendance",
			"Punch Log",
			"Leave Balance",
		):
			self.assertIn(expected, labels)
		self.assertEqual(frappe.db.exists("Page", "shift-roster-planner"), "shift-roster-planner")
		self.assertEqual(frappe.db.exists("Page", "live-attendance"), "live-attendance")

	def test_module_sidebar_is_empty_so_desk_uses_hrms_only(self):
		"""A named 'HRMS Custom' sidebar stops Frappe auto-building a second menu."""
		self.assertTrue(frappe.db.exists("Workspace Sidebar", "HRMS Custom"))
		links = [row.label for row in frappe.get_doc("Workspace Sidebar", "HRMS Custom").items if row.type == "Link"]
		self.assertEqual(links, [])
