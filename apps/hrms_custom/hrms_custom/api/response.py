"""Standard `{success, message, data}` envelope for every hrms_custom endpoint (spec section 3)."""

import functools
from typing import Any

import frappe
from werkzeug.wrappers import Response


class ApiError(Exception):
	def __init__(self, message: str, status: int = 400, data: dict | None = None):
		super().__init__(message)
		self.message = message
		self.status = status
		self.data = data or {}


def success(data: Any = None, message: str = "", status: int = 200) -> Response:
	return _json_response(True, message, data, status)


def failure(message: str, status: int = 400, data: Any = None) -> Response:
	return _json_response(False, message, data, status)


def _json_response(ok: bool, message: str, data: Any, status: int) -> Response:
	body = {"success": ok, "message": message, "data": data if data is not None else {}}
	return Response(frappe.as_json(body, indent=None), status=status, mimetype="application/json")


def api_endpoint(fn):
	"""Wrap an endpoint so every outcome, including errors, is returned as the envelope.

	Apply *below* `@frappe.whitelist()`. Errors roll back the transaction before responding.
	"""

	@functools.wraps(fn)
	def wrapper(*args, **kwargs):
		try:
			result = fn(*args, **kwargs)
		except ApiError as e:
			return _error(e.message, e.status, e.data)
		except (frappe.RateLimitExceededError, frappe.TooManyRequestsError):
			return _error("Too many attempts. Please wait and try again.", 429)
		except frappe.AuthenticationError as e:
			return _error(_message(e, "Authentication required"), 401)
		except frappe.PermissionError as e:
			return _error(_message(e, "Not permitted"), 403)
		except frappe.DoesNotExistError as e:
			return _error(_message(e, "Not found"), 404)
		except frappe.ValidationError as e:
			return _error(_message(e, "Invalid request"), 400)
		except Exception:
			frappe.log_error(title=f"hrms_custom API error: {fn.__module__}.{fn.__name__}")
			return _error("Something went wrong. Please try again.", 500)

		if isinstance(result, Response):
			return result
		return success(result)

	return wrapper


def _error(message: str, status: int, data: Any = None) -> Response:
	frappe.db.rollback()
	frappe.local.message_log = []
	return failure(message, status, data)


def _message(exc: Exception, fallback: str) -> str:
	text = str(exc).strip()
	return frappe.utils.strip_html_tags(text) if text else fallback
