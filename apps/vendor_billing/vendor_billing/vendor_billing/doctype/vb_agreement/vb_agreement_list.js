frappe.listview_settings["VB Agreement"] = {
	add_fields: ["status", "archived", "end_date", "docstatus"],
	onload(listview) {
		const filters = listview.filter_area.get() || [];
		const has_archived = filters.some((row) => row[1] === "archived");
		if (!has_archived) {
			listview.filter_area.add([[listview.doctype, "archived", "=", 0]]);
		}
	},
	get_indicator(doc) {
		if (cint(doc.archived)) {
			return [__("Archived"), "gray", "archived,=,1"];
		}
		if (cint(doc.docstatus) === 0) {
			return [__("Draft"), "gray", "docstatus,=,0"];
		}
		if (cint(doc.docstatus) === 2) {
			return [__("Cancelled"), "red", "docstatus,=,2"];
		}
		const map = {
			Active: "green",
			"Expiring Soon": "orange",
			Expired: "red",
			Terminated: "gray",
		};
		return [__(doc.status), map[doc.status] || "gray", "status,=," + doc.status];
	},
};
