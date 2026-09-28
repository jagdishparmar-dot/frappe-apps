"""Email and in-app / push notifications. Failures here must never roll back the business action."""

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import frappe
from frappe.utils import cint, now_datetime
from frappe.utils.messages import clear_last_message

CHANNEL_SHIFT_START = "shift_start"
CHANNEL_SHIFT_END = "shift_end"
CHANNEL_APPROVAL = "approval"

CHANNEL_PREFERENCE = {
	CHANNEL_SHIFT_START: "notify_shift_start",
	CHANNEL_SHIFT_END: "notify_shift_end",
	CHANNEL_APPROVAL: "notify_approvals",
}

FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"


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


def notify_employee(
	employee: str,
	channel: str,
	title: str,
	body: str = "",
	*,
	route: str | None = None,
	reference_doctype: str | None = None,
	reference_name: str | None = None,
	occurrence_key: str | None = None,
) -> str | None:
	"""Write an Employee Notification (and try FCM) when the employee has that channel enabled.

	Returns the notification name, or None when skipped (unknown employee, preference off).
	"""
	if channel not in CHANNEL_PREFERENCE:
		frappe.throw(f"Unknown notification channel: {channel}")
	pref_field = CHANNEL_PREFERENCE[channel]
	row = frappe.db.get_value("Employee", employee, ["name", pref_field], as_dict=True)
	if not row:
		return None
	pref = row.get(pref_field)
	if pref is not None and not cint(pref):
		return None

	filters = {"employee": employee, "channel": channel, "occurrence_key": occurrence_key}
	if occurrence_key:
		existing = frappe.db.get_value("Employee Notification", filters, "name")
		if existing:
			return existing

	doc = frappe.get_doc(
		{
			"doctype": "Employee Notification",
			"employee": employee,
			"channel": channel,
			"title": title,
			"body": body,
			"route": route,
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"occurrence_key": occurrence_key,
			"sent_at": now_datetime(),
			"read": 0,
		}
	)
	doc.insert(ignore_permissions=True)
	try:
		send_push_to_employee(employee, title, body, {"route": route or "", "channel": channel, "name": doc.name})
	except Exception:
		frappe.log_error(title="hrms_custom: push not sent", message=frappe.get_traceback())
	return doc.name


def preference_dict(employee) -> dict:
	return {
		"notify_shift_start": _pref_on(getattr(employee, "notify_shift_start", None)),
		"notify_shift_end": _pref_on(getattr(employee, "notify_shift_end", None)),
		"notify_approvals": _pref_on(getattr(employee, "notify_approvals", None)),
	}


def _pref_on(value) -> bool:
	return True if value is None else bool(cint(value))


def notification_dict(doc) -> dict:
	return {
		"name": doc.name,
		"channel": doc.channel,
		"title": doc.title,
		"body": doc.body,
		"route": doc.route,
		"reference_doctype": doc.reference_doctype,
		"reference_name": doc.reference_name,
		"read": bool(cint(doc.read)),
		"sent_at": str(doc.sent_at) if doc.sent_at else None,
		"creation": str(doc.creation) if doc.creation else None,
	}


def send_push_to_employee(employee: str, title: str, body: str, data: dict | None = None) -> int:
	"""Send FCM to every registered device. No-op until a Firebase service account is configured."""
	tokens = frappe.get_all("Employee Device", filters={"employee": employee}, pluck="fcm_token")
	if not tokens:
		return 0
	sent = 0
	stale = []
	for token in tokens:
		result = _send_fcm(token, title, body, data or {})
		if result == "ok":
			sent += 1
		elif result == "stale":
			stale.append(token)
	for token in stale:
		for name in frappe.get_all("Employee Device", filters={"fcm_token": token}, pluck="name"):
			frappe.delete_doc("Employee Device", name, force=True, ignore_permissions=True)
	return sent


def _firebase_service_account() -> dict | None:
	raw = frappe.conf.get("firebase_service_account")
	if isinstance(raw, dict) and raw.get("client_email"):
		return raw
	if isinstance(raw, str) and raw.strip().startswith("{"):
		parsed = json.loads(raw)
		return parsed if parsed.get("client_email") else None
	if isinstance(raw, str) and raw.strip():
		with open(raw, encoding="utf-8") as handle:
			parsed = json.loads(handle.read())
		return parsed if parsed.get("client_email") else None
	return None


def _send_fcm(token: str, title: str, body: str, data: dict) -> str:
	account = _firebase_service_account()
	if not account:
		return "skipped"
	access_token = _google_access_token(account)
	if not access_token:
		return "skipped"
	project_id = account.get("project_id")
	if not project_id:
		return "skipped"
	payload = json.dumps(
		{
			"message": {
				"token": token,
				"notification": {"title": title, "body": body},
				"data": {str(key): "" if value is None else str(value) for key, value in data.items()},
			}
		}
	).encode()
	request = Request(
		f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send",
		data=payload,
		headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
		method="POST",
	)
	try:
		with urlopen(request, timeout=10) as response:
			response.read()
		return "ok"
	except HTTPError as exc:
		detail = exc.read().decode("utf-8", errors="replace")
		if exc.code in (404, 410) or "UNREGISTERED" in detail or "INVALID_ARGUMENT" in detail:
			return "stale"
		frappe.log_error(title="hrms_custom: FCM HTTP error", message=f"{exc.code} {detail}")
		return "error"
	except URLError as exc:
		frappe.log_error(title="hrms_custom: FCM network error", message=str(exc))
		return "error"


def _google_access_token(account: dict) -> str | None:
	try:
		from google.oauth2 import service_account
	except ImportError:
		return None
	credentials = service_account.Credentials.from_service_account_info(account, scopes=[FCM_SCOPE])
	from google.auth.transport.requests import Request as GoogleRequest

	credentials.refresh(GoogleRequest())
	return credentials.token
