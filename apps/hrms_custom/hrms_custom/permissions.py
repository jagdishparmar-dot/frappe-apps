import frappe

HR_ROLES = ("System Manager", "HR Admin", "HR Executive")

# Desk documents an Employee-role user may open, limited to their own employee id.
EMPLOYEE_SCOPED_DOCTYPES = (
	"Employee",
	"Leave Application",
	"Leave Allocation",
	"Attendance Regularization",
	"Profile Update Request",
	"Shift Assignment",
	"Shift Roster",
)


def is_hr(user: str | None = None) -> bool:
	user = user or frappe.session.user
	return user == "Administrator" or bool(set(HR_ROLES) & set(frappe.get_roles(user)))


def employee_permission_query(user, doctype=None):
	"""Hide other people's rows from a desk login that is not HR."""
	if not doctype or is_hr(user):
		return None
	employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
	if not employee:
		return "1=0"
	column = "name" if doctype == "Employee" else "employee"
	return f"`tab{doctype}`.{column} = {frappe.db.escape(employee)}"


def employee_has_permission(doc, ptype=None, user=None, debug=False):
	"""Block opening or saving another employee's document from Desk."""
	if is_hr(user):
		return True
	user = user or frappe.session.user
	employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
	if not employee:
		return False
	value = doc.name if doc.doctype == "Employee" else doc.get("employee")
	if not value and getattr(doc, "is_new", lambda: False)():
		return True
	return value == employee
