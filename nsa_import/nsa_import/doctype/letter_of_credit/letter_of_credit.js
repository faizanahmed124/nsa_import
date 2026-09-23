// NSA Import - Letter of Credit
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

frappe.ui.form.on("Letter of Credit", {
	setup(frm) {
		frm.set_query("purchase_order", () => ({ filters: { docstatus: 1, purchase_type: "Import" } }));
		frm.set_query("bank_gl_account", () => ({ filters: { company: frm.doc.company, is_group: 0, account_type: "Bank" } }));
		frm.set_query("account", "charges", () => ({ filters: { company: frm.doc.company, is_group: 0 } }));
	},
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;
		const open = (method) => frappe.model.open_mapped_doc({ method, frm });
		if (!["Retired", "Closed", "Expired"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Import Shipment"), () => open("nsa_import.api.make_import_shipment_from_lc"), __("Create"));
		}
		if (!["Retired", "Closed"].includes(frm.doc.status)) {
			frm.add_custom_button(__("LC Retirement"), () => open("nsa_import.api.make_lc_retirement"), __("Create"));
		}
		if (!frm.doc.journal_entry && (flt(frm.doc.margin_amount) || flt(frm.doc.total_charges))) {
			frm.add_custom_button(__("Margin / Charges Journal Entry"),
				() => nsa_make_je(frm, "nsa_import.api.make_lc_journal_entry"), __("Create"));
		}
		if (["Fully Shipped", "Retired", "Partially Retired", "Expired"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Close LC"), () =>
				frappe.confirm(__("Close this Letter of Credit?"), () =>
					frappe.call({ method: "nsa_import.api.close_letter_of_credit", args: { name: frm.doc.name } })
						.then(() => frm.reload_doc())));
		}
		frm.dashboard.add_indicator(__("Balance: {0}", [format_currency(frm.doc.balance_amount, frm.doc.currency)]),
			flt(frm.doc.balance_amount) > 0 ? "orange" : "green");
	},
	purchase_order(frm) {
		if (!frm.doc.purchase_order) return;
		frappe.call({ method: "nsa_import.api.get_lc_defaults", args: { purchase_order: frm.doc.purchase_order } })
			.then((r) => nsa_set_if_empty(frm, r.message));
	},
	margin_percent(frm) {
		const base = flt(frm.doc.lc_amount) * flt(frm.doc.exchange_rate);
		frm.set_value("margin_amount", flt(base * flt(frm.doc.margin_percent) / 100, 2));
	},
});
