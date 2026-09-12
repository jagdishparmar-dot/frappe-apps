"""S3-compatible File adapter (AWS / MinIO / RustFS / R2).

Configure Desk → VB File Storage Settings, or site_config.json keys:
  s3_endpoint, s3_region, s3_bucket, s3_access_key_id, s3_secret_access_key,
  s3_force_path_style, s3_folder_prefix
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote, unquote

import frappe

S3_SCHEME = "/api/method/vendor_billing.storage.download?key="


def _settings():
    if frappe.db.exists("DocType", "VB File Storage Settings"):
        try:
            return frappe.get_single("VB File Storage Settings")
        except Exception:
            return None
    return None


def is_enabled() -> bool:
    s = _settings()
    if s and s.enabled and s.bucket and s.access_key_id:
        return True
    conf = frappe.conf
    return bool(conf.get("s3_bucket") and conf.get("s3_access_key_id"))


def _client_kwargs() -> dict:
    s = _settings()
    conf = frappe.conf
    endpoint = (s.endpoint if s else None) or conf.get("s3_endpoint")
    region = (s.region if s else None) or conf.get("s3_region") or "us-east-1"
    key = (s.access_key_id if s else None) or conf.get("s3_access_key_id")
    secret = (s.secret_access_key if s else None) or conf.get("s3_secret_access_key")
    path_style = True
    if s:
        path_style = bool(s.force_path_style)
    elif conf.get("s3_force_path_style") in (0, "0", False, "false"):
        path_style = False
    kwargs = {
        "service_name": "s3",
        "region_name": region,
        "aws_access_key_id": key,
        "aws_secret_access_key": secret,
    }
    if endpoint:
        kwargs["endpoint_url"] = str(endpoint).rstrip("/")
    return kwargs, path_style


def _bucket() -> str:
    s = _settings()
    return (s.bucket if s else None) or frappe.conf.get("s3_bucket") or frappe.conf.get("s3_bucket_name")


def _prefix() -> str:
    s = _settings()
    raw = (s.folder_prefix if s else None) or frappe.conf.get("s3_folder_prefix") or ""
    return str(raw).strip("/")


def get_client():
    import boto3
    from botocore.config import Config

    kwargs, path_style = _client_kwargs()
    return boto3.client(
        **kwargs,
        config=Config(s3={"addressing_style": "path" if path_style else "auto"}),
    )


def object_key(file_name: str, folder: str | None = None) -> str:
    parts = [p for p in (_prefix(), folder, file_name) if p]
    return "/".join(parts)


def upload_bytes(key: str, content: bytes, content_type: str | None = None) -> str:
    extra = {}
    if content_type:
        extra["ContentType"] = content_type
    get_client().put_object(Bucket=_bucket(), Key=key, Body=content, **extra)
    return key


def delete_key(key: str) -> None:
    get_client().delete_object(Bucket=_bucket(), Key=key)


def signed_url(key: str, expires: int = 300) -> str:
    return get_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": _bucket(), "Key": key},
        ExpiresIn=expires,
    )


def get_object_bytes(key: str) -> bytes:
    obj = get_client().get_object(Bucket=_bucket(), Key=key)
    return obj["Body"].read()


def file_after_insert(doc, method=None):
    if not is_enabled():
        return
    if doc.is_folder or not doc.file_url:
        return
    if "vendor_billing.storage.download" in (doc.file_url or ""):
        return
    if (doc.file_url or "").startswith("http"):
        return
    site_path = Path(frappe.get_site_path())
    rel = (doc.file_url or "").lstrip("/")
    local = site_path / rel
    if not local.is_file():
        public = site_path / "public" / rel
        local = public if public.is_file() else local
    if not local.is_file():
        return
    key = object_key(doc.file_name or local.name, folder=doc.attached_to_doctype)
    upload_bytes(key, local.read_bytes(), content_type=doc.content_type)
    doc.db_set("file_url", f"{S3_SCHEME}{quote(key, safe='')}", update_modified=False)


def file_on_trash(doc, method=None):
    if not is_enabled():
        return
    url = doc.file_url or ""
    if "key=" not in url:
        return
    key = unquote(url.split("key=", 1)[-1])
    try:
        delete_key(key)
    except Exception:
        frappe.log_error(title="S3 delete failed")


@frappe.whitelist(allow_guest=True)
def download(key: str | None = None):
    """Stream or redirect an S3 object. Portal methods should prefer signed URLs."""
    if not key:
        frappe.throw("key is required")
    # Guest download is only for Desk session or portal session via other methods.
    if frappe.session.user == "Guest":
        frappe.throw("Not permitted", frappe.PermissionError)
    url = signed_url(key)
    frappe.local.response["type"] = "redirect"
    frappe.local.response["location"] = url
