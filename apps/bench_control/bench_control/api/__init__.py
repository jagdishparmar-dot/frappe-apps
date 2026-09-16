import json

import frappe
from frappe import _

from bench_control.api.auth import check_app_permission
from bench_control.services import bench_ops


def _guard():
	bench_ops.require_manager()


def _truthy(val) -> bool:
	return str(val).lower() in ("1", "true", "yes", "on")


@frappe.whitelist()
def overview():
	_guard()
	sites = bench_ops.list_sites(with_stats=True)
	apps = bench_ops.list_available_apps()
	status = bench_ops.get_bench_status()
	jobs = frappe.get_all(
		"Bench Job",
		fields=[
			"name",
			"operation",
			"site_name",
			"app_name",
			"status",
			"requested_by",
			"creation",
			"started_at",
			"finished_at",
			"error",
			"output",
		],
		order_by="creation desc",
		limit_page_length=50,
	)
	for job in jobs:
		out = job.get("output") or ""
		job["output_tail"] = out[-2000:] if out else ""
		job["has_output"] = bool(out)
		job.pop("output", None)
	return {
		"current_site": frappe.local.site,
		"sites": sites,
		"available_apps": apps,
		"jobs": jobs,
		"can_manage": check_app_permission(),
		"bench": status,
	}


@frappe.whitelist()
def list_sites():
	_guard()
	return bench_ops.list_sites(with_stats=True)


@frappe.whitelist()
def list_apps():
	_guard()
	return bench_ops.list_available_apps()


@frappe.whitelist()
def get_site(site_name: str):
	_guard()
	return bench_ops.get_site_detail(site_name)


@frappe.whitelist()
def site_health(site_name: str):
	_guard()
	return bench_ops.check_site_health(site_name)


@frappe.whitelist()
def list_backups(site_name: str):
	_guard()
	return bench_ops.list_backups(site_name)


@frappe.whitelist()
def bench_status():
	_guard()
	return bench_ops.get_bench_status()


@frappe.whitelist()
def error_log(site_name: str | None = None, lines: int = 80):
	_guard()
	return bench_ops.get_error_log_tail(site_name or None, lines=lines)


@frappe.whitelist()
def get_job(job_id: str):
	_guard()
	job = frappe.get_doc("Bench Job", job_id)
	return job.as_dict()


def _parse_apps_arg(apps: str | list | None) -> list[str]:
	if apps is None or apps == "":
		return []
	if isinstance(apps, list):
		return [str(a).strip() for a in apps if str(a).strip()]
	raw = str(apps).strip()
	if not raw:
		return []
	if raw.startswith("["):
		try:
			parsed = json.loads(raw)
			if isinstance(parsed, list):
				return [str(a).strip() for a in parsed if str(a).strip()]
		except json.JSONDecodeError:
			raw = raw.strip("[]")
	return [a.strip().strip("\"'") for a in raw.replace(";", ",").split(",") if a.strip().strip("\"'")]


def _parse_sites_arg(sites: str | list | None) -> list[str]:
	return _parse_apps_arg(sites)


@frappe.whitelist()
def create_site(site_name: str, apps: str | list | None = None, admin_password: str | None = None, host_name: str | None = None):
	_guard()
	apps = _parse_apps_arg(apps)
	job_id = bench_ops.enqueue_job(
		"create_site",
		site_name,
		payload={
			"apps": apps,
			"admin_password": admin_password,
			"host_name": host_name,
		},
	)
	return {"job_id": job_id}


@frappe.whitelist()
def install_app(site_name: str, app_name: str):
	_guard()
	job_id = bench_ops.enqueue_job("install_app", site_name, app_name=app_name)
	return {"job_id": job_id}


@frappe.whitelist()
def install_app_multi(app_name: str, sites: str | list | None = None):
	_guard()
	site_list = _parse_sites_arg(sites)
	if not site_list:
		frappe.throw(_("Select at least one site"))
	job_id = bench_ops.enqueue_job(
		"install_app_multi",
		"all",
		app_name=app_name,
		payload={"sites": site_list},
	)
	return {"job_id": job_id}


