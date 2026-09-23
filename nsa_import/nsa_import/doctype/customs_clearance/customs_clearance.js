// NSA Import - Customs Clearance (Goods Declaration)
function nsa_make_je(frm, method) {
	frappe.call({
		method,
		args: { source_name: frm.doc.name },
		freeze: true,
		callback(r) {
			if (r.message) {
				frm.reload_doc();
				frappe.set_route("Form", "Journal Entry", r.message);
			}
		},
	});
}

function nsa_set_if_empty(frm, values) {
	Object.entries(values || {}).forEach(([k, v]) => {
		if (v !== null && v !== undefined && v !== "" && !frm.doc[k] && frm.fields_dict[k]) frm.set_value(k, v);
	});
}

frappe.ui.form.on("Customs Clearance", {
	setup(frm) {
		frm.set_query("import_shipment", () => ({ filters: { docstatus: 1, status: ["in", ["In Transit", "Arrived"]] } }));
		frm.set_query("paid_through", () => ({ filters: { company: frm.doc.company, is_group: 0, account_type: ["in", ["Bank", "Cash"]] } }));
	},
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;
		frm.add_custom_button(__("Purchase Receipt"),
			() => frappe.model.open_mapped_doc({ method: "nsa_import.api.make_purchase_receipt_from_clearance", frm }), __("Create"));
		if (!frm.doc.journal_entry && flt(frm.doc.total_duties_and_taxes)) {
			frm.add_custom_button(__("Duty Payment Journal Entry"),
				() => nsa_make_je(frm, "nsa_import.api.make_duty_journal_entry"), __("Create"));
		}
	},
	import_shipment(frm) {
		if (!frm.doc.import_shipment) return;
		frappe.call({ method: "nsa_import.api.get_clearance_defaults", args: { import_shipment: frm.doc.import_shipment }, freeze: true })
			.then((r) => {
				const data = r.message || {};
				nsa_set_if_empty(frm, data.header);
				frm.clear_table("items");
				(data.items || []).forEach((row) => frm.add_child("items", row));
				frm.refresh_field("items");
			});
	},
});

frappe.ui.form.on("Customs Clearance Item", {
	hs_code(frm, cdt, cdn) {
		const d = locals[cdt][cdn];
		if (!d.hs_code) return;
		frappe.call({ method: "nsa_import.api.get_hs_duty_rates", args: { hs_code: d.hs_code } }).then((r) => {
			Object.entries(r.message || {}).forEach(([k, v]) => frappe.model.set_value(cdt, cdn, k, v));
		});
	},
});
