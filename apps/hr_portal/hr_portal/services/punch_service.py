from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

import frappe
from frappe.utils import get_datetime, now_datetime

from hr_portal.lib.attendance_shift import (
	WorkShift,
	build_shift_occurrence,
	candidate_shift_dates,
	compute_punch_in_status,
	finalize_attendance_on_punch_out,
	hhmm_from_timestamp,
	resolve_punch_in_occurrence,
	resolve_punch_out_occurrence,
	shift_from_employee_fallback,
)
from hr_portal.lib.geo import distance_meters, is_inside_geofence

OPEN_SHIFT_MAX_AGE_MS = 12 * 60 * 60 * 1000


def _ms(now_ms: int | None = None) -> int:
	return int(now_ms if now_ms is not None else datetime.now(tz=timezone.utc).timestamp() * 1000)


def _dt_from_ms(value: int) -> datetime:
	# Frappe/MariaDB expect naive datetimes (UTC wall clock).
	return get_datetime(datetime.utcfromtimestamp(value / 1000))


def _ms_from_dt(value) -> int:
	if not value:
		return 0
	return int(get_datetime(value).replace(tzinfo=timezone.utc).timestamp() * 1000)


def _hhmm(value) -> str:
	if value is None or value == "":
		return ""
	if hasattr(value, "total_seconds"):
		seconds = int(value.total_seconds()) % (24 * 3600)
		hours, rem = divmod(seconds, 3600)
		minutes, _ = divmod(rem, 60)
		return f"{hours:02d}:{minutes:02d}"
	text = str(value)
	return text[:5] if len(text) >= 5 else text


def _get_settings() -> dict:
	row = frappe.get_single("HR Settings")
	return {
		"timezone": row.timezone or "Asia/Kolkata",
		"late_grace_minutes": int(row.late_grace_minutes or 15),
	}


def _shift_from_doc(name: str | None, late_grace: int) -> WorkShift | None:
	if not name:
		return None
	row = frappe.db.get_value(
		"HR Shift",
		name,
		[
			"name",
			"shift_name",
			"code",
			"shift_type",
			"start_time",
			"end_time",
			"crosses_midnight",
			"punch_in_before_minutes",
			"punch_in_after_minutes",
			"punch_out_before_minutes",
			"punch_out_after_minutes",
			"late_grace_minutes",
			"early_leave_grace_minutes",
			"full_day_minutes",
			"half_day_minutes",
			"overtime_after_minutes",
			"status",
		],
		as_dict=True,
	)
	if not row or row.get("status") != "Active":
		return None
	return WorkShift(
		id=row.name,
		name=row.shift_name or row.code,
		code=row.code or row.name,
		shift_type=row.shift_type or "general",
		start_time=_hhmm(row.start_time),
		end_time=_hhmm(row.end_time),
		crosses_midnight=bool(row.crosses_midnight),
		punch_in_before_minutes=int(row.punch_in_before_minutes or 120),
		punch_in_after_minutes=int(row.punch_in_after_minutes or 240),
		punch_out_before_minutes=int(row.punch_out_before_minutes or 120),
		punch_out_after_minutes=int(row.punch_out_after_minutes or 240),
		late_grace_minutes=int(row.late_grace_minutes or late_grace),
		early_leave_grace_minutes=int(row.early_leave_grace_minutes or late_grace),
		full_day_minutes=int(row.full_day_minutes or 480),
		half_day_minutes=int(row.half_day_minutes or 240),
		overtime_after_minutes=int(row.overtime_after_minutes or 480),
	)


def _load_default_shift(employee: dict, late_grace: int) -> WorkShift:
	shift = _shift_from_doc(employee.get("default_shift"), late_grace)
	if shift:
		return shift
	return shift_from_employee_fallback(
		_hhmm(employee.get("work_shift_start")) or "09:00",
		_hhmm(employee.get("work_shift_end")) or "18:00",
		late_grace,
	)


def _load_sites(employee: dict) -> list[dict]:
	site_ids: list[str] = []
	if employee.get("primary_site"):
		site_ids.append(employee["primary_site"])
	rows = frappe.get_all(
		"HR Site",
		filters={"status": "Active"},
		fields=["name", "site_name", "latitude", "longitude", "radius_meters"],
	)
	if site_ids:
		rows = [r for r in rows if r.name in site_ids] or rows
	return rows


