import frappe
from frappe.utils.messages import clear_last_message


def try_sendmail(**kwargs) -> bool:
	"""Send an email, returning False instead of raising when the site has no outgoing Email Account.

	Emails here are notifications only; they must never block or roll back the action that caused them.
	"""
	try:
		frappe.sendmail(**kwargs)
		return True
	except frappe.OutgoingEmailError:
		clear_last_message()
		frappe.log_error(
			title="hrms_custom: email not sent",
			message=f"No outgoing Email Account; skipped '{kwargs.get('subject')}' to {kwargs.get('recipients')}",
		)
		return False
