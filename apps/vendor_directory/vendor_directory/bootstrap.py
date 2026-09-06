# Copyright (c) 2026, Vendor Directory and contributors
# For license information, please see license.txt

"""One-shot helpers used during Docker site bootstrap."""

from __future__ import annotations

import json
import os
from pathlib import Path

import frappe
from frappe.core.doctype.user.user import generate_keys


def write_api_credentials(path: str | None = None) -> dict:
	"""Generate Administrator API keys and write them for the Next.js BFF."""
	out = Path(path or os.environ.get("CREDENTIALS_FILE", "/shared/credentials.json"))
	frappe.set_user("Administrator")
	result = generate_keys("Administrator")
	frappe.db.commit()

	payload = {
		"FRAPPE_API_KEY": result["api_key"],
		"FRAPPE_API_SECRET": result["api_secret"],
		"FRAPPE_SITE_NAME": frappe.local.site,
		"FRAPPE_URL": os.environ.get("FRAPPE_INTERNAL_URL", "http://backend:8000"),
	}
	out.parent.mkdir(parents=True, exist_ok=True)
	out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
	print(f"Wrote API credentials to {out}")
	return payload
