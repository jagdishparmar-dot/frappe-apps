frappe.listview_settings["VB Vendor KYC"] = {
	add_fields: ["kyc_status", "vendor"],
	onload(listview) {
		const filters = listview.filter_area.get() || [];
		if (!filters.length) {
			listview.filter_area.add([[listview.doctype, "kyc_status", "=", "pending_verification"]]);
		}
	},
	get_indicator(doc) {
		const map = {
			pending_submission: "gray",
			pending_verification: "orange",
			verified: "green",
			rejected: "red",
		};
		return [__(doc.kyc_status), map[doc.kyc_status] || "gray", "kyc_status,=," + doc.kyc_status];
	},
};