def _pick_best_site(lat: float, lon: float, sites: list[dict]) -> dict | None:
	best: dict | None = None
	for site in sites:
		distance = distance_meters(lat, lon, float(site.latitude), float(site.longitude))
		inside, _ = is_inside_geofence(
			lat, lon, float(site.latitude), float(site.longitude), float(site.radius_meters or 500)
		)
		candidate = {"site": site, "distance": distance, "inside": inside}
		if best is None or candidate["distance"] < best["distance"]:
			best = candidate
	return best


def _resolve_punch_location(
	employee: dict, lat: float, lon: float, sites: list[dict]
) -> dict:
	policy = employee.get("attendance_policy") or "geofenced"
	if policy == "manual":
		frappe.throw("Self punch is disabled for your account. Contact HR to mark attendance.")
	if policy == "gps_logged":
		match = _pick_best_site(lat, lon, sites) if sites else None
		if match and match["inside"]:
			name = match["site"]["site_name"]
			return {
				"site": match["site"]["name"],
				"location_name": name,
				"geofence_status": "GPS_ONLY",
				"distance_meters": int(round(match["distance"])),
			}
		if match:
			name = match["site"]["site_name"]
			return {
				"site": match["site"]["name"],
				"location_name": f"Field ({int(round(match['distance']))}m from {name})",
				"geofence_status": "GPS_ONLY",
				"distance_meters": int(round(match["distance"])),
			}
		return {
			"site": employee.get("primary_site") or "",
			"location_name": "Field (GPS logged)",
			"geofence_status": "GPS_ONLY",
			"distance_meters": 0,
		}
	if not sites:
		frappe.throw("No active site assigned. Ask HR to assign a geofence site.")
	match = _pick_best_site(lat, lon, sites)
	if not match:
		frappe.throw("Unable to evaluate geofence.")
	if not match["inside"]:
		name = match["site"]["site_name"]
		frappe.throw(f"Outside geofence ({int(round(match['distance']))}m from {name}).")
	return {
		"site": match["site"]["name"],
		"location_name": match["site"]["site_name"],
		"geofence_status": "INSIDE",
		"distance_meters": int(round(match["distance"])),
	}


def _open_shift_cutoff_ms(now_ms: int | None = None) -> int:
	return _ms(now_ms) - OPEN_SHIFT_MAX_AGE_MS


def _find_open_segment(employee_name: str, now_ms: int | None = None) -> dict | None:
	cutoff = _open_shift_cutoff_ms(now_ms)
	rows = frappe.db.sql(
		"""
		SELECT seg.name, seg.parent, seg.segment_index, seg.clock_in_timestamp, att.date_iso
		FROM `tabHR Punch Segment` seg
		INNER JOIN `tabHR Attendance` att ON att.name = seg.parent
		WHERE att.employee = %s AND seg.is_open = 1
		ORDER BY seg.clock_in_timestamp DESC
		LIMIT 5
		""",
		(employee_name,),
		as_dict=True,
	)
	for row in rows:
		if _ms_from_dt(row.clock_in_timestamp) >= cutoff:
			return row
	return None


def _find_open_attendance(employee_name: str, now_ms: int | None = None) -> frappe.Document | None:
	cutoff = _open_shift_cutoff_ms(now_ms)
	rows = frappe.get_all(
		"HR Attendance",
		filters={"employee": employee_name},
		fields=["name", "clock_in_time", "clock_out_time", "clock_in_timestamp", "date_iso"],
		order_by="clock_in_timestamp desc",
		limit=5,
	)
	for row in rows:
		if row.clock_in_time and not row.clock_out_time:
			if _ms_from_dt(row.clock_in_timestamp) >= cutoff:
				return frappe.get_doc("HR Attendance", row.name)
	return None


def _list_assignments(employee_name: str, dates: list[str]) -> list[dict]:
	return frappe.get_all(
		"HR Shift Assignment",
		filters={
			"employee": employee_name,
			"assignment_date": ("in", dates),
			"status": ("in", ["Scheduled", "Completed"]),
		},
		fields=["name", "shift", "assignment_date", "sequence"],
		order_by="sequence asc",
	)


