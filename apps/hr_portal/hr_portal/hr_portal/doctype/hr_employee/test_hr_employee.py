import frappe
from frappe.utils.password import update_password

from hr_portal.constants import HR_ADMIN, HR_EMPLOYEE, HR_PAYROLL_ADMIN

try:
	from frappe.tests import IntegrationTestCase
except ImportError:
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase


ADMIN_EMAIL = "hr.admin@example.com"
PAYROLL_EMAIL = "hr.payroll@example.com"
EMP_A_EMAIL = "emp.a@example.com"
EMP_B_EMAIL = "emp.b@example.com"
TEST_PASSWORD = "TestPass!23456"


def _ensure_user(email: str, role: str, first_name: str) -> str:
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
	else:
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": first_name,
				"send_welcome_email": 0,
				"enabled": 1,
			}
		)
		user.insert(ignore_permissions=True)
		update_password(email, TEST_PASSWORD)
	user.add_roles(role)
	return email


def _ensure_site() -> str:
	existing = frappe.db.get_value("HR Site", {"site_name": "Test HQ"}, "name")
	if existing:
		return existing
	doc = frappe.get_doc(
		{
			"doctype": "HR Site",
			"site_name": "Test HQ",
			"latitude": 19.07,
			"longitude": 72.87,
			"radius_meters": 300,
			"status": "Active",
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _ensure_shift() -> str:
	existing = frappe.db.get_value("HR Shift", {"code": "TESTGEN"}, "name")
	if existing:
		return existing
	doc = frappe.get_doc(
		{
			"doctype": "HR Shift",
			"shift_name": "Test General",
			"code": "TESTGEN",
			"start_time": "09:00:00",
			"end_time": "18:00:00",
			"status": "Active",
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _ensure_employee(email: str, name: str, role: str, bank: str) -> str:
	site = _ensure_site()
	shift = _ensure_shift()
	existing = frappe.db.get_value("HR Employee", {"user": email}, "name")
	if existing:
		doc = frappe.get_doc("HR Employee", existing)
		doc.bank_account_number = bank
		doc.pan_number = "ABCDE1234F"
		doc.primary_site = site
		doc.default_shift = shift
		doc.attendance_policy = "geofenced"
		doc.save(ignore_permissions=True)
		return doc.name
	doc = frappe.get_doc(
		{
			"doctype": "HR Employee",
			"employee_name": name,
			"user": email,
			"email": email,
			"phone": "9999900001",
			"portal_role": role,
			"status": "Active",
			"must_change_password": 0,
			"attendance_policy": "geofenced",
			"primary_site": site,
			"default_shift": shift,
			"bank_account_number": bank,
			"pan_number": "ABCDE1234F",
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


class TestF0Permissions(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		from hr_portal.setup.install import after_migrate

		after_migrate()
		_ensure_user(ADMIN_EMAIL, HR_ADMIN, "Admin")
		_ensure_user(PAYROLL_EMAIL, HR_PAYROLL_ADMIN, "Payroll")
		_ensure_user(EMP_A_EMAIL, HR_EMPLOYEE, "Alice")
		_ensure_user(EMP_B_EMAIL, HR_EMPLOYEE, "Bob")
		cls.admin_emp = _ensure_employee(ADMIN_EMAIL, "Admin User", HR_ADMIN, "00001111")
		cls.payroll_emp = _ensure_employee(PAYROLL_EMAIL, "Payroll User", HR_PAYROLL_ADMIN, "00002222")
		cls.emp_a = _ensure_employee(EMP_A_EMAIL, "Alice A", HR_EMPLOYEE, "111122223333")
		cls.emp_b = _ensure_employee(EMP_B_EMAIL, "Bob B", HR_EMPLOYEE, "999988887777")
		frappe.db.commit()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_employee_list_is_own_record_only(self):
		frappe.set_user(EMP_A_EMAIL)
		names = frappe.get_list("HR Employee", pluck="name")
		self.assertEqual(set(names), {self.emp_a})

	def test_employee_cannot_get_other_employee(self):
		frappe.set_user(EMP_A_EMAIL)
		self.assertFalse(frappe.has_permission("HR Employee", "read", doc=self.emp_b, user=EMP_A_EMAIL))

	def test_employee_cannot_read_own_bank_permlevel(self):
		frappe.set_user(EMP_A_EMAIL)
		doc = frappe.get_doc("HR Employee", self.emp_a)
		doc.apply_fieldlevel_read_permissions()
		self.assertFalse(doc.get("bank_account_number"))
		self.assertFalse(doc.get("pan_number"))

	def test_hr_admin_can_list_all_and_read_bank(self):
		frappe.set_user(ADMIN_EMAIL)
		names = set(frappe.get_list("HR Employee", pluck="name"))
		self.assertTrue({self.emp_a, self.emp_b, self.admin_emp}.issubset(names))
		other = frappe.get_doc("HR Employee", self.emp_b)
		self.assertEqual(other.bank_account_number, "999988887777")

	def test_payroll_admin_can_read_bank_cannot_create(self):
		frappe.set_user(PAYROLL_EMAIL)
		doc = frappe.get_doc("HR Employee", self.emp_a)
		self.assertEqual(doc.bank_account_number, "111122223333")
		self.assertFalse(frappe.has_permission("HR Employee", "create", user=PAYROLL_EMAIL))

	def test_employee_cannot_create_employee(self):
		frappe.set_user(EMP_A_EMAIL)
		self.assertFalse(frappe.has_permission("HR Employee", "create", user=EMP_A_EMAIL))

	def test_guest_has_no_app_permission(self):
		from hr_portal.api.session import check_app_permission

		frappe.set_user("Guest")
		self.assertFalse(check_app_permission())

	def test_hr_admin_has_app_permission(self):
		from hr_portal.api.session import check_app_permission

		frappe.set_user(ADMIN_EMAIL)
		self.assertTrue(check_app_permission())