@frappe.whitelist()
def uninstall_app(site_name: str, app_name: str):
	_guard()
	job_id = bench_ops.enqueue_job("uninstall_app", site_name, app_name=app_name)
	return {"job_id": job_id}


@frappe.whitelist()
def migrate_site(site_name: str, backup_first: int | str | bool = 0):
	_guard()
	job_id = bench_ops.enqueue_job(
		"migrate",
		site_name,
		payload={"backup_first": _truthy(backup_first)},
	)
	return {"job_id": job_id}


@frappe.whitelist()
def migrate_all(sites: str | list | None = None):
	_guard()
	site_list = _parse_sites_arg(sites)
	job_id = bench_ops.enqueue_job(
		"migrate_all",
		"all",
		payload={"sites": site_list or None},
	)
	return {"job_id": job_id}


@frappe.whitelist()
def drop_site(site_name: str, confirm: int | str | bool = 0, backup_first: int | str | bool = 1):
	_guard()
	if not _truthy(confirm):
		frappe.throw(_("Pass confirm=1 to drop a site"))
	job_id = bench_ops.enqueue_job(
		"drop_site",
		site_name,
		payload={"confirm": True, "backup_first": _truthy(backup_first)},
	)
	return {"job_id": job_id}


@frappe.whitelist()
def set_host_name(site_name: str, host_name: str | None = None):
	_guard()
	job_id = bench_ops.enqueue_job("set_host_name", site_name, payload={"host_name": host_name or ""})
	return {"job_id": job_id}


@frappe.whitelist()
def backup_site(site_name: str, with_files: int | str | bool = 1):
	_guard()
	job_id = bench_ops.enqueue_job(
		"backup",
		site_name,
		payload={"with_files": _truthy(with_files)},
	)
	return {"job_id": job_id}


@frappe.whitelist()
def restore_site(site_name: str, backup_path: str, allow_current: int | str | bool = 0):
	_guard()
	job_id = bench_ops.enqueue_job(
		"restore",
		site_name,
		payload={
			"backup_path": backup_path,
			"allow_current": _truthy(allow_current),
		},
	)
	return {"job_id": job_id}


@frappe.whitelist()
def clear_cache(site_name: str):
	_guard()
	job_id = bench_ops.enqueue_job("clear_cache", site_name)
	return {"job_id": job_id}


@frappe.whitelist()
def set_maintenance(site_name: str, enabled: int | str | bool = 0):
	_guard()
	job_id = bench_ops.enqueue_job(
		"set_maintenance",
		site_name,
		payload={"enabled": _truthy(enabled)},
	)
	return {"job_id": job_id}


@frappe.whitelist()
def reset_admin_password(site_name: str, password: str):
	_guard()
	job_id = bench_ops.enqueue_job(
		"reset_admin_password",
		site_name,
		payload={"password": password},
	)
	return {"job_id": job_id}


@frappe.whitelist()
def rename_site(site_name: str, new_name: str):
	_guard()
	job_id = bench_ops.enqueue_job(
		"rename_site",
		site_name,
		payload={"new_name": new_name},
	)
	return {"job_id": job_id}


@frappe.whitelist()
def clone_site(site_name: str, new_name: str, admin_password: str | None = None):
	_guard()
	job_id = bench_ops.enqueue_job(
		"clone_site",
		site_name,
		payload={"new_name": new_name, "admin_password": admin_password},
	)
	return {"job_id": job_id}


@frappe.whitelist()
def set_default_site(site_name: str):
	_guard()
	job_id = bench_ops.enqueue_job("set_default_site", site_name)
	return {"job_id": job_id}


@frappe.whitelist()
def set_site_config(site_name: str, config: str | dict | None = None):
	_guard()
	if isinstance(config, str):
		raw = config.strip()
		if not raw:
			config = {}
		else:
			try:
				config = json.loads(raw)
			except json.JSONDecodeError:
				# Tolerate single-quoted payloads from some clients
				config = json.loads(raw.replace("'", '"'))
	if not isinstance(config, dict):
		frappe.throw(_("config must be a JSON object"))
	job_id = bench_ops.enqueue_job(
		"set_site_config",
		site_name,
		payload={"config": config},
	)
	return {"job_id": job_id}
