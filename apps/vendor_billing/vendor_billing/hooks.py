app_name = "vendor_billing"
app_title = "Vendor Billing"
app_publisher = "Coldverse"
app_description = (
    "Vendor billing admin on Frappe Desk v16. "
    "The vendor-facing OTP portal is a separate Next.js app."
)
app_email = "vms@intoship.cloud"
app_license = "mit"
app_version = "0.0.1"
app_logo_url = "/assets/vendor_billing/images/vendor-billing.svg"
app_home = "/desk/vendor-billing"

required_apps = ["frappe"]  # Framework v16 only; do not add erpnext

add_to_apps_screen = [
    {
        "name": "vendor_billing",
        "logo": "/assets/vendor_billing/images/vendor-billing.svg",
        "title": "Vendor Billing",
        "route": "/desk/vendor-billing",
        "has_permission": "vendor_billing.permissions.check_app_permission",
    }
]

after_install = "vendor_billing.install.after_install"
after_migrate = "vendor_billing.install.after_migrate"

doc_events = {
    "File": {
        "after_insert": "vendor_billing.storage.file_after_insert",
        "on_trash": "vendor_billing.storage.file_on_trash",
    }
}

scheduler_events = {
    "hourly": [
        "vendor_billing.tasks.purge_expired_portal_auth",
    ],
    "daily": [
        "vendor_billing.tasks.refresh_agreement_statuses",
    ],
}
