// NSA Import - Purchase Receipt (GRN)
const nsa_import_grn_events = {
	refresh(frm) {
		if (frm.doc.docstatus === 1 && frm.doc.purchase_type === "Import") {
			frm.add_custom_button(__("Import Cost Sheet"), () =>
				frappe.model.open_mapped_doc({ method: "nsa_import.api.make_import_cost_sheet", frm }), __("Import"));
		}
		if (frm.doc.docstatus !== 1) return;
		// Inward Gate Pass (gate pass app) created from the GRN and linked back to it
		frappe.call({ method: "nsa_import.api.get_inward_gate_pass_info" }).then((r) => {
			const info = r.message || {};
			if (!info.exists) return;
			const make_igp = () => frappe.model.open_mapped_doc({ method: "nsa_import.api.make_inward_gate_pass", frm });
			frm.make_methods = Object.assign(frm.make_methods || {}, { "Inward Gate Pass": make_igp });
			if (info.can_create) frm.add_custom_button(__("Inward Gate Pass"), make_igp, __("Create"));
		});
	},
};
// "GRN" on sites where ERPNext's Purchase Receipt DocType was renamed
["Purchase Receipt", "GRN"].forEach((dt) => frappe.ui.form.on(dt, nsa_import_grn_events));
