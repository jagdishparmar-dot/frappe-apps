import frappe
from hr_portal.utils import require_employee_write


def _status(value: str | None, default: str = "Active") -> str:
	text = (value or default).strip().title()
	if text.lower() == "inactive":
		return "Inactive"
	return "Active"


@frappe.whitelist()
def save_site(
	site_name: str,
	latitude: float,
	longitude: float,
	radius_meters: int = 500,
	address: str | None = None,
	status: str = "Active",
	name: str | None = None,
) -> dict:
	require_employee_write()
	payload = {
		"doctype": "HR Site",
		"site_name": (site_name or "").strip(),
		"latitude": latitude,
		"longitude": longitude,
		"radius_meters": int(radius_meters or 500),
		"address": address or "",
		"status": _status(status),
	}
	if name:
		doc = frappe.get_doc("HR Site", name)
		doc.update(payload)
		doc.save()
	else:
		doc = frappe.get_doc(payload)
		doc.insert()
	return {"ok": True, "name": doc.name}


@frappe.whitelist()
def save_shift(
	shift_name: str,
	code: str,
	start_time: str,
	end_time: str,
	shift_type: str = "general",
	status: str = "Active",
	late_grace_minutes: int = 15,
	name: str | None = None,
	**kwargs,
) -> dict:
	require_employee_write()
	payload = {
		"doctype": "HR Shift",
		"shift_name": (shift_name or "").strip(),
		"code": (code or "").strip().upper(),
		"start_time": start_time,
		"end_time": end_time,
		"shift_type": shift_type or "general",
		"status": _status(status),
		"late_grace_minutes": int(late_grace_minutes or 15),
		"punch_in_before_minutes": int(kwargs.get("punch_in_before_minutes") or 120),
		"punch_in_after_minutes": int(kwargs.get("punch_in_after_minutes") or 240),
		"punch_out_before_minutes": int(kwargs.get("punch_out_before_minutes") or 120),
		"punch_out_after_minutes": int(kwargs.get("punch_out_after_minutes") or 240),
		"early_leave_grace_minutes": int(kwargs.get("early_leave_grace_minutes") or 15),
		"full_day_minutes": int(kwargs.get("full_day_minutes") or 480),
		"half_day_minutes": int(kwargs.get("half_day_minutes") or 240),
		"overtime_after_minutes": int(kwargs.get("overtime_after_minutes") or 480),
		"crosses_midnight": 1 if kwargs.get("crosses_midnight") else 0,
	}
	if name:
		doc = frappe.get_doc("HR Shift", name)
		doc.update(payload)
		doc.save()
	else:
		doc = frappe.get_doc(payload)
		doc.insert()
	return {"ok": True, "name": doc.name}


@frappe.whitelist()
def save_vendor(
	vendor_name: str,
	contact_name: str | None = None,
	contact_email: str | None = None,
	contact_phone: str | None = None,
	status: str = "Active",
	name: str | None = None,
) -> dict:
	require_employee_write()
	payload = {
		"doctype": "HR Vendor",
		"vendor_name": (vendor_name or "").strip(),
		"contact_name": contact_name or "",
		"contact_email": contact_email or "",
		"contact_phone": contact_phone or "",
		"status": _status(status),
	}
	if name:
		doc = frappe.get_doc("HR Vendor", name)
		doc.update(payload)
		doc.save()
	else:
		doc = frappe.get_doc(payload)
		doc.insert()
	return {"ok": True, "name": doc.name}


@frappe.whitelist()
def save_leave_type(
	leave_type_name: str,
	code: str,
	paid: int = 1,
	accrual_per_month: float = 1,
	max_balance: float = 24,
	carry_forward: int = 0,
	status: str = "Active",
	name: str | None = None,
) -> dict:
	require_employee_write()
	payload = {
		"doctype": "HR Leave Type",
		"leave_type_name": (leave_type_name or "").strip(),
		"code": (code or "").strip().upper(),
		"paid": 1 if paid else 0,
		"accrual_per_month": accrual_per_month,
		"max_balance": max_balance,
		"carry_forward": 1 if carry_forward else 0,
		"status": _status(status),
	}
	if name:
		doc = frappe.get_doc("HR Leave Type", name)
		doc.update(payload)
		doc.save()
	else:
		doc = frappe.get_doc(payload)
		doc.insert()
	return {"ok": True, "name": doc.name}


@frappe.whitelist()
def save_holiday(holiday_date: str, holiday_name: str, region: str | None = None, name: str | None = None) -> dict:
	require_employee_write()
	payload = {
		"doctype": "HR Holiday",
		"holiday_date": holiday_date,
		"holiday_name": (holiday_name or "").strip(),
		"region": region or "",
	}
	if name:
		doc = frappe.get_doc("HR Holiday", name)
		doc.update(payload)
		doc.save()
	else:
		doc = frappe.get_doc(payload)
		doc.insert()
	return {"ok": True, "name": doc.name}
