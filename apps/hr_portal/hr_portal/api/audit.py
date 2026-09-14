from __future__ import annotations

import frappe

from hr_portal.constants import PAYROLL_ADMIN_ROLES
from hr_portal.utils import require_roles


def _map_audit(row: dict) -> dict:
	return {
		"id": row.name,
		"actorUserId": row.actor_user or "",
		"action": row.action or "",
		"entityType": row.entity_type or "",
		"entityId": row.entity_id or "",
		"meta": row.event_meta or {},
		"createdAt": str(row.creation) if row.get("creation") else "",
	}


@frappe.whitelist()
def list_audit_logs(limit: int = 50) -> list[dict]:
	require_roles(*PAYROLL_ADMIN_ROLES)
	limit = max(1, min(int(limit or 50), 200))
	rows = frappe.get_all(
		"HR Audit Log",
		fields=["name", "actor_user", "action", "entity_type", "entity_id", "event_meta", "creation"],
		order_by="creation desc",
		limit=limit,
	)
	return [_map_audit(row) for row in rows]
