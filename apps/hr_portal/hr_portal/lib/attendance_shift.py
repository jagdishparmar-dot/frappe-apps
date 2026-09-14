from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

AttendanceStatus = Literal["PRESENT", "LATE", "HALF_DAY", "ABSENT", "ON_LEAVE", "LEAVE_PENDING"]
ShiftType = Literal["general", "evening", "night", "rotational", "cross_midnight"]


@dataclass
class WorkShift:
	id: str
	name: str
	code: str
	shift_type: ShiftType
	start_time: str
	end_time: str
	crosses_midnight: bool
	punch_in_before_minutes: int
	punch_in_after_minutes: int
	punch_out_before_minutes: int
	punch_out_after_minutes: int
	late_grace_minutes: int
	early_leave_grace_minutes: int
	full_day_minutes: int
	half_day_minutes: int
	overtime_after_minutes: int
	status: str = "Active"


@dataclass
class ShiftOccurrence:
	shift: WorkShift
	shift_date_iso: str
	day_of_week: str
	scheduled_start_ms: int
	scheduled_end_ms: int
	punch_in_window_start_ms: int
	punch_in_window_end_ms: int
	punch_out_window_start_ms: int
	punch_out_window_end_ms: int
	is_overnight: bool


@dataclass
class PunchFinalizeResult:
	status: AttendanceStatus
	early_departure: bool
	overtime_minutes: int
	total_minutes: int


def pad2(value: int) -> str:
	return str(value).zfill(2)


def minutes_from_hhmm(value: str) -> int:
	parts = value.split(":")
	h = int(parts[0]) if parts and parts[0].isdigit() else 0
	m = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
	return h * 60 + m


def _hhmm_from_dt(dt: datetime) -> str:
	return dt.strftime("%H:%M")


def date_iso_in_timezone(timestamp_ms: int, tz_name: str) -> tuple[str, str]:
	dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=ZoneInfo(tz_name))
	return dt.strftime("%Y-%m-%d"), dt.strftime("%a")


def hhmm_from_timestamp(timestamp_ms: int, tz_name: str) -> str:
	dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=ZoneInfo(tz_name))
	return _hhmm_from_dt(dt)


def add_days_iso(date_iso: str, days: int) -> str:
	d = date.fromisoformat(date_iso)
	return (d + timedelta(days=days)).isoformat()


def zoned_datetime_to_utc_ms(date_iso: str, time_hhmm: str, tz_name: str) -> int:
	year, month, day = (int(x) for x in date_iso.split("-"))
	hour, minute = (int(x) for x in time_hhmm.split(":"))
	tz = ZoneInfo(tz_name)
	utc = datetime(year, month, day, hour, minute, tzinfo=tz).astimezone(timezone.utc)
	return int(utc.timestamp() * 1000)


def infer_crosses_midnight(start_time: str, end_time: str) -> bool:
	return minutes_from_hhmm(end_time) <= minutes_from_hhmm(start_time)


def infer_shift_type(start_time: str, end_time: str) -> ShiftType:
	if infer_crosses_midnight(start_time, end_time):
		return "cross_midnight"
	start = minutes_from_hhmm(start_time)
	if start >= 16 * 60:
		return "evening"
	if start >= 20 * 60 or start < 5 * 60:
		return "night"
	return "general"


