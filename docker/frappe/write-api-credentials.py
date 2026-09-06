#!/usr/bin/env python3
"""Generate Administrator API keys and write them for the Next.js BFF."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", default=os.environ.get("SITE_NAME", "vendors.localhost"))
    parser.add_argument(
        "--path",
        default=os.environ.get("CREDENTIALS_FILE", "/shared/credentials.json"),
    )
    args = parser.parse_args()

    bench_path = Path("/home/frappe/frappe-bench")
    sites_path = bench_path / "sites"
    os.chdir(bench_path)

    site_dir = sites_path / args.site
    if not site_dir.is_dir():
        available = [p.name for p in sites_path.iterdir() if p.is_dir() and p.name != "assets"]
        raise SystemExit(
            f"Site directory missing: {site_dir}. Available under sites/: {available}"
        )

    import frappe
    from frappe.core.doctype.user.user import generate_keys

    frappe.init(site=args.site, sites_path=str(sites_path))
    frappe.connect()
    frappe.set_user("Administrator")
    try:
        result = generate_keys("Administrator")
        frappe.db.commit()
        payload = {
            "FRAPPE_API_KEY": result["api_key"],
            "FRAPPE_API_SECRET": result["api_secret"],
            "FRAPPE_SITE_NAME": args.site,
            "FRAPPE_URL": os.environ.get("FRAPPE_INTERNAL_URL", "http://backend:8000"),
        }
        out = Path(args.path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote API credentials to {out}")
    finally:
        frappe.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
