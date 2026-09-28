import json

import frappe
from frappe.tests import IntegrationTestCase

from hrms_custom.utils.desk_home import today_absent, today_late, today_on_leave, today_present


PENDING_CARDS = (
	"Today Present",
	"Today Late",
	"Today Absent",
	"Today On Leave",
	"Open Leave Applications",
	"Open Regularizations",
	"Pending Documents",
	"Pending Profile Updates",
	"Onboarding to Verify",
)


class TestDeskHome(IntegrationTestCase):
	def test_workspace_has_pending_widgets(self):
		workspace = frappe.get_doc("Workspace", "HRMS")
		card_names = {row.number_card_name for row in workspace.number_cards}
		for name in PENDING_CARDS:
			self.assertIn(name, card_names)
			self.assertEqual(frappe.db.exists("Number Card", name), name)
		list_labels = {row.label for row in workspace.quick_lists}
		for label in ("Open Leave Applications", "Open Regularizations", "Pending Documents", "Pending Profile Updates"):
			self.assertIn(label, list_labels)
		content = json.loads(workspace.content)
		types = {block["type"] for block in content}
		self.assertIn("number_card", types)
		self.assertIn("quick_list", types)
		headers = [block["data"]["text"] for block in content if block["type"] == "header"]
		self.assertTrue(any("Pending actions" in text for text in headers))
		self.assertTrue(any("Today" in text for text in headers))

	def test_today_cards_return_counts_for_hr(self):
		frappe.set_user("Administrator")
		for method in (today_present, today_late, today_absent, today_on_leave):
			result = method()
			self.assertIn("value", result)
			self.assertGreaterEqual(result["value"], 0)