def shift_from_employee_fallback(
	start_time: str,
	end_time: str,
	late_grace_minutes: int,
) -> WorkShift:
	start_time = start_time or "09:00"
	end_time = end_time or "18:00"
	crosses = infer_crosses_midnight(start_time, end_time)
	span = (
		minutes_from_hhmm(end_time)
		- minutes_from_hhmm(start_time)
		+ (24 * 60 if crosses else 0)
		+ 24 * 60
	) % (24 * 60) or 8 * 60
	return WorkShift(
		id="",
		name="Assigned hours",
		code="DEFAULT",
		shift_type=infer_shift_type(start_time, end_time),
		start_time=start_time,
		end_time=end_time,
		crosses_midnight=crosses,
		punch_in_before_minutes=120,
		punch_in_after_minutes=240,
		punch_out_before_minutes=120,
		punch_out_after_minutes=240,
		late_grace_minutes=late_grace_minutes,
		early_leave_grace_minutes=late_grace_minutes,
		full_day_minutes=span,
		half_day_minutes=max(60, span // 2),
		overtime_after_minutes=span,
	)


def build_shift_occurrence(shift: WorkShift, shift_date_iso: str, tz_name: str) -> ShiftOccurrence:
	crosses = shift.crosses_midnight or infer_crosses_midnight(shift.start_time, shift.end_time)
	scheduled_start_ms = zoned_datetime_to_utc_ms(shift_date_iso, shift.start_time, tz_name)
	end_date_iso = add_days_iso(shift_date_iso, 1) if crosses else shift_date_iso
	scheduled_end_ms = zoned_datetime_to_utc_ms(end_date_iso, shift.end_time, tz_name)
	_, day_of_week = date_iso_in_timezone(scheduled_start_ms, tz_name)
	return ShiftOccurrence(
		shift=shift,
		shift_date_iso=shift_date_iso,
		day_of_week=day_of_week,
		scheduled_start_ms=scheduled_start_ms,
		scheduled_end_ms=scheduled_end_ms,
		punch_in_window_start_ms=scheduled_start_ms - shift.punch_in_before_minutes * 60_000,
		punch_in_window_end_ms=scheduled_start_ms + shift.punch_in_after_minutes * 60_000,
		punch_out_window_start_ms=scheduled_end_ms - shift.punch_out_before_minutes * 60_000,
		punch_out_window_end_ms=scheduled_end_ms + shift.punch_out_after_minutes * 60_000,
		is_overnight=crosses,
	)


def candidate_shift_dates(now_ms: int, tz_name: str) -> list[str]:
	today, _ = date_iso_in_timezone(now_ms, tz_name)
	return [today, add_days_iso(today, -1)]


def resolve_punch_in_occurrence(
	shift: WorkShift, now_ms: int, tz_name: str
) -> ShiftOccurrence | None:
	candidates = [
		build_shift_occurrence(shift, date_iso, tz_name)
		for date_iso in candidate_shift_dates(now_ms, tz_name)
	]
	candidates = [
		o
		for o in candidates
		if o.punch_in_window_start_ms <= now_ms <= o.punch_in_window_end_ms
	]
	candidates.sort(key=lambda o: o.scheduled_start_ms, reverse=True)
	return candidates[0] if candidates else None


def resolve_punch_out_occurrence(
	shift: WorkShift, shift_date_iso: str, tz_name: str
) -> ShiftOccurrence:
	return build_shift_occurrence(shift, shift_date_iso, tz_name)


def compute_punch_in_status(now_ms: int, occurrence: ShiftOccurrence) -> AttendanceStatus:
	grace_ms = occurrence.shift.late_grace_minutes * 60_000
	if now_ms > occurrence.scheduled_start_ms + grace_ms:
		return "LATE"
	return "PRESENT"


def format_shift_window_label(shift: dict) -> str:
	start = shift.get("startTime") or shift.get("start_time") or ""
	end = shift.get("endTime") or shift.get("end_time") or ""
	crosses = shift.get("crossesMidnight") or shift.get("crosses_midnight")
	if crosses or infer_crosses_midnight(start, end):
		return f"{start} – {end} (+1 day)"
	return f"{start} – {end}"


def finalize_attendance_on_punch_out(
	punch_in_status: AttendanceStatus,
	clock_in_timestamp: int,
	clock_out_timestamp: int,
	occurrence: ShiftOccurrence,
) -> PunchFinalizeResult:
	total_minutes = max(0, round((clock_out_timestamp - clock_in_timestamp) / 60_000))
	shift = occurrence.shift
	early_departure = clock_out_timestamp < occurrence.scheduled_end_ms - shift.early_leave_grace_minutes * 60_000
	overtime_minutes = max(0, total_minutes - shift.overtime_after_minutes)
	status: AttendanceStatus = punch_in_status
	if status in ("ON_LEAVE", "LEAVE_PENDING", "ABSENT"):
		status = "PRESENT"
	if total_minutes < shift.half_day_minutes:
		status = "HALF_DAY"
	elif status != "LATE":
		status = "PRESENT"
	return PunchFinalizeResult(
		status=status,
		early_departure=early_departure,
		overtime_minutes=overtime_minutes,
		total_minutes=total_minutes,
	)
