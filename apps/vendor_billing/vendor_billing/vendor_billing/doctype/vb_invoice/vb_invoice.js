frappe.ui.form.on("VB Invoice", {
	refresh(frm) {
		if (frm.is_new()) return;

		if (frm.doc.docstatus === 0) {
			frm.dashboard.set_headline(
				__("Draft — the vendor can still edit this invoice. Submit to lock it for AP review.")
			);
		}

		const frozen = frm.doc.status === "Paid" || frm.doc.payment_status === "paid";
		if (frm.doc.docstatus === 1 && frm.has_perm("write") && !frm.doc.archived && !frozen) {
			frm.add_custom_button(__("Update Status / Payment"), () => show_payment_dialog(frm), __("Review"));
			frm.add_custom_button(
				__("Return to Vendor"),
				() => {
					frappe.prompt(
						{ fieldtype: "Small Text", fieldname: "remarks", label: __("Remarks"), reqd: 1 },
						(values) => {
							frappe.call({
								method: "vendor_billing.desk.return_invoice_to_vendor",
								args: { invoice: frm.doc.name, remarks: values.remarks },
								callback(r) {
									const amended = r.message && r.message.amended_invoice;
									frappe.show_alert({
										message: amended
											? __("Draft {0} opened for the vendor", [amended])
											: __("Invoice returned to the vendor"),
										indicator: "orange",
									});
									frm.reload_doc();
								},
							});
						},
						__("Return invoice to vendor")
					);
				},
				__("Review")
			);
		}
		if (frm.doc.docstatus === 1 && frozen) {
			frm.dashboard.set_headline(__("Paid invoices are frozen. Correction requires a credit or debit note."));
		}
		if (frm.doc.docstatus === 2) {
			frm.dashboard.set_headline(__("Cancelled. The vendor may upload a new invoice if AP asked them to."));
		}

		frm.add_custom_button(
			__("Payment Challan"),
			() => open_print(frm, "VB Payment Challan"),
			__("Print")
		);
		frm.add_custom_button(__("Invoice"), () => open_print(frm, "VB Invoice"), __("Print"));

		if (frm.doc.docstatus === 1 && !frm.doc.archived && frm.has_perm("write")) {
			frm.add_custom_button(__("Archive"), () => {
				frappe.prompt(
					{ fieldtype: "Small Text", fieldname: "remarks", label: __("Remarks"), reqd: 1 },
					(values) => {
						frappe.call({
							method: "vendor_billing.desk.archive_doc",
							args: { doctype: "VB Invoice", name: frm.doc.name, remarks: values.remarks },
							callback() {
								frm.reload_doc();
							},
						});
					},
					__("Archive invoice")
				);
			});
		} else if (frm.doc.archived && frm.has_perm("write")) {
			frm.add_custom_button(__("Restore"), () => {
				frappe.call({
					method: "vendor_billing.desk.restore_doc",
					args: { doctype: "VB Invoice", name: frm.doc.name },
					callback() {
						frm.reload_doc();
					},
				});
			});
		}
	},
});

function open_print(frm, format) {
	const url =
		"/printview?doctype=" +
		encodeURIComponent(frm.doctype) +
		"&name=" +
		encodeURIComponent(frm.doc.name) +
		"&format=" +
		encodeURIComponent(format) +
		"&no_letterhead=1";
	window.open(url, "_blank");
}

function show_payment_dialog(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Invoice status and payment"),
		fields: [
			{
				fieldname: "status",
				fieldtype: "Select",
				label: __("Status"),
				options: "Pending\nPaid\nHold\nRejected",
				default: frm.doc.status,
				reqd: 1,
			},
			{
				fieldname: "payment_status",
				fieldtype: "Select",
				label: __("Payment Status"),
				options: "none\napproved\nscheduled\npaid",
				default: frm.doc.payment_status || "none",
			},
			{
				fieldname: "scheduled_pay_date",
				fieldtype: "Date",
				label: __("Scheduled Pay Date"),
				default: frm.doc.scheduled_pay_date,
			},
			{
				fieldname: "paid_date",
				fieldtype: "Date",
				label: __("Paid Date"),
				default: frm.doc.paid_date,
			},
			{
				fieldname: "payment_reference",
				fieldtype: "Data",
				label: __("UTR / Reference"),
				default: frm.doc.payment_reference,
			},
			{
				fieldname: "payment_remarks",
				fieldtype: "Small Text",
				label: __("Payment Remarks"),
				default: frm.doc.payment_remarks,
			},
			{
				fieldname: "remarks",
				fieldtype: "Small Text",
				label: __("Remarks"),
				default: frm.doc.remarks,
			},
		],
		primary_action_label: __("Save"),
		primary_action(values) {
			frappe.call({
				method: "vendor_billing.desk.apply_invoice_status",
				args: { invoice: frm.doc.name, ...values },
				callback() {
					d.hide();
					frm.reload_doc();
					frappe.show_alert({ message: __("Invoice updated"), indicator: "green" });
				},
			});
		},
	});
	d.show();
}
