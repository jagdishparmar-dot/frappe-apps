frappe.listview_settings["VB Vendor Registration Request"] = {
	add_fields: ["status"],
	onload(listview) {
		const filters = listview.filter_area.get() || [];
		if (!filters.length) {
			listview.filter_area.add([[listview.doctype, "status", "=", "pending"]]);
		}
	},
	get_indicator(doc) {
		const map = { pending: "orange", approved: "green", rejected: "red" };
		return [__(doc.status), map[doc.status] || "gray", "status,=," + doc.status];
	},
};
