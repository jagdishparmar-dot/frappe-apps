"""Password login for the mobile app, with OTP only when an employee resets a forgotten password.

A successful login issues Frappe API key/secret credentials. Issuing a new secret invalidates the
previous one, so a user is signed in on one device at a time.
"""

import hashlib
import hmac
import re
import secrets
import time

import frappe
from frappe.rate_limiter import rate_limit
from frappe.utils import cint
from frappe.utils.password import check_password, set_encrypted_password, update_password

from hrms_custom.api.response import ApiError, api_endpoint, success
from hrms_custom.api.session import can_log_in

OTP_LENGTH = 6
CACHE_PREFIX = "hrms_custom:otp:"
GENERIC_SENT_MESSAGE = "If an account exists for these details, a verification code has been sent."
INVALID_CODE = "The code is invalid or has expired. Please request a new one."
INVALID_CREDENTIALS = (
	"Incorrect email, employee ID, mobile number, or password. Use Forgot password if you need to set one."
)
_EMPLOYEE_FIELDS = [
	"name",
	"user_id",
	"cell_number",
	"company_email",
	"personal_email",
	"status",
	"onboarding_status",
]


@frappe.whitelist(allow_guest=True, methods=["POST"])
@api_endpoint
@rate_limit(key="mobile_or_email", ip_based=False, limit=10, seconds=10 * 60)
@rate_limit(limit=120, seconds=10 * 60)
def login_with_password(mobile_or_email=None, password=None):
	identifier = _normalize_identifier(mobile_or_email)
	password = password or ""
	account = _resolve_account(identifier) if password else None
	if not account:
		raise ApiError(INVALID_CREDENTIALS, 401)
	try:
		check_password(account.user, password)
	except frappe.AuthenticationError:
		raise ApiError(INVALID_CREDENTIALS, 401)
	return _login_success(account.user)


@frappe.whitelist(allow_guest=True, methods=["POST"])
@api_endpoint
@rate_limit(key="mobile_or_email", ip_based=False, limit=5, seconds=10 * 60)
@rate_limit(limit=60, seconds=10 * 60)
def request_otp(mobile_or_email=None):
	identifier = _normalize_identifier(mobile_or_email)
	settings = _otp_settings()
	data = {"expires_in_seconds": settings["expiry_seconds"]}

	account = _resolve_account(identifier)
	if not account or not account.address:
		# Same response as success, so the endpoint cannot be used to discover accounts.
		return success(data, GENERIC_SENT_MESSAGE)

	otp = "".join(secrets.choice("0123456789") for _ in range(OTP_LENGTH))
	frappe.cache.set_value(
		CACHE_PREFIX + identifier,
		{
			"user": account.user,
			"hash": _hash(otp, account.user),
			"attempts": 0,
			"expires_at": time.time() + settings["expiry_seconds"],
		},
		expires_in_sec=settings["expiry_seconds"],
	)
	_deliver(account.address, otp, settings["expiry_seconds"])

	if frappe.conf.developer_mode:
		data["debug_otp"] = otp
	return success(data, GENERIC_SENT_MESSAGE)


@frappe.whitelist(allow_guest=True, methods=["POST"])
@api_endpoint
@rate_limit(key="mobile_or_email", ip_based=False, limit=10, seconds=10 * 60)
@rate_limit(limit=120, seconds=10 * 60)
def verify_otp(mobile_or_email=None, otp=None):
	identifier = _normalize_identifier(mobile_or_email)
	user = _match_otp(identifier, otp, consume=True)
	return _login_success(user)


@frappe.whitelist(allow_guest=True, methods=["POST"])
@api_endpoint
@rate_limit(key="mobile_or_email", ip_based=False, limit=10, seconds=10 * 60)
@rate_limit(limit=120, seconds=10 * 60)
def reset_password(mobile_or_email=None, otp=None, new_password=None):
	identifier = _normalize_identifier(mobile_or_email)
	if not _resolve_account(identifier):
		raise ApiError(INVALID_CODE, 400)
	user = _match_otp(identifier, otp, consume=False)
	_reject_weak_password(user, new_password or "")
	frappe.cache.delete_value(CACHE_PREFIX + identifier)
	update_password(user, new_password, logout_all_sessions=True)
	return _login_success(user)


@frappe.whitelist(methods=["POST"])
@api_endpoint
def logout():
	"""Rotate the secret so the token held by the device stops working."""
	user = frappe.session.user
	if user == "Guest":
		raise ApiError("Please log in to continue", 401)
	set_encrypted_password("User", user, frappe.generate_hash(length=32), "api_secret")
	return success({}, "Logged out")


def _login_success(user: str):
	api_key, api_secret = _issue_api_credentials(user)
	employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
	return success(
		{
			"user": user,
			"employee": employee,
			"api_key": api_key,
			"api_secret": api_secret,
			"token": f"{api_key}:{api_secret}",
		},
		"Logged in successfully",
	)


def _normalize_identifier(value) -> str:
	value = (value or "").strip()
	if not value:
		raise ApiError("Please enter your email, employee ID, or mobile number", 400)
	if "@" in value:
		return value.lower()
	if re.search(r"[A-Za-z]", value):
		return value.upper()
	digits = re.sub(r"\D", "", value)
	if len(digits) >= 10:
		# Mobile numbers are keyed by their last 10 digits, so "+91 98765 43210" == "9876543210".
		return digits[-10:]
	return value.upper()


