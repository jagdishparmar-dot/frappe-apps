from __future__ import annotations

import frappe


def write_audit_log(
	action: str,
	entity_type: str,
	entity_id: str | None = None,
	meta: dict | None = None,
	actor_user: str | None = None,
) -> str:
	actor = actor_user or frappe.session.user
	doc = frappe.get_doc(
		{
			"doctype": "HR Audit Log",
			"actor_user": actor,
			"action": action,
			"entity_type": entity_type,
			"entity_id": entity_id or "",
			"event_meta": meta or {},
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert()
	return doc.name
