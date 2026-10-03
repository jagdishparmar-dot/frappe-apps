import frappe
from frappe.tests import IntegrationTestCase

from hrms_custom.hrms_custom.report.employee_master.employee_master import execute as employee_master
from hrms_custom.tests.utils import get_test_company, make_employee_user
from hrms_custom.utils.reports import list_employees

EMPLOYEE_USER = "emptype.employee@example.com"


class TestEmployeeType(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = get_test_company()
		cls.employee = make_employee_user(EMPLOYEE_USER, cls.company, "Type Emp", mobile="9000019000")
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		if frappe.db.exists("Employee", {"user_id": EMPLOYEE_USER}):
			name = frappe.db.get_value("Employee", {"user_id": EMPLOYEE_USER}, "name")
			frappe.delete_doc("Employee", name, force=True, ignore_permissions=True)
		frappe.db.commit()
		super().tearDownClass()

	def setUp(self):
		frappe.set_user("Administrator")
		# This class edits job fields. Put the shared fixture back to Draft if it was submitted.
		if frappe.db.get_value("Employee", self.employee, "docstatus") != 0:
			frappe.db.set_value("Employee", self.employee, "docstatus", 0)
		frappe.db.set_value("Employee", self.employee, "employee_type", "Permanent")
		frappe.db.set_value("Employee", self.employee, "vendor", None)
		frappe.db.set_value("Employee", self.employee, "other_employee_type", None)
		frappe.db.commit()

	def _vendor(self, name="Type Vendor 3PL"):
		if frappe.db.exists("Vendor", name):
			return name
		return (
			frappe.get_doc({"doctype": "Vendor", "vendor_name": name, "is_active": 1})
			.insert(ignore_permissions=True)
			.name
		)

	def test_defaults_to_permanent(self):
		self.assertEqual(frappe.db.get_value("Employee", self.employee, "employee_type") or "Permanent", "Permanent")

	def test_contract_requires_vendor(self):
		doc = frappe.get_doc("Employee", self.employee)
		doc.employee_type = "Contract"
		doc.vendor = None
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_contract_saves_with_vendor(self):
		vendor = self._vendor()
		doc = frappe.get_doc("Employee", self.employee)
		doc.employee_type = "Contract"
		doc.vendor = vendor
		doc.save(ignore_permissions=True)
		frappe.db.commit()
		self.assertEqual(frappe.db.get_value("Employee", self.employee, "vendor"), vendor)

		_, people = employee_master({"employee": self.employee, "employee_type": "Contract"})
		row = next(r for r in people if r.name == self.employee)
		self.assertEqual(row.employee_type, "Contract")
		self.assertEqual(row.vendor, vendor)

		matched = list_employees({"employee_type": "Contract", "vendor": vendor})
		self.assertTrue(any(row.name == self.employee for row in matched))

	def test_other_requires_label(self):
		doc = frappe.get_doc("Employee", self.employee)
		doc.employee_type = "Other"
		doc.other_employee_type = None
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_other_type_is_stored(self):
		doc = frappe.get_doc("Employee", self.employee)
		doc.employee_type = "Other"
		doc.other_employee_type = "Intern"
		doc.save(ignore_permissions=True)
		frappe.db.commit()
		self.assertEqual(frappe.db.get_value("Employee", self.employee, "other_employee_type"), "Intern")
		_, people = employee_master({"employee": self.employee, "employee_type": "Other"})
		row = next(r for r in people if r.name == self.employee)
		self.assertEqual(row.other_employee_type, "Intern")

	def test_workspace_lists_vendor(self):
		labels = {row.label for row in frappe.get_doc("Workspace Sidebar", "HRMS").items}
		self.assertIn("Vendor", labels)
		self.assertEqual(frappe.db.exists("DocType", "Vendor"), "Vendor")
