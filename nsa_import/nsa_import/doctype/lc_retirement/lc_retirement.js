// NSA Import - LC Retirement
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

frappe.ui.form.on("LC Retirement", {
	setup(frm) {
		frm.set_query("letter_of_credit", () => ({ filters: { docstatus: 1, status: ["not in", ["Retired", "Closed"]] } }));
		frm.set_query("import_shipment", () => ({ filters: { docstatus: 1, letter_of_credit: frm.doc.letter_of_credit } }));
		frm.set_query("paid_from_account", () => ({ filters: { company: frm.doc.company, is_group: 0 } }));
	},
	refresh(frm) {
		if (frm.doc.docstatus === 1 && !frm.doc.journal_entry) {
			frm.add_custom_button(__("Journal Entry"),
				() => nsa_make_je(frm, "nsa_import.api.make_retirement_journal_entry"), __("Create"));
		}
	},
	letter_of_credit(frm) {
		if (!frm.doc.letter_of_credit) return;
		frappe.call({ method: "nsa_import.api.get_retirement_defaults", args: { letter_of_credit: frm.doc.letter_of_credit } })
			.then((r) => nsa_set_if_empty(frm, r.message));
	},
	amount: (frm) => frm.trigger("calculate"),
	exchange_rate: (frm) => frm.trigger("calculate"),
	margin_adjusted: (frm) => frm.trigger("calculate"),
	bank_charges: (frm) => frm.trigger("calculate"),
	calculate(frm) {
		const base = flt(flt(frm.doc.amount) * flt(frm.doc.exchange_rate), 2);
		frm.set_value("base_amount", base);
		frm.set_value("net_bank_payment", flt(base - flt(frm.doc.margin_adjusted) + flt(frm.doc.bank_charges), 2));
	},
});
