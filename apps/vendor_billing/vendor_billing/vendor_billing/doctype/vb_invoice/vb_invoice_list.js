frappe.listview_settings["VB Invoice"] = {
	add_fields: ["status", "payment_status", "archived", "amount", "docstatus"],
	hide_name_column: true,
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
			Pending: "orange",
			Paid: "green",
			Hold: "blue",
			Rejected: "red",
		};
		return [__(doc.status), map[doc.status] || "gray", "status,=," + doc.status];
	},
	button: {
		show(doc) {
			return (
				!cint(doc.archived) &&
				cint(doc.docstatus) === 1 &&
				doc.status !== "Paid" &&
				doc.payment_status !== "paid"
			);
		},
		get_label() {
			return __("Payment");
		},
		get_description() {
			return __("Update status and payment");
		},
		action(doc) {
			frappe.set_route("Form", "VB Invoice", doc.name);
		},
	},
};
