frappe.listview_settings["VB Vendor"] = {
	add_fields: ["status", "kyc_status", "archived"],
	hide_name_column: false,
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
		const map = {
			pending_submission: ["Pending KYC", "gray"],
			pending_verification: ["KYC Review", "orange"],
			verified: ["KYC Verified", "green"],
			rejected: ["KYC Rejected", "red"],
		};
		const row = map[doc.kyc_status] || [doc.kyc_status, "gray"];
		return [__(row[0]), row[1], "kyc_status,=," + doc.kyc_status];
	},
};
