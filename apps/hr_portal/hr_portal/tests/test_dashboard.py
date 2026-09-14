import frappe
from frappe.tests import IntegrationTestCase

from hr_portal.services.dashboard_service import build_dashboard_snapshot


class TestDashboardSnapshot(IntegrationTestCase):
	def test_build_dashboard_snapshot_shape(self):
		frappe.set_user("Administrator")
		data = build_dashboard_snapshot()
		self.assertIn("today", data)
		self.assertIn("employees", data)
		self.assertIn("attendance", data)
		self.assertIn("leave", data)
		self.assertIn("recent", data)
		self.assertIn("active", data["employees"])
		self.assertIn("present", data["attendance"])