def _resolve_punch_in_candidate(
	employee: dict, now_ms: int, tz: str, late_grace: int
) -> dict | None:
	dates = candidate_shift_dates(now_ms, tz)
	assignments = _list_assignments(employee["name"], dates)
	candidates: list[dict] = []
	for assignment in assignments:
		shift = _shift_from_doc(assignment.shift, late_grace)
		if not shift:
			continue
		occurrence = build_shift_occurrence(shift, str(assignment.assignment_date), tz)
		if occurrence.punch_in_window_start_ms <= now_ms <= occurrence.punch_in_window_end_ms:
			candidates.append(
				{"shift": shift, "sequence": int(assignment.sequence or 1), "occurrence": occurrence}
			)
	if not candidates:
		fallback = _load_default_shift(employee, late_grace)
		occurrence = resolve_punch_in_occurrence(fallback, now_ms, tz)
		if occurrence:
			candidates.append({"shift": fallback, "sequence": 1, "occurrence": occurrence})
	candidates.sort(key=lambda c: c["occurrence"].scheduled_start_ms, reverse=True)
	return candidates[0] if candidates else None


def _find_attendance_for_shift(
	employee_name: str, shift_date_iso: str, shift_id: str, sequence: int
) -> frappe.Document | None:
	rows = frappe.get_all(
		"HR Attendance",
		filters={"employee": employee_name, "date_iso": shift_date_iso},
		fields=["name", "shift", "assignment_sequence", "clock_in_time", "clock_out_time", "status"],
		limit=20,
	)
	for row in rows:
		if str(row.shift or "") == str(shift_id or "") and int(row.assignment_sequence or 1) == sequence:
			return frappe.get_doc("HR Attendance", row.name)
	if sequence == 1 and not shift_id:
		for row in rows:
			if not row.shift or int(row.assignment_sequence or 1) == 1:
				return frappe.get_doc("HR Attendance", row.name)
	return None


def _sum_segment_minutes(segments: list) -> int:
	total = 0
	for seg in segments:
		if seg.clock_in_timestamp and seg.clock_out_timestamp:
			delta = _ms_from_dt(seg.clock_out_timestamp) - _ms_from_dt(seg.clock_in_timestamp)
			total += max(0, round(delta / 60_000))
	return total


def attendance_to_record(doc: frappe.Document) -> dict:
	return {
		"id": doc.name,
		"userId": doc.user or "",
		"dateIso": str(doc.date_iso),
		"dayOfWeek": doc.day_of_week or "",
		"formattedDate": str(doc.date_iso),
		"clockInTime": doc.clock_in_time or "",
		"clockInTimestamp": _ms_from_dt(doc.clock_in_timestamp),
		"clockOutTime": doc.clock_out_time or None,
		"clockOutTimestamp": _ms_from_dt(doc.clock_out_timestamp) if doc.clock_out_timestamp else None,
		"totalMinutes": int(doc.total_minutes or 0),
		"status": doc.status or "PRESENT",
		"locationName": doc.location_name or "",
		"distanceMeters": int(doc.distance_meters or 0),
		"note": doc.note or None,
		"shiftId": doc.shift or "",
		"assignmentSequence": int(doc.assignment_sequence or 1),
		"earlyDeparture": bool(doc.early_departure),
		"overtimeMinutes": int(doc.overtime_minutes or 0),
		"segmentCount": int(doc.segment_count or 1),
	}


