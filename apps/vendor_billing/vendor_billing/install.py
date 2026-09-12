"""Create staff roles, seed billing categories, and singleton defaults."""

from __future__ import annotations

import os

import frappe

ROLES = [
    {"role_name": "VB Admin", "desk_access": 1},
    {"role_name": "VB AP Operator", "desk_access": 1},
    {"role_name": "VB Vendor Manager", "desk_access": 1},
    {"role_name": "VB Hub Master", "desk_access": 1},
    {"role_name": "VB Auditor", "desk_access": 1},
    {"role_name": "VB Viewer", "desk_access": 1},
    {"role_name": "VB Portal Gateway", "desk_access": 0},
]

DEFAULT_CATEGORIES = [
    "Rent",
    "Manpower",
    "Vehicle Rent",
    "Repairs & Maintenance",
    "Electricity",
    "Others",
]


def after_install() -> None:
    ensure_roles()
    seed_categories()
    ensure_singles()


def after_migrate() -> None:
    ensure_roles()
    seed_categories()
    ensure_desk_navigation()


def ensure_roles() -> None:
    for spec in ROLES:
        name = spec["role_name"]
        if frappe.db.exists("Role", name):
            continue
        frappe.get_doc(
            {
                "doctype": "Role",
                "role_name": name,
                "desk_access": spec["desk_access"],
                "is_custom": 1,
            }
        ).insert(ignore_permissions=True)
    frappe.db.commit()


def seed_categories() -> None:
    if not frappe.db.exists("DocType", "VB Billing Category"):
        return
    for name in DEFAULT_CATEGORIES:
        if frappe.db.exists("VB Billing Category", name):
            continue
        frappe.get_doc({"doctype": "VB Billing Category", "category_name": name}).insert(ignore_permissions=True)
    frappe.db.commit()


def ensure_desk_navigation() -> None:
    """Install the Desk launcher and grouped sidebar even if an auto-generated sidebar already exists."""
    from frappe.modules.import_file import import_file_by_path

    for rel in ("workspace_sidebar/vendor_billing.json", "desktop_icon/vendor_billing.json"):
        path = frappe.get_app_path("vendor_billing", *rel.split("/"))
        if os.path.exists(path):
            import_file_by_path(path, force=True, ignore_version=True)

    _pin_launcher_on_layouts()
    frappe.clear_cache()
    frappe.cache.delete_key("desktop_icons")
    frappe.cache.delete_key("bootinfo")
    frappe.db.commit()


def _pin_launcher_on_layouts() -> None:
    """Saved Desktop Layouts hide new launchers until they are merged in."""
    if not frappe.db.exists("Desktop Icon", "Vendor Billing"):
        return
    icon = frappe.get_doc("Desktop Icon", "Vendor Billing")
    tile = {
        "label": icon.label,
        "icon": icon.icon,
        "icon_type": icon.icon_type,
        "link_type": icon.link_type,
        "link_to": icon.link_to,
        "logo_url": icon.logo_url,
        "app": icon.app,
        "standard": 1,
        "hidden": 0,
        "parent_icon": None,
    }
    if not frappe.db.exists("DocType", "Desktop Layout"):
        return
    for name in frappe.get_all("Desktop Layout", pluck="name"):
        doc = frappe.get_doc("Desktop Layout", name)
        if not doc.layout:
            continue
        layout = frappe.parse_json(doc.layout)
        if not isinstance(layout, list):
            continue
        if any((item or {}).get("label") == "Vendor Billing" for item in layout):
            continue
        layout.insert(0, tile)
        doc.layout = frappe.as_json(layout)
        doc.save(ignore_permissions=True)


def ensure_singles() -> None:
    for dt in ("VB Company Profile", "VB Notification Settings", "VB File Storage Settings"):
        if not frappe.db.exists("DocType", dt):
            continue
        try:
            frappe.get_single(dt)
        except Exception:
            pass
