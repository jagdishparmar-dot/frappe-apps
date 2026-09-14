import frappe
from frappe.utils.password import update_password

from hr_portal.constants import HR_ADMIN, HR_EMPLOYEE

try:
	from frappe.tests import IntegrationTestCase
except ImportError:
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase


ADMIN_EMAIL = "f1.admin@example.com"
EMP_EMAIL = "f1.emp@example.com"
TEST_PASSWORD = "TestPass!23456"


def _login_as(email: str, role: str, first_name: str) -> None:
	if not frappe.db.exists("User", email):
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": first_name,
				"send_welcome_email": 0,
				"enabled": 1,
				"user_type": "Website User",
			}
		)
		user.insert(ignore_permissions=True)
		update_password(email, TEST_PASSWORD)
	user = frappe.get_doc("User", email)
	user.add_roles(role)


class TestF1HireAndProfile(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		from hr_portal.setup.install import after_migrate

		after_migrate()
		_login_as(ADMIN_EMAIL, HR_ADMIN, "F1Admin")
		_login_as(EMP_EMAIL, HR_EMPLOYEE, "F1Emp")

		if not frappe.db.exists("HR Site", {"site_name": "F1 HQ"}):
			cls.site = frappe.get_doc(
				{
					"doctype": "HR Site",
					"site_name": "F1 HQ",
					"latitude": 18.52,
					"longitude": 73.85,
					"radius_meters": 250,
					"status": "Active",
				}
			).insert(ignore_permissions=True).name
		else:
			cls.site = frappe.db.get_value("HR Site", {"site_name": "F1 HQ"}, "name")

		if not frappe.db.exists("HR Shift", {"code": "F1GEN"}):
			cls.shift = frappe.get_doc(
				{
					"doctype": "HR Shift",
					"shift_name": "F1 General",
					"code": "F1GEN",
					"start_time": "09:00:00",
					"end_time": "18:00:00",
					"status": "Active",
				}
			).insert(ignore_permissions=True).name
		else:
			cls.shift = frappe.db.get_value("HR Shift", {"code": "F1GEN"}, "name")

		if not frappe.db.exists("HR Employee", {"user": ADMIN_EMAIL}):
			frappe.get_doc(
				{
					"doctype": "HR Employee",
					"employee_name": "F1 Admin",
					"user": ADMIN_EMAIL,
					"email": ADMIN_EMAIL,
					"phone": "9000000001",
					"portal_role": HR_ADMIN,
					"status": "Active",
					"must_change_password": 0,
					"attendance_policy": "geofenced",
					"primary_site": cls.site,
					"default_shift": cls.shift,
				}
			).insert(ignore_permissions=True)

		frappe.db.commit()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_admin_can_hire(self):
		from hr_portal.api.employees import create_employee

		frappe.set_user(ADMIN_EMAIL)
		result = create_employee(
			employee_name="Hired Person",
			email="hired.f1@example.com",
			password="HirePass!234",
			phone="9888877776",
			portal_role=HR_EMPLOYEE,
			attendance_policy="geofenced",
			primary_site=self.site,
			default_shift=self.shift,
			department="Operations",
		)
		self.assertTrue(result["ok"])
		self.assertTrue(frappe.db.exists("User", "hired.f1@example.com"))
		emp = frappe.get_doc("HR Employee", result["name"])
		self.assertEqual(emp.must_change_password, 1)
		self.assertEqual(emp.primary_site, self.site)

	def test_employee_cannot_hire(self):
		from hr_portal.api.employees import create_employee

		frappe.set_user(EMP_EMAIL)
		with self.assertRaises(frappe.PermissionError):
			create_employee(
				employee_name="Nope",
				email="nope.f1@example.com",
				password="HirePass!234",
				phone="9888877775",
				primary_site=self.site,
				default_shift=self.shift,
			)

	def test_geofenced_hire_requires_site(self):
		from hr_portal.api.employees import create_employee

		frappe.set_user(ADMIN_EMAIL)
		with self.assertRaises(frappe.ValidationError):
			create_employee(
				employee_name="No Site",
				email="nosite.f1@example.com",
				password="HirePass!234",
				phone="9888877774",
				attendance_policy="geofenced",
				default_shift=self.shift,
			)

	def test_mobile_login_issues_token(self):
		from hr_portal.api.auth import login

		frappe.set_user("Guest")
		result = login(email=ADMIN_EMAIL, password=TEST_PASSWORD)
		self.assertTrue(result["ok"])
		self.assertTrue(result["api_key"])
		self.assertTrue(result["api_secret"])
		self.assertTrue(result["memberships"])

	def test_employee_cannot_read_other_documents(self):
		from hr_portal.api.documents import list_employee_documents

		admin_emp = frappe.db.get_value("HR Employee", {"user": ADMIN_EMAIL}, "name")
		frappe.set_user(EMP_EMAIL)
		with self.assertRaises(frappe.PermissionError):
			list_employee_documents(admin_emp)
