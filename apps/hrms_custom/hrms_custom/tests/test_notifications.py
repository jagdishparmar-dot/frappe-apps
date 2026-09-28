from datetime import datetime
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate

from hrms_custom.api import leave, notifications
from hrms_custom.jobs.shift_reminders import send_shift_reminders
from hrms_custom.tests.utils import call, get_test_company, make_employee_user
from hrms_custom.utils.notify import CHANNEL_APPROVAL, CHANNEL_SHIFT_END, CHANNEL_SHIFT_START, notify_employee

EMPLOYEE_USER = "notify.employee@example.com"
OTHER_USER = "notify.other@example.com"
HR_USER = "notify.hr@example.com"


class TestNotifications(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = get_test_company()
		cls.employee = make_employee_user(EMPLOYEE_USER, cls.company, "Notify Emp", mobile="9000020000")
		cls.other = make_employee_user(OTHER_USER, cls.company, "Notify Other", mobile="9000020001")
		if not frappe.db.exists("User", HR_USER):
			frappe.get_doc(
				{"doctype": "User", "email": HR_USER, "first_name": "Notify HR", "send_welcome_email": 0}
			).insert(ignore_permissions=True).add_roles("HR Executive")
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		cls._clear()
		frappe.db.commit()
		super().tearDownClass()

	@classmethod
	def _clear(cls):
		for doctype in ("Employee Notification", "Employee Device", "Leave Application", "Leave Allocation"):
			filters = {"employee": ["in", [cls.employee, cls.other]]}
			if doctype == "Leave Allocation":
				filters = {"employee": cls.employee}
			for name in frappe.get_all(doctype, filters=filters, pluck="name"):
				frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
		for name in frappe.get_all("Shift Assignment", filters={"employee": cls.employee}, pluck="name"):
			frappe.delete_doc("Shift Assignment", name, force=True, ignore_permissions=True)

	def setUp(self):
		frappe.set_user("Administrator")
		self._clear()
		frappe.db.set_value(
			"Employee",
			self.employee,
			{"notify_shift_start": 1, "notify_shift_end": 1, "notify_approvals": 1},
		)
		frappe.db.set_single_value("HRMS Custom Settings", "shift_reminder_minutes", 15)
		frappe.db.commit()
		patcher = patch("frappe.sendmail")
		self.sendmail = patcher.start()
		self.addCleanup(patcher.stop)

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_notify_employee_creates_row_and_skips_when_preference_is_off(self):
		row = notify_employee(
			self.employee,
			CHANNEL_APPROVAL,
			"Leave approved",
			"Your casual leave was approved.",
			route="/leave",
			occurrence_key="leave-1",
		)
		self.assertTrue(row)
		self.assertEqual(frappe.db.count("Employee Notification", {"employee": self.employee}), 1)
		again = notify_employee(
			self.employee,
			CHANNEL_APPROVAL,
			"Leave approved",
			"Your casual leave was approved.",
			route="/leave",
			occurrence_key="leave-1",
		)
		self.assertEqual(again, row)
		self.assertEqual(frappe.db.count("Employee Notification", {"employee": self.employee}), 1)

		frappe.db.set_value("Employee", self.employee, "notify_approvals", 0)
		skipped = notify_employee(
			self.employee,
			CHANNEL_APPROVAL,
			"Leave rejected",
			"Your leave was rejected.",
			occurrence_key="leave-2",
		)
		self.assertIsNone(skipped)
		self.assertEqual(frappe.db.count("Employee Notification", {"employee": self.employee}), 1)

	def test_preferences_api_reads_and_updates_immediately(self):
		frappe.set_user(EMPLOYEE_USER)
		status, body = call(notifications.get_notification_preferences)
		self.assertEqual(status, 200, body)
		self.assertTrue(body["data"]["notify_shift_start"])
		self.assertTrue(body["data"]["notify_shift_end"])
		self.assertTrue(body["data"]["notify_approvals"])

		status, body = call(
			notifications.update_notification_preferences,
			notify_shift_start=0,
			notify_shift_end=1,
			notify_approvals=0,
		)
		self.assertEqual(status, 200, body)
		self.assertFalse(body["data"]["notify_shift_start"])
		self.assertTrue(body["data"]["notify_shift_end"])
		self.assertFalse(body["data"]["notify_approvals"])
		self.assertEqual(frappe.db.get_value("Employee", self.employee, "notify_shift_start"), 0)

	def test_device_register_list_and_unregister(self):
		frappe.set_user(EMPLOYEE_USER)
		status, body = call(
			notifications.register_device, fcm_token="fcm-token-aaa", platform="android", device_id="phone-1"
		)
		self.assertEqual(status, 200, body)
		self.assertEqual(frappe.db.count("Employee Device", {"employee": self.employee}), 1)
		frappe.db.commit()

		status, body = call(
			notifications.register_device, fcm_token="fcm-token-aaa", platform="android", device_id="phone-1"
		)
		self.assertEqual(status, 200, body)
		self.assertEqual(frappe.db.count("Employee Device", {"employee": self.employee}), 1)

		frappe.set_user(OTHER_USER)
		self.assertEqual(call(notifications.unregister_device, fcm_token="fcm-token-aaa")[0], 403)

		frappe.set_user(EMPLOYEE_USER)
		self.assertEqual(call(notifications.unregister_device, fcm_token="fcm-token-aaa")[0], 200)
		self.assertEqual(frappe.db.count("Employee Device", {"employee": self.employee}), 0)

	def test_list_and_mark_read(self):
		notify_employee(self.employee, CHANNEL_SHIFT_START, "Shift starts soon", "09:00", occurrence_key="2026-09-28")
		notify_employee(self.other, CHANNEL_SHIFT_START, "Other shift", "10:00", occurrence_key="2026-09-28")
		frappe.set_user(EMPLOYEE_USER)
		status, body = call(notifications.list_my_notifications)
		self.assertEqual(status, 200, body)
		self.assertEqual(body["data"]["unread_count"], 1)
		self.assertEqual(len(body["data"]["notifications"]), 1)
		name = body["data"]["notifications"][0]["name"]
		self.assertEqual(call(notifications.mark_notifications_read, names=[name])[0], 200)
		self.assertEqual(call(notifications.list_my_notifications)[1]["data"]["unread_count"], 0)

	def test_leave_review_writes_an_approval_notification(self):
		if not frappe.db.exists("Leave Type", "Notify Casual"):
			frappe.get_doc(
				{"doctype": "Leave Type", "leave_type_name": "Notify Casual", "company": self.company}
			).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Leave Allocation",
				"employee": self.employee,
				"leave_type": "Notify Casual",
				"from_date": "2026-01-01",
				"to_date": "2026-12-31",
				"allocated": 8,
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()
		frappe.set_user(EMPLOYEE_USER)
		name = call(
			leave.apply_leave,
			leave_type="Notify Casual",
			from_date="2026-10-05",
			to_date="2026-10-05",
			reason="Personal",
		)[1]["data"]["name"]
		frappe.db.commit()
		frappe.set_user(HR_USER)
		status, body = call(leave.review_leave, application=name, status="Approved")
		self.assertEqual(status, 200, body)
		row = frappe.db.get_value(
			"Employee Notification",
			{"employee": self.employee, "channel": CHANNEL_APPROVAL},
			["title", "route"],
			as_dict=True,
		)
		self.assertTrue(row)
		self.assertIn("approved", row.title.lower())
		self.assertEqual(row.route, "/leave")

	def test_shift_reminder_sends_once_inside_the_lead_window(self):
		shift = "Notify Day"
		if frappe.db.exists("Shift Type", shift):
			doc = frappe.get_doc("Shift Type", shift)
			doc.update({"company": self.company, "is_active": 1, "start_time": "09:00:00", "end_time": "18:00:00"})
			doc.save(ignore_permissions=True)
		else:
			frappe.get_doc(
				{
					"doctype": "Shift Type",
					"shift_name": shift,
					"company": self.company,
					"start_time": "09:00:00",
					"end_time": "18:00:00",
					"is_active": 1,
				}
			).insert(ignore_permissions=True)
		today = getdate()
		frappe.get_doc(
			{
				"doctype": "Shift Assignment",
				"employee": self.employee,
				"shift_type": shift,
				"start_date": today,
				"end_date": today,
				"status": "Active",
			}
		).insert(ignore_permissions=True)
		now = datetime(today.year, today.month, today.day, 8, 50, 0)
		send_shift_reminders(now=now)
		self.assertEqual(
			frappe.db.count("Employee Notification", {"employee": self.employee, "channel": CHANNEL_SHIFT_START}),
			1,
		)
		send_shift_reminders(now=now)
		self.assertEqual(
			frappe.db.count("Employee Notification", {"employee": self.employee, "channel": CHANNEL_SHIFT_START}),
			1,
		)

		frappe.db.set_value("Employee", self.employee, "notify_shift_end", 0)
		end_now = datetime(today.year, today.month, today.day, 17, 50, 0)
		send_shift_reminders(now=end_now)
		self.assertEqual(
			frappe.db.count("Employee Notification", {"employee": self.employee, "channel": CHANNEL_SHIFT_END}),
			0,
		)

		frappe.db.set_value("Employee", self.employee, "notify_shift_end", 1)
		send_shift_reminders(now=end_now)
		self.assertEqual(
			frappe.db.count("Employee Notification", {"employee": self.employee, "channel": CHANNEL_SHIFT_END}),
			1,
		)
		send_shift_reminders(now=end_now)
		self.assertEqual(
			frappe.db.count("Employee Notification", {"employee": self.employee, "channel": CHANNEL_SHIFT_END}),
			1,
		)
