"""Safe wrappers around bench CLI for site/app management."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

BENCH_DIR = Path(os.environ.get("BENCH_DIR", "/home/frappe/frappe-bench"))
SITE_NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$", re.I)
APP_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
PROTECTED_APPS = frozenset({"frappe"})
CONTROL_APP = "bench_control"
ALL_SITES_TOKEN = "__all__"

JOB_OPERATIONS = frozenset(
	{
		"create_site",
		"install_app",
		"install_app_multi",
		"uninstall_app",
		"migrate",
		"migrate_all",
		"drop_site",
		"set_host_name",
		"backup",
		"restore",
		"clear_cache",
		"set_maintenance",
		"reset_admin_password",
		"rename_site",
		"clone_site",
		"set_default_site",
		"set_site_config",
	}
)

SAFE_SITE_CONFIG_KEYS = frozenset(
	{
		"developer_mode",
		"allow_cors",
		"ignore_csrf",
		"mail_server",
		"mail_port",
		"host_name",
		"maintenance_mode",
	}
)

SITE_PRESETS = {
	"hr_only": {"label": "HR only", "apps": ["hr_portal"]},
	"vendor_hr": {"label": "Vendor + HR", "apps": ["vendor_billing", "hr_portal"]},
	"control": {"label": "Control plane", "apps": ["bench_control"]},
	"all_apps": {"label": "All product apps", "apps": None},
}


def require_manager():
	if frappe.session.user == "Guest":
		frappe.throw(_("Login required"), frappe.AuthenticationError)
	roles = set(frappe.get_roles())
	if "System Manager" not in roles and "Bench Manager" not in roles:
		frappe.throw(_("Bench Manager or System Manager role required"), frappe.PermissionError)


def validate_site_name(site: str, *, allow_all: bool = False) -> str:
	site = (site or "").strip().lower()
	if allow_all and site in {ALL_SITES_TOKEN, "*", "all"}:
		return ALL_SITES_TOKEN
	if not site or len(site) > 100 or not SITE_NAME_RE.match(site):
		frappe.throw(_("Invalid site name: {0}").format(site))
	if site in {"assets", "common_site_config.json", "apps.txt", "currentsite.txt"}:
		frappe.throw(_("Reserved site name"))
	return site


def validate_app_name(app: str) -> str:
	app = (app or "").strip()
	if not app or not APP_NAME_RE.match(app):
		frappe.throw(_("Invalid app name: {0}").format(app))
	if app in PROTECTED_APPS:
		frappe.throw(_("Cannot manage protected app: {0}").format(app))
	return app


def list_available_apps() -> list[str]:
	apps_dir = BENCH_DIR / "apps"
	if not apps_dir.is_dir():
		return []
	apps = []
	for path in sorted(apps_dir.iterdir()):
		if not path.is_dir():
			continue
		if path.name == "frappe":
			continue
		if (path / "pyproject.toml").is_file() or (path / path.name).is_dir():
			apps.append(path.name)
	return apps


def list_sites(*, with_stats: bool = False) -> list[dict]:
	sites_dir = BENCH_DIR / "sites"
	sites = []
	if not sites_dir.is_dir():
		return sites

	current = frappe.local.site
	for path in sorted(sites_dir.iterdir()):
		if not path.is_dir() or path.name.startswith(".") or path.name == "assets":
			continue
		if not (path / "site_config.json").is_file():
			continue
		site = path.name
		cfg = _read_site_config(site)
		row = {
			"name": site,
			"installed_apps": _read_installed_apps(site),
			"host_name": cfg.get("host_name"),
			"maintenance_mode": cint(cfg.get("maintenance_mode") or 0),
			"is_current": site == current,
			"healthy": True,
		}
		if with_stats:
			row.update(_site_stats(site))
		sites.append(row)
	return sites


def get_site_detail(site: str) -> dict:
	site = validate_site_name(site)
	path = BENCH_DIR / "sites" / site
	if not path.is_dir():
		frappe.throw(_("Site not found: {0}").format(site))

	cfg = _read_site_config(site)
	stats = _site_stats(site)
	health = check_site_health(site)
	detail = {
		"name": site,
		"installed_apps": _read_installed_apps(site),
		"host_name": cfg.get("host_name"),
		"maintenance_mode": cint(cfg.get("maintenance_mode") or 0),
		"developer_mode": cint(cfg.get("developer_mode") or 0),
		"allow_cors": cfg.get("allow_cors"),
		"ignore_csrf": cint(cfg.get("ignore_csrf") or 0),
		"mail_server": cfg.get("mail_server"),
		"mail_port": cfg.get("mail_port"),
		"db_name": cfg.get("db_name"),
		"is_current": site == frappe.local.site,
		"backups": list_backups(site),
		"health": health,
		**stats,
	}
	return enrich_site_detail(detail)



def check_site_health(site: str) -> dict:
	site = validate_site_name(site)
	path = BENCH_DIR / "sites" / site
	ok_files = path.is_dir() and (path / "site_config.json").is_file()
	db_ok = False
	db_error = None
	ping_ms = None

	if ok_files:
		import time

		start = time.time()
		result = _run(
			[
				"bench",
				"--site",
				site,
				"execute",
				"frappe.db.sql('select 1')",
			],
			check=False,
			timeout=30,
		)
		ping_ms = int((time.time() - start) * 1000)
		db_ok = result.returncode == 0
		if not db_ok:
			db_error = ((result.stderr or result.stdout) or "db check failed")[-500:]

	return {
		"files_ok": ok_files,
		"db_ok": db_ok,
		"db_error": db_error,
		"ping_ms": ping_ms,
		"ok": ok_files and db_ok,
	}


def list_backups(site: str) -> list[dict]:
	site = validate_site_name(site)
	backup_dir = BENCH_DIR / "sites" / site / "private" / "backups"
	items = []
	if not backup_dir.is_dir():
		return items
	for path in sorted(backup_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
		if not path.is_file():
			continue
		name = path.name.lower()
		if not (
			name.endswith((".sql.gz", ".sql", ".tar", ".tgz", ".json"))
			or "database" in name
			or "files" in name
		):
			continue
		stat = path.stat()
		items.append(
			{
				"name": path.name,
				"path": str(path.relative_to(BENCH_DIR / "sites" / site)),
				"size_bytes": stat.st_size,
				"size_human": _human_size(stat.st_size),
				"mtime": stat.st_mtime,
			}
		)
	return items[:40]


def _site_stats(site: str) -> dict:
	site_path = BENCH_DIR / "sites" / site
	files_bytes = _dir_size(site_path / "public") + _dir_size(site_path / "private")
	db_bytes = _db_size_bytes(site)
	return {
		"files_bytes": files_bytes,
		"files_human": _human_size(files_bytes),
		"db_bytes": db_bytes,
		"db_human": _human_size(db_bytes) if db_bytes is not None else None,
	}


def _dir_size(path: Path) -> int:
	if not path.exists():
		return 0
	total = 0
	for root, _dirs, files in os.walk(path):
		for name in files:
			try:
				total += (Path(root) / name).stat().st_size
			except OSError:
				continue
	return total


def _db_size_bytes(site: str) -> int | None:
	cfg = _read_site_config(site)
	db_name = cfg.get("db_name")
	if not db_name:
		return None
	db_host = os.environ.get("DB_HOST") or frappe.conf.db_host or "db"
	root_pw = _db_root_password()
	if not root_pw:
		return None
	sql = (
		"SELECT SUM(data_length + index_length) FROM information_schema.tables "
		f"WHERE table_schema = '{db_name.replace(chr(39), '')}'"
	)
	result = _run(
		["mysql", "-h", str(db_host), "-uroot", f"-p{root_pw}", "-N", "-e", sql],
		check=False,
		timeout=30,
	)
	if result.returncode != 0:
		return None
	raw = (result.stdout or "").strip()
	if not raw or raw.upper() == "NULL":
		return 0
	try:
		return int(float(raw))
	except ValueError:
		return None


def _human_size(n: int | None) -> str:
	if n is None:
		return "—"
	n = float(n)
	for unit in ("B", "KB", "MB", "GB", "TB"):
		if n < 1024 or unit == "TB":
			if unit == "B":
				return f"{int(n)} {unit}"
			return f"{n:.1f} {unit}"
		n /= 1024
	return f"{n:.1f} TB"


def _read_site_config(site: str) -> dict:
	path = BENCH_DIR / "sites" / site / "site_config.json"
	try:
		return json.loads(path.read_text(encoding="utf-8"))
	except (OSError, json.JSONDecodeError):
		return {}


def _read_installed_apps(site: str) -> list[str]:
	site_apps = BENCH_DIR / "sites" / site / "apps.txt"
	if site_apps.is_file():
		return [line.strip() for line in site_apps.read_text(encoding="utf-8").splitlines() if line.strip()]

	if site == frappe.local.site:
		try:
			return list(frappe.get_installed_apps())
		except Exception:
			pass

	result = _run(["bench", "--site", site, "list-apps"], check=False, timeout=90)
	if result.returncode != 0:
		return []
	apps = []
	for line in result.stdout.splitlines():
		line = line.strip()
		if not line or line.lower().startswith("app") or set(line) <= {"-", "="}:
			continue
		name = line.split()[0].strip()
		if name and name.lower() not in {"app", "apps"}:
			apps.append(name)
	return apps


def _db_root_password() -> str:
	return (
		os.environ.get("MYSQL_ROOT_PASSWORD")
		or os.environ.get("MARIADB_ROOT_PASSWORD")
		or os.environ.get("DB_ROOT_PASSWORD")
		or ""
	)


def _run(cmd: list[str], check: bool = True, timeout: int = 600) -> subprocess.CompletedProcess:
	env = os.environ.copy()
	env.setdefault("PATH", "/home/frappe/.local/bin:/usr/local/bin:/usr/bin:/bin")
	return subprocess.run(
		cmd,
		cwd=str(BENCH_DIR),
		capture_output=True,
		text=True,
		timeout=timeout,
		check=check,
		env=env,
	)


def enqueue_job(operation: str, site_name: str, app_name: str | None = None, payload: dict | None = None) -> str:
	require_manager()
	if operation not in JOB_OPERATIONS:
		frappe.throw(_("Unknown operation: {0}").format(operation))
	allow_all = operation in {"migrate_all", "install_app_multi"}
	site_name = validate_site_name(site_name, allow_all=allow_all)
	if app_name:
		app_name = validate_app_name(app_name)

	doc = frappe.get_doc(
		{
			"doctype": "Bench Job",
			"operation": operation,
			"site_name": site_name if site_name != ALL_SITES_TOKEN else "all",
			"app_name": app_name,
			"status": "Queued",
			"requested_by": frappe.session.user,
			"payload": json.dumps(payload or {}, indent=2),
		}
	)
	doc.insert(ignore_permissions=True)
	frappe.db.commit()

	sync = str(os.environ.get("BENCH_CONTROL_SYNC_JOBS", "")).lower() in ("1", "true", "yes")
	frappe.enqueue(
		"bench_control.services.bench_ops.run_job",
		job_name=f"bench_job:{doc.name}",
		queue="long",
		timeout=3600,
		bench_job_name=doc.name,
		now=sync or bool(frappe.conf.developer_mode),
		enqueue_after_commit=True,
	)
	return doc.name


def run_job(bench_job_name: str):
	"""RQ worker entrypoint."""
	job = frappe.get_doc("Bench Job", bench_job_name)
	if job.status not in ("Queued", "Failed"):
		return

	job.status = "Running"
	job.started_at = now_datetime()
	job.save(ignore_permissions=True)
	frappe.db.commit()

	try:
		output = _execute_operation(job)
		job.reload()
		job.status = "Success"
		job.output = (output or "")[-50000:]
		job.error = None
	except Exception as exc:
		job.reload()
		job.status = "Failed"
		job.error = frappe.get_traceback() or str(exc)
		job.output = getattr(exc, "output", None) or job.output
	finally:
		job.finished_at = now_datetime()
		job.save(ignore_permissions=True)
		frappe.db.commit()


def _execute_operation(job) -> str:
	op = job.operation
	payload = {}
	if job.payload:
		try:
			payload = json.loads(job.payload)
		except json.JSONDecodeError:
			payload = {}

	if op == "migrate_all":
		return _migrate_all(payload)
	if op == "install_app_multi":
		return _install_app_multi(validate_app_name(job.app_name), payload)

	site = validate_site_name(job.site_name)

	if op == "create_site":
		return _create_site(site, payload)
	if op == "install_app":
		return _install_app(site, validate_app_name(job.app_name))
	if op == "uninstall_app":
		return _uninstall_app(site, validate_app_name(job.app_name))
	if op == "migrate":
		if payload.get("backup_first"):
			_backup(site, {"with_files": False})
		return _migrate(site)
	if op == "drop_site":
		if payload.get("backup_first"):
			_backup(site, {"with_files": True})
		return _drop_site(site, payload)
	if op == "set_host_name":
		return _set_host_name(site, payload.get("host_name", ""))
	if op == "backup":
		return _backup(site, payload)
	if op == "restore":
		return _restore(site, payload)
	if op == "clear_cache":
		return _clear_cache(site)
	if op == "set_maintenance":
		return _set_maintenance(site, payload)
	if op == "reset_admin_password":
		return _reset_admin_password(site, payload)
	if op == "rename_site":
		return _rename_site(site, payload)
	if op == "clone_site":
		return _clone_site(site, payload)
	if op == "set_default_site":
		return _set_default_site(site)
	if op == "set_site_config":
		return _set_site_config(site, payload)
	frappe.throw(_("Unknown operation: {0}").format(op))


def _create_site(site: str, payload: dict) -> str:
	if (BENCH_DIR / "sites" / site).is_dir():
		frappe.throw(_("Site already exists: {0}").format(site))

	admin_password = payload.get("admin_password") or os.environ.get("ADMIN_PASSWORD") or "admin"
	apps = payload.get("apps") or []
	for app in apps:
		validate_app_name(app)
		if app not in list_available_apps():
			frappe.throw(_("App not available on this bench: {0}").format(app))

	db_password = _db_root_password()
	if not db_password:
		frappe.throw(_("MYSQL_ROOT_PASSWORD is not set in the container environment"))

	cmd = [
		"bench",
		"new-site",
		site,
		"--mariadb-user-host-login-scope=%",
		f"--admin-password={admin_password}",
		"--db-root-username=root",
		f"--db-root-password={db_password}",
	]
	for app in apps:
		cmd.extend(["--install-app", app])

	result = _run(cmd, check=False, timeout=1200)
	text = (result.stdout or "") + "\n" + (result.stderr or "")
	if result.returncode != 0:
		err = RuntimeError(text[-2000:] or f"bench new-site failed ({result.returncode})")
		err.output = text
		raise err

	host_name = payload.get("host_name")
	if host_name:
		_set_host_name(site, host_name)

	return text


def _install_app(site: str, app: str) -> str:
	if app not in list_available_apps():
		frappe.throw(_("App not available on this bench: {0}").format(app))
	result = _run(["bench", "--site", site, "install-app", app], check=False, timeout=900)
	text = (result.stdout or "") + "\n" + (result.stderr or "")
	if result.returncode != 0 and "already installed" not in text.lower():
		err = RuntimeError(text[-2000:] or "install-app failed")
		err.output = text
		raise err
	return text


def _uninstall_app(site: str, app: str) -> str:
	if app == CONTROL_APP and site == frappe.local.site:
		frappe.throw(_("Cannot uninstall bench_control from the site you are using"))
	result = _run(
		["bench", "--site", site, "uninstall-app", app, "--yes", "--no-backup"],
		check=False,
		timeout=900,
	)
	text = (result.stdout or "") + "\n" + (result.stderr or "")
	if result.returncode != 0:
		err = RuntimeError(text[-2000:] or "uninstall-app failed")
		err.output = text
		raise err
	return text


def _migrate(site: str) -> str:
	result = _run(["bench", "--site", site, "migrate"], check=False, timeout=1800)
	text = (result.stdout or "") + "\n" + (result.stderr or "")
	if result.returncode != 0:
		err = RuntimeError(text[-2000:] or "migrate failed")
		err.output = text
		raise err
	return text


def _migrate_all(payload: dict) -> str:
	sites = payload.get("sites") or [s["name"] for s in list_sites()]
	logs = []
	failed = []
	for site in sites:
		site = validate_site_name(site)
		logs.append(f"=== migrate {site} ===")
		try:
			logs.append(_migrate(site))
		except Exception as exc:
			failed.append(site)
			logs.append(str(getattr(exc, "output", None) or exc))
	text = "\n".join(logs)
	if failed:
		err = RuntimeError(f"Migrate failed for: {', '.join(failed)}")
		err.output = text
		raise err
	return text


def _drop_site(site: str, payload: dict) -> str:
	if site == frappe.local.site:
		frappe.throw(_("Cannot drop the site you are currently using"))
	if not payload.get("confirm"):
		frappe.throw(_("Drop site requires confirm=true"))

	db_password = _db_root_password()
	cmd = [
		"bench",
		"drop-site",
		site,
		"--force",
		"--no-backup",
		"--db-root-username=root",
	]
	if db_password:
		cmd.append(f"--db-root-password={db_password}")

	result = _run(cmd, check=False, timeout=600)
	text = (result.stdout or "") + "\n" + (result.stderr or "")
	if result.returncode != 0:
		err = RuntimeError(text[-2000:] or "drop-site failed")
		err.output = text
		raise err
	return text


def _set_host_name(site: str, host_name: str) -> str:
	host_name = (host_name or "").strip()
	if host_name and not re.match(r"^https?://[^/\s]+", host_name):
		frappe.throw(_("host_name must be a full URL, e.g. https://desk.example.com"))
	if not host_name:
		result = _run(["bench", "--site", site, "set-config", "-d", "host_name"], check=False)
	else:
		result = _run(["bench", "--site", site, "set-config", "host_name", host_name], check=False)
	text = (result.stdout or "") + "\n" + (result.stderr or "")
	if result.returncode != 0:
		err = RuntimeError(text[-2000:] or "set-config failed")
		err.output = text
		raise err
	return text or f"host_name={host_name}"


def _backup(site: str, payload: dict) -> str:
	cmd = ["bench", "--site", site, "backup"]
	if payload.get("with_files"):
		cmd.append("--with-files")
	result = _run(cmd, check=False, timeout=1800)
	text = (result.stdout or "") + "\n" + (result.stderr or "")
	if result.returncode != 0:
		err = RuntimeError(text[-2000:] or "backup failed")
		err.output = text
		raise err
	backups = list_backups(site)
	latest = backups[0]["name"] if backups else "(unknown)"
	return text + f"\nLatest backup artifact: {latest}"


def _restore(site: str, payload: dict) -> str:
	if site == frappe.local.site and not payload.get("allow_current"):
		frappe.throw(_("Refusing to restore onto the control site without allow_current=1"))
	rel = (payload.get("backup_path") or "").strip().replace("\\", "/")
	if not rel or ".." in rel.split("/"):
		frappe.throw(_("Invalid backup_path"))

	# Accept either private/backups/file or just filename
	if "/" not in rel:
		rel = f"private/backups/{rel}"
	full = (BENCH_DIR / "sites" / site / rel).resolve()
	backup_root = (BENCH_DIR / "sites" / site / "private" / "backups").resolve()
	if not str(full).startswith(str(backup_root)) or not full.is_file():
		frappe.throw(_("Backup file not found under site private/backups"))

	db_password = _db_root_password()
	cmd = [
		"bench",
		"--site",
		site,
		"restore",
		str(full),
		"--force",
	]
	if db_password:
		cmd.extend(["--db-root-password", db_password])

	result = _run(cmd, check=False, timeout=2400)
	text = (result.stdout or "") + "\n" + (result.stderr or "")
	if result.returncode != 0:
		err = RuntimeError(text[-2000:] or "restore failed")
		err.output = text
		raise err
	return text


def _clear_cache(site: str) -> str:
	result = _run(["bench", "--site", site, "clear-cache"], check=False, timeout=120)
	text = (result.stdout or "") + "\n" + (result.stderr or "")
	# also clear website cache
	result2 = _run(["bench", "--site", site, "clear-website-cache"], check=False, timeout=120)
	text += "\n" + (result2.stdout or "") + "\n" + (result2.stderr or "")
	if result.returncode != 0:
		err = RuntimeError(text[-2000:] or "clear-cache failed")
		err.output = text
		raise err
	return text


def _set_maintenance(site: str, payload: dict) -> str:
	enabled = payload.get("enabled")
	on = str(enabled).lower() in ("1", "true", "yes", "on")
	mode = "on" if on else "off"
	result = _run(["bench", "--site", site, "set-maintenance-mode", mode], check=False, timeout=60)
	text = (result.stdout or "") + "\n" + (result.stderr or "")
	if result.returncode != 0:
		# fallback to set-config
		result = _run(
			["bench", "--site", site, "set-config", "maintenance_mode", "1" if on else "0"],
			check=False,
			timeout=60,
		)
		text += "\n" + (result.stdout or "") + "\n" + (result.stderr or "")
		if result.returncode != 0:
			err = RuntimeError(text[-2000:] or "set-maintenance-mode failed")
			err.output = text
			raise err
	return text or f"maintenance_mode={mode}"


def _reset_admin_password(site: str, payload: dict) -> str:
	password = (payload.get("password") or "").strip()
	if len(password) < 4:
		frappe.throw(_("Password must be at least 4 characters"))
	result = _run(
		["bench", "--site", site, "set-admin-password", password],
		check=False,
		timeout=120,
	)
	text = (result.stdout or "") + "\n" + (result.stderr or "")
	if result.returncode != 0:
		err = RuntimeError(text[-2000:] or "set-admin-password failed")
		err.output = text
		raise err
	return "Administrator password updated"


def _install_app_multi(app: str, payload: dict) -> str:
	sites = payload.get("sites") or []
	if not sites:
		frappe.throw(_("No sites provided"))
	logs = []
	failed = []
	for site in sites:
		site = validate_site_name(site)
		logs.append(f"=== install {app} on {site} ===")
		try:
			logs.append(_install_app(site, app))
		except Exception as exc:
			failed.append(site)
			logs.append(str(getattr(exc, "output", None) or exc))
	text = "\n".join(logs)
	if failed:
		err = RuntimeError(f"Install failed on: {', '.join(failed)}")
		err.output = text
		raise err
	return text


def _rename_site(site: str, payload: dict) -> str:
	new_name = validate_site_name(payload.get("new_name") or "")
	if new_name == site:
		frappe.throw(_("New name must differ from current name"))
	if (BENCH_DIR / "sites" / new_name).exists():
		frappe.throw(_("Target site already exists: {0}").format(new_name))
	if site == frappe.local.site:
		frappe.throw(_("Cannot rename the site you are currently using"))
	result = _run(["bench", "rename-site", site, new_name], check=False, timeout=600)
	text = (result.stdout or "") + "\n" + (result.stderr or "")
	if result.returncode != 0:
		err = RuntimeError(text[-2000:] or "rename-site failed")
		err.output = text
		raise err
	return text


def _clone_site(site: str, payload: dict) -> str:
	new_name = validate_site_name(payload.get("new_name") or "")
	if (BENCH_DIR / "sites" / new_name).exists():
		frappe.throw(_("Target site already exists: {0}").format(new_name))
	admin_password = payload.get("admin_password") or os.environ.get("ADMIN_PASSWORD") or "admin"
	logs = []
	logs.append(_backup(site, {"with_files": True}))
	backups = list_backups(site)
	db_backup = next((b for b in backups if "database" in b["name"].lower() or b["name"].endswith((".sql.gz", ".sql"))), None)
	if not db_backup:
		frappe.throw(_("Could not find database backup after backup step"))
	logs.append(
		_create_site(
			new_name,
			{"admin_password": admin_password, "apps": []},
		)
	)
	logs.append(
		_restore(
			new_name,
			{"backup_path": db_backup["path"], "allow_current": True},
		)
	)
	return "\n".join(logs)


def _set_default_site(site: str) -> str:
	result = _run(["bench", "use", site], check=False, timeout=60)
	text = (result.stdout or "") + "\n" + (result.stderr or "")
	# Also write currentsite.txt for compatibility
	(BENCH_DIR / "sites" / "currentsite.txt").write_text(site + "\n", encoding="utf-8")
	if result.returncode != 0 and "does not exist" in text.lower():
		err = RuntimeError(text[-2000:] or "bench use failed")
		err.output = text
		raise err
	return text or f"default_site={site}"


def _set_site_config(site: str, payload: dict) -> str:
	updates = payload.get("config") or {}
	if not isinstance(updates, dict) or not updates:
		frappe.throw(_("config object required"))
	logs = []
	for key, value in updates.items():
		key = str(key).strip()
		if key not in SAFE_SITE_CONFIG_KEYS:
			frappe.throw(_("Config key not allowed: {0}").format(key))
		if value is None or value == "":
			result = _run(["bench", "--site", site, "set-config", "-d", key], check=False, timeout=60)
		else:
			result = _run(
				["bench", "--site", site, "set-config", key, str(value)],
				check=False,
				timeout=60,
			)
		text = (result.stdout or "") + "\n" + (result.stderr or "")
		logs.append(f"{key}={value}: {text.strip() or 'ok'}")
		if result.returncode != 0:
			err = RuntimeError(text[-2000:] or f"set-config {key} failed")
			err.output = "\n".join(logs)
			raise err
	return "\n".join(logs)


def get_default_site() -> str | None:
	path = BENCH_DIR / "sites" / "currentsite.txt"
	if path.is_file():
		return path.read_text(encoding="utf-8").strip() or None
	try:
		cfg = json.loads((BENCH_DIR / "sites" / "common_site_config.json").read_text(encoding="utf-8"))
		return cfg.get("default_site")
	except (OSError, json.JSONDecodeError):
		return None


def get_app_catalog() -> list[dict]:
	catalog = []
	routes = {
		"hr_portal": "/hr",
		"bench_control": "/control",
		"crm": "/crm",
		"vendor_billing": "/app",
	}
	for app in list_available_apps():
		version = "unknown"
		pyproject = BENCH_DIR / "apps" / app / "pyproject.toml"
		hooks = BENCH_DIR / "apps" / app / app / "hooks.py"
		if pyproject.is_file():
			text = pyproject.read_text(encoding="utf-8", errors="ignore")
			m = re.search(r'^version\s*=\s*["\']([^"\']+)["\']', text, re.M)
			if m:
				version = m.group(1)
			elif 'dynamic = ["version"]' in text or "dynamic = ['version']" in text:
				version = "0.0.1"
		if hooks.is_file():
			h = hooks.read_text(encoding="utf-8", errors="ignore")
			m = re.search(r'^app_version\s*=\s*["\']([^"\']+)["\']', h, re.M)
			if m:
				version = m.group(1)
		catalog.append(
			{
				"name": app,
				"version": version,
				"route": routes.get(app),
				"in_image": True,
			}
		)
	return catalog


def get_error_log_tail(site: str | None = None, lines: int = 80) -> dict:
	lines = max(10, min(int(lines or 80), 400))
	candidates = []
	if site:
		site = validate_site_name(site)
		candidates.extend(
			[
				BENCH_DIR / "sites" / site / "logs" / f"{site}.log",
				BENCH_DIR / "sites" / site / "logs" / "frappe.log",
			]
		)
	candidates.extend(
		[
			BENCH_DIR / "logs" / "bench.log",
			BENCH_DIR / "logs" / "worker.log",
			BENCH_DIR / "logs" / "web.log",
		]
	)
	for path in candidates:
		if path.is_file():
			content = path.read_text(encoding="utf-8", errors="replace").splitlines()
			tail = "\n".join(content[-lines:])
			return {"path": str(path.relative_to(BENCH_DIR)), "lines": lines, "content": tail}
	return {"path": None, "lines": lines, "content": "(no log files found)"}


def get_bench_status() -> dict:
	default_site = get_default_site()
	queue_stats = {}
	redis_url = None
	try:
		cfg = json.loads((BENCH_DIR / "sites" / "common_site_config.json").read_text(encoding="utf-8"))
		redis_url = cfg.get("redis_queue")
	except (OSError, json.JSONDecodeError):
		pass
	if redis_url:
		try:
			import redis

			client = redis.from_url(redis_url)
			for q in ("short", "default", "long"):
				try:
					queue_stats[q] = int(client.llen(f"frappe:queue:{q}") or 0)
				except Exception:
					queue_stats[q] = None
		except Exception:
			# redis package or server unavailable — leave depths empty
			queue_stats = {}
	return {
		"default_site": default_site,
		"queue_depth": queue_stats,
		"presets": [
			{"id": k, "label": v["label"], "apps": v["apps"] or list_available_apps()}
			for k, v in SITE_PRESETS.items()
		],
		"safe_config_keys": sorted(SAFE_SITE_CONFIG_KEYS),
		"app_catalog": get_app_catalog(),
	}



def enrich_site_detail(detail: dict) -> dict:
	"""Attach catalog versions for installed apps."""
	catalog = {a["name"]: a for a in get_app_catalog()}
	detail["app_details"] = [
		{
			"name": app,
			"version": catalog.get(app, {}).get("version", "—"),
			"route": catalog.get(app, {}).get("route"),
		}
		for app in detail.get("installed_apps") or []
	]
	detail["default_site"] = get_default_site()
	detail["is_default"] = detail.get("name") == detail.get("default_site")
	return detail
