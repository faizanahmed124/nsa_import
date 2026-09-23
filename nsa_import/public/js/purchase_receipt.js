// NSA Import - Purchase Receipt
frappe.ui.form.on("Purchase Receipt", {
	refresh(frm) {
		if (frm.doc.docstatus === 1 && frm.doc.purchase_type === "Import") {
			frm.add_custom_button(__("Import Cost Sheet"), () =>
				frappe.model.open_mapped_doc({ method: "nsa_import.api.make_import_cost_sheet", frm }), __("Import"));
		}
	},
});
