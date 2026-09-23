// NSA Import - Import Cost Sheet (Landed Cost)
frappe.ui.form.on("Import Cost Sheet", {
	setup(frm) {
		frm.set_query("purchase_receipt", () => ({ filters: { docstatus: 1, purchase_type: "Import" } }));
		frm.set_query("expense_account", "charges", () => ({ filters: { company: frm.doc.company, is_group: 0 } }));
	},
	refresh(frm) {
		if (frm.doc.docstatus === 1 && !frm.doc.landed_cost_voucher) {
			frm.add_custom_button(__("Landed Cost Voucher"), () => {
				frappe.call({ method: "nsa_import.api.make_landed_cost_voucher", args: { source_name: frm.doc.name }, freeze: true })
					.then((r) => { frm.reload_doc(); if (r.message) frappe.set_route("Form", "Landed Cost Voucher", r.message); });
			}, __("Create"));
		}
		if (frm.doc.docstatus === 1 && frm.doc.landed_cost_voucher) {
			frm.add_custom_button(__("Open Landed Cost Voucher"),
				() => frappe.set_route("Form", "Landed Cost Voucher", frm.doc.landed_cost_voucher));
		}
	},
	purchase_receipt(frm) {
		if (frm.doc.purchase_receipt) frm.call("load_receipt");
	},
	get_charges(frm) {
		if (!frm.doc.purchase_receipt) {
			frappe.msgprint(__("Select Purchase Receipt first."));
			return;
		}
		frm.call("fetch_charges");
	},
});
