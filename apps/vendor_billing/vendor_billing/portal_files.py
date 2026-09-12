"""Save / read portal uploads as Frappe File docs (S3 hook runs on insert)."""

from __future__ import annotations

import base64
import mimetypes
import re
from pathlib import Path
from urllib.parse import unquote

import frappe
from frappe import _
from frappe.utils.file_manager import save_file

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_EXT = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}
SUPPORTING_EXT = ALLOWED_EXT | {".doc", ".docx", ".xls", ".xlsx"}


def parse_upload(payload, *, supporting: bool = False) -> dict | None:
    if not payload:
        return None
    if isinstance(payload, str):
        payload = frappe.parse_json(payload)
    if not isinstance(payload, dict):
        return None
    name = (payload.get("fileName") or payload.get("filename") or "").strip()
    raw = payload.get("contentBase64") or payload.get("fileData") or payload.get("content")
    if not name or not raw:
        return None
    if isinstance(raw, str) and "," in raw and raw.strip().startswith("data:"):
        raw = raw.split(",", 1)[1]
    try:
        content = base64.b64decode(raw)
    except Exception:
        frappe.throw(_("Invalid file encoding."))
    if len(content) > MAX_UPLOAD_BYTES:
        frappe.throw(_("File is larger than 10 MB."))
    ext = Path(name).suffix.lower()
    allowed = SUPPORTING_EXT if supporting else ALLOWED_EXT
    if ext not in allowed:
        frappe.throw(
            _("Only PDF, Word, Excel, and image files are allowed.")
            if supporting
            else _("Only PDF, JPEG, PNG, and WEBP files are allowed.")
        )
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:120]
    return {
        "file_name": safe or f"upload{ext}",
        "content": content,
        "content_type": payload.get("fileType") or mimetypes.guess_type(name)[0] or "application/octet-stream",
    }


def attach_bytes(filename: str, content: bytes, dt: str | None = None, dn: str | None = None) -> str:
    doc = save_file(filename, content, dt or None, dn or None, is_private=1)
    return doc.file_url


def reattach(file_url: str, dt: str, dn: str) -> None:
    name = frappe.db.get_value("File", {"file_url": file_url}, "name")
    if not name:
        return
    frappe.db.set_value(
        "File",
        name,
        {"attached_to_doctype": dt, "attached_to_name": dn},
        update_modified=False,
    )


def read_file_bytes(file_url: str) -> bytes:
    if not file_url:
        frappe.throw(_("File not found."), frappe.DoesNotExistError)
    if "vendor_billing.storage.download" in file_url:
        from vendor_billing.storage import get_object_bytes

        key = unquote(file_url.split("key=", 1)[-1])
        return get_object_bytes(key)
    fname = Path(file_url.split("?")[0]).name
    private = Path(frappe.get_site_path("private", "files")) / fname
    public = Path(frappe.get_site_path("public", "files")) / fname
    if "/private/files/" in file_url and private.is_file():
        return private.read_bytes()
    if public.is_file():
        return public.read_bytes()
    if private.is_file():
        return private.read_bytes()
    rel = file_url.lstrip("/")
    local = Path(frappe.get_site_path()) / rel
    if local.is_file():
        return local.read_bytes()
    frappe.throw(_("File not found."), frappe.DoesNotExistError)


def file_payload(file_url: str, file_name: str | None = None) -> dict:
    content = read_file_bytes(file_url)
    name = file_name or Path(file_url).name
    mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
    return {
        "fileName": name,
        "contentType": mime,
        "contentBase64": base64.b64encode(content).decode("ascii"),
    }