def _is_mobile(identifier: str) -> bool:
	return identifier.isdigit() and len(identifier) == 10


def _resolve_account(identifier: str):
	"""Find the enabled user behind exactly one Employee (active, or an invited joiner)."""
	if "@" in identifier:
		employees = frappe.get_all(
			"Employee",
			filters={"user_id": ("is", "set")},
			or_filters={"user_id": identifier, "company_email": identifier, "personal_email": identifier},
			fields=_EMPLOYEE_FIELDS,
			limit=5,
		)
	elif _is_mobile(identifier):
		employees = frappe.db.sql(
			"""
			select name, user_id, cell_number, company_email, personal_email, status, onboarding_status
			from `tabEmployee`
			where ifnull(user_id, '') != ''
				and right(regexp_replace(ifnull(cell_number, ''), '[^0-9]', ''), 10) = %s
			limit 5
			""",
			identifier,
			as_dict=True,
		)
	else:
		employees = frappe.get_all(
			"Employee",
			filters={"name": identifier, "user_id": ("is", "set")},
			fields=_EMPLOYEE_FIELDS,
			limit=5,
		)
	employees = [e for e in employees if can_log_in(e.status, e.onboarding_status)]
	if len(employees) != 1:
		return None

	employee = employees[0]
	if not frappe.db.get_value("User", employee.user_id, "enabled"):
		return None
	return frappe._dict(
		user=employee.user_id,
		employee=employee.name,
		address=_delivery_address(employee, identifier),
	)


def _delivery_address(employee, identifier: str):
	if "@" in identifier:
		return identifier
	if _is_mobile(identifier):
		return employee.cell_number
	return employee.company_email or employee.personal_email or employee.cell_number or None


def _match_otp(identifier: str, otp: str, *, consume: bool) -> str:
	otp = (otp or "").strip()
	key = CACHE_PREFIX + identifier
	entry = frappe.cache.get_value(key)
	invalid = ApiError(INVALID_CODE, 400)
	if not entry or not otp:
		raise invalid

	entry["attempts"] += 1
	if entry["attempts"] > _otp_settings()["max_attempts"]:
		frappe.cache.delete_value(key)
		raise ApiError("Too many incorrect attempts. Please request a new code.", 429)

	if not hmac.compare_digest(entry["hash"], _hash(otp, entry["user"])):
		remaining = int(entry["expires_at"] - time.time())
		if remaining > 0:
			frappe.cache.set_value(key, entry, expires_in_sec=remaining)
		else:
			frappe.cache.delete_value(key)
		raise invalid

	if consume:
		frappe.cache.delete_value(key)
	return entry["user"]


def _reject_weak_password(user: str, new_password: str) -> None:
	from frappe.core.doctype.user.user import MAX_PASSWORD_SIZE, handle_password_test_fail, test_password_strength

	if not new_password:
		raise ApiError("Please enter a new password.", 400)
	if len(new_password) > MAX_PASSWORD_SIZE:
		raise ApiError("Password size exceeded the maximum allowed size.", 400)

	user_data = frappe.db.get_value(
		"User", user, ["first_name", "middle_name", "last_name", "email", "birth_date"]
	)
	result = test_password_strength(new_password, user_data=user_data)
	feedback = result.get("feedback", None)
	if feedback and not feedback.get("password_policy_validation_passed", False):
		handle_password_test_fail(feedback)


def _send_otp_email(address: str, text: str) -> None:
	"""Send the login code over SMTP before this request returns."""
	from frappe.email.doctype.email_queue.email_queue import QueueBuilder

	queue = QueueBuilder(
		recipients=[address],
		subject="Your HRMS login code",
		message=text,
	).process(send_now=False)
	if queue:
		queue.send(force_send=True)


def _deliver(address: str, otp: str, expiry_seconds: int) -> None:
	minutes = max(expiry_seconds // 60, 1)
	text = f"{otp} is your HRMS login code. It expires in {minutes} minutes. Do not share it with anyone."
	try:
		if "@" in address:
			_send_otp_email(address, text)
		else:
			from frappe.core.doctype.sms_settings.sms_settings import send_sms

			send_sms([address], text, success_msg=False)
	except Exception:
		frappe.log_error(title="hrms_custom: OTP delivery failed")


def _issue_api_credentials(user: str) -> tuple[str, str]:
	api_key = frappe.db.get_value("User", user, "api_key")
	if not api_key:
		api_key = frappe.generate_hash(length=15)
		frappe.db.set_value("User", user, "api_key", api_key, update_modified=False)
	api_secret = frappe.generate_hash(length=32)
	set_encrypted_password("User", user, api_secret, "api_secret")
	return api_key, api_secret


def _hash(otp: str, user: str) -> str:
	return hashlib.sha256(f"{user}:{otp}:{frappe.local.conf.encryption_key or ''}".encode()).hexdigest()


def _otp_settings() -> dict:
	settings = frappe.get_cached_doc("HRMS Custom Settings")
	return {
		"expiry_seconds": max(cint(settings.otp_expiry_minutes), 1) * 60,
		"max_attempts": max(cint(settings.otp_max_attempts), 1),
	}