def process_punch(
	employee_name: str,
	punch_type: Literal["in", "out"],
	lat: float,
	lon: float,
	*,
	accuracy: float = 0,
	device_id: str = "",
	timezone: str | None = None,
	now_ms: int | None = None,
) -> dict[str, Any]:
	employee = frappe.db.get_value(
		"HR Employee",
		employee_name,
		[
			"name",
			"user",
			"attendance_policy",
			"primary_site",
			"default_shift",
			"work_shift_start",
			"work_shift_end",
			"status",
		],
		as_dict=True,
	)
	if not employee or employee.get("status") != "Active":
		frappe.throw("Employee membership not found.")

	settings = _get_settings()
	tz = timezone or settings["timezone"]
	now_ms = _ms(now_ms)
	late_grace = settings["late_grace_minutes"]

	sites = _load_sites(employee)
	open_segment = _find_open_segment(employee_name, now_ms)
	open_attendance = _find_open_attendance(employee_name, now_ms) if punch_type == "in" else None
	punch_in_candidate = _resolve_punch_in_candidate(employee, now_ms, tz, late_grace) if punch_type == "in" else None
	punch_location = _resolve_punch_location(employee, lat, lon, sites)

	if punch_type == "in":
		if open_segment:
			frappe.throw(
				f"Already punched in (segment {int(open_segment.segment_index or 0) + 1} on {open_segment.date_iso}). Punch out first."
			)
		if open_attendance:
			frappe.throw(f"Already punched in on {open_attendance.date_iso}. Punch out first.")
		if not punch_in_candidate:
			frappe.throw(
				"Outside punch-in window for all assigned / default shifts. Check roster or shift hours."
			)

		candidate = punch_in_candidate
		shift = candidate["shift"]
		sequence = candidate["sequence"]
		occurrence = candidate["occurrence"]
		status = compute_punch_in_status(now_ms, occurrence)
		clock_time = hhmm_from_timestamp(now_ms, tz)
		existing = _find_attendance_for_shift(employee_name, occurrence.shift_date_iso, shift.id, sequence)

		if existing:
			doc = existing
			if doc.clock_in_time and not doc.clock_out_time:
				open_rows = [s for s in doc.segments if s.is_open]
				if not doc.segments or open_rows:
					frappe.throw(f"Already punched in for shift date {occurrence.shift_date_iso}.")
			segment_index = len(doc.segments)
			is_first = len(doc.segments) == 0 and not doc.clock_in_time
			keep_status = bool(doc.clock_in_time)
		else:
			doc = frappe.new_doc("HR Attendance")
			doc.employee = employee_name
			doc.user = employee.get("user") or ""
			doc.date_iso = occurrence.shift_date_iso
			segment_index = 0
			is_first = True
			keep_status = False

		doc.day_of_week = occurrence.day_of_week
		doc.shift = shift.id or ""
		doc.assignment_sequence = sequence
		doc.is_overnight = occurrence.is_overnight
		doc.scheduled_start_timestamp = _dt_from_ms(occurrence.scheduled_start_ms)
		doc.scheduled_end_timestamp = _dt_from_ms(occurrence.scheduled_end_ms)
		doc.status = doc.status if keep_status else status
		doc.site = punch_location["site"]
		doc.geofence_status = punch_location["geofence_status"]
		doc.distance_meters = punch_location["distance_meters"]
		doc.punch_in_lat = lat
		doc.punch_in_long = lon
		doc.punch_in_accuracy = accuracy
		doc.device_id = device_id
		doc.note = "Overnight / cross-midnight shift" if occurrence.is_overnight else doc.note or ""
		doc.location_name = punch_location["location_name"]
		doc.early_departure = False
		doc.overtime_minutes = 0
		doc.clock_in_time = clock_time if is_first else (doc.clock_in_time or clock_time)
		doc.clock_in_timestamp = _dt_from_ms(now_ms if is_first else _ms_from_dt(doc.clock_in_timestamp) or now_ms)
		doc.clock_out_time = None
		doc.clock_out_timestamp = None
		doc.segment_count = max(1, len(doc.segments) + 1)
		doc.append(
			"segments",
			{
				"segment_index": segment_index,
				"clock_in_time": clock_time,
				"clock_in_timestamp": _dt_from_ms(now_ms),
				"is_open": 1,
				"site": punch_location["site"],
				"device_id": device_id,
				"punch_in_lat": lat,
				"punch_in_long": lon,
			},
		)
		doc.flags.ignore_permissions = True
		doc.save()

		record = attendance_to_record(doc)
		segment_label = f" (segment {segment_index + 1})" if segment_index > 0 else ""
		message = (
			f"Punched in late for shift {occurrence.shift_date_iso}{segment_label}."
			if status == "LATE"
			else f"Punched in for shift {occurrence.shift_date_iso}{segment_label}."
		)
		return {"record": record, "message": message}

	# punch out
	doc = None
	if open_segment:
		doc = frappe.get_doc("HR Attendance", open_segment.parent)
	if not doc:
		doc = _find_open_attendance(employee_name, now_ms)
	if not doc or (not doc.clock_in_time and not open_segment):
		frappe.throw("Punch in first before punching out.")

	shift_date_iso = str(doc.date_iso)
	shift = _shift_from_doc(doc.shift, late_grace) or _load_default_shift(employee, late_grace)
	occurrence = resolve_punch_out_occurrence(shift, shift_date_iso, tz)

	if now_ms < occurrence.punch_out_window_start_ms or now_ms > occurrence.punch_out_window_end_ms:
		first_in = _ms_from_dt(doc.clock_in_timestamp)
		soft_end = first_in + 20 * 60 * 60 * 1000
		if now_ms > soft_end and now_ms > occurrence.punch_out_window_end_ms:
			frappe.throw(
				f"Outside punch-out window for shift date {shift_date_iso}. Request regularization if needed."
			)

	clock_out_time = hhmm_from_timestamp(now_ms, tz)
	from hr_portal.lib.attendance_shift import date_iso_in_timezone

	punch_out_date, _ = date_iso_in_timezone(now_ms, tz)

	open_rows = [s for s in doc.segments if s.is_open]
	if open_rows:
		seg = open_rows[0]
		seg.clock_out_time = clock_out_time
		seg.clock_out_timestamp = _dt_from_ms(now_ms)
		seg.is_open = 0
		seg.punch_out_lat = lat
		seg.punch_out_long = lon
		seg.site = punch_location["site"]
		seg.device_id = device_id or seg.device_id

	closed = [s for s in doc.segments if s.clock_in_timestamp and s.clock_out_timestamp and not s.is_open]
	has_open = any(s.is_open for s in doc.segments)
	first_in = _ms_from_dt(doc.segments[0].clock_in_timestamp if doc.segments else doc.clock_in_timestamp)
	last_out = None if has_open else max(_ms_from_dt(s.clock_out_timestamp) for s in closed) if closed else now_ms
	total_from_segments = _sum_segment_minutes(closed) if closed else max(0, round((now_ms - first_in) / 60_000))

	finalized = finalize_attendance_on_punch_out(
		doc.status or "PRESENT",
		first_in,
		last_out or now_ms,
		occurrence,
	)
	total_minutes = total_from_segments if len(closed) > 1 else finalized.total_minutes

	if not has_open:
		doc.clock_out_time = clock_out_time
		doc.clock_out_timestamp = _dt_from_ms(last_out or now_ms)
		doc.total_minutes = total_minutes
		doc.early_departure = finalized.early_departure
		doc.overtime_minutes = finalized.overtime_minutes
		doc.status = finalized.status
	else:
		doc.total_minutes = total_from_segments
		doc.early_departure = False
		doc.overtime_minutes = 0

	doc.is_overnight = occurrence.is_overnight or punch_out_date != shift_date_iso
	doc.scheduled_start_timestamp = doc.scheduled_start_timestamp or _dt_from_ms(occurrence.scheduled_start_ms)
	doc.scheduled_end_timestamp = doc.scheduled_end_timestamp or _dt_from_ms(occurrence.scheduled_end_ms)
	doc.shift = doc.shift or shift.id or ""
	doc.assignment_sequence = doc.assignment_sequence or 1
	doc.segment_count = max(len(doc.segments), 1)
	doc.punch_out_lat = lat
	doc.punch_out_long = lon
	doc.punch_out_accuracy = accuracy
	doc.distance_meters = punch_location["distance_meters"]
	doc.site = punch_location["site"]
	doc.location_name = punch_location["location_name"]
	doc.geofence_status = punch_location["geofence_status"]
	doc.device_id = device_id or doc.device_id
	if punch_out_date != shift_date_iso:
		doc.note = f"Cross-day punch-out on {punch_out_date} for shift {shift_date_iso}"
	doc.flags.ignore_permissions = True
	doc.save()

	record = attendance_to_record(doc)
	extras = [
		"early departure" if not has_open and finalized.early_departure else None,
		f"{finalized.overtime_minutes}m OT" if not has_open and finalized.overtime_minutes > 0 else None,
		f"{len(doc.segments)} segments" if len(doc.segments) > 1 else None,
	]
	extras = [x for x in extras if x]
	message = (
		f"Punched out for shift {shift_date_iso} ({', '.join(extras)})."
		if extras
		else f"Punched out for shift {shift_date_iso}."
	)
	return {"record": record, "message": message}


def close_open_segments_for_regularization(
	attendance_name: str,
	*,
	clock_out_time: str = "",
	clock_out_timestamp_ms: int | None = None,
) -> None:
	doc = frappe.get_doc("HR Attendance", attendance_name)
	changed = False
	for seg in doc.segments:
		if seg.is_open:
			seg.is_open = 0
			seg.clock_out_time = clock_out_time or seg.clock_out_time
			seg.clock_out_timestamp = _dt_from_ms(
				clock_out_timestamp_ms or _ms_from_dt(seg.clock_out_timestamp) or _ms()
			)
			changed = True
	if changed:
		doc.flags.ignore_permissions = True
		doc.save()
