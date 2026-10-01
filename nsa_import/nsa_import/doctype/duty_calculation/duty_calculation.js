// NSA Import - Duty Calculation (mirrors the server formulas for live totals)
frappe.provide("nsa_import.dc");

nsa_import.dc.ON_IMPORT_VALUE = ["custom_duty", "acd", "regulatory_duty", "anti_dumping_duty"];
nsa_import.dc.SALES_TAXES = ["sales_tax", "additional_sales_tax"];
nsa_import.dc.ALL = nsa_import.dc.ON_IMPORT_VALUE.concat(nsa_import.dc.SALES_TAXES, ["income_tax"]);

nsa_import.dc.calc_row = function (frm, d) {
	const landing = flt((frm.__nsa || {}).landing_charges_percent);
	const set = (f, v) => (d[f] = v);
	set("foreign_currency_value", flt(flt(d.shipped_qty) * flt(d.rate), 2));
	const cf_fcy = flt(d.cf_value_fcy) || d.foreign_currency_value;
	const cf_pkr = flt(cf_fcy * flt(d.exchange_rate), 2);
	set("cf_value_pkr", cf_pkr);
	const insurance = flt(d.insurance_amount) || flt((cf_pkr * 1) / 100, 2);
	const cif = cf_pkr + flt(d.freight_amount) + insurance;
	set("landing_charges", flt((cif * landing) / 100, 2));
	set("dv_value", flt(cif + d.landing_charges, 2));
	set("import_value", Math.max(flt(d.dv_value), flt(d.scan_av_value)));
	const amount = (base, key) => {
		const v = flt((base * flt(d[`applied_${key}_rate`])) / 100, 2);
		set(`total_${key}`, v);
		return v;
	};
	const duties = nsa_import.dc.ON_IMPORT_VALUE.reduce((a, k) => a + amount(d.import_value, k), 0);
	const vst = d.import_value + duties;
	const taxes = nsa_import.dc.SALES_TAXES.reduce((a, k) => a + amount(vst, k), 0);
	const it = amount(vst + taxes, "income_tax");
	set("excise_charges", flt((d.import_value * flt(d.excise_charges_percent)) / 100, 2));
	set("total_duty_and_taxes", flt(duties + taxes + it + d.excise_charges + flt(d.stamp_charges), 2));
};

nsa_import.dc.calculate = function (frm) {
	if (frm.doc.docstatus !== 0) return;
	(frm.doc.items || []).forEach((d) => nsa_import.dc.calc_row(frm, d));
	frm.refresh_field("items");
	const d = frm.doc;
	const sum = (f) => flt((d.items || []).reduce((a, r) => a + flt(r[f]), 0), 2);
	const set = (f, v) => { if (flt(d[f]) !== flt(v)) frm.set_value(f, v); };
	set("total_import_value", sum("import_value"));
	set("total_duty_and_taxes", sum("total_duty_and_taxes"));
	set("duty_amount", sum("total_duty_and_taxes"));
	set("containers", cint(d.container_20) + cint(d.container_40));
	const hc = flt(sum("total_duty_and_taxes") + flt(d.cess_and_token), 2);
	set("total_duty_amount_hc", hc);
	set("total", flt(hc + flt(d.do_amount) + flt(d.yard_amount) + flt(d.security_deposit_amount) + flt(d.other_amount), 2));
};

const nsa_dc_calc = (frm) => nsa_import.dc.calculate(frm);

frappe.ui.form.on("Duty Calculation", {
	setup(frm) {
		frm.set_query("shipping_document", () => ({ filters: { docstatus: 1 } }));
		frm.set_query("warehouse", "items", () => ({ filters: { company: frm.doc.company, is_group: 0 } }));
	},
	refresh(frm) {
		if (frm.is_new() || frm.doc.docstatus === 2) return;
		const make = (method) => () => frappe.model.open_mapped_doc({ method, frm });
		frm.make_methods = Object.assign(frm.make_methods || {}, {
			"Freight Bill": make("nsa_import.api.make_freight_bill"),
			"Transporter Bill": make("nsa_import.api.make_transporter_bill"),
			"Clearance Bill": make("nsa_import.api.make_clearance_bill"),
			"Arrival Notice": make("nsa_import.api.make_arrival_notice"),
		});
		frm.add_custom_button(__("Arrival Notice"), make("nsa_import.api.make_arrival_notice"), __("Create"));
		frm.add_custom_button(__("Clearance Bill"), make("nsa_import.api.make_clearance_bill"), __("Create"));
		frm.add_custom_button(__("Freight Bill"), make("nsa_import.api.make_freight_bill"), __("Create"));
		frm.add_custom_button(__("Transporter Bill"), make("nsa_import.api.make_transporter_bill"), __("Create"));
	},
	onload(frm) {
		frappe.db.get_single_value("NSA Import Settings", "landing_charges_percent")
			.then((v) => { frm.__nsa = { landing_charges_percent: v === null || v === undefined ? 1 : v }; })
			.catch(() => { frm.__nsa = { landing_charges_percent: 1 }; });
	},
	shipping_document(frm) {
		if (!frm.doc.shipping_document || !frm.is_new()) return;
		frappe.call({ method: "nsa_import.api.make_duty_calculation", args: { source_name: frm.doc.shipping_document }, freeze: true })
			.then((r) => {
				const doc = r.message;
				if (!doc) return;
				const skip = ["name", "doctype", "docstatus", "__islocal", "__unsaved", "owner", "creation", "modified", "naming_series", "items"];
				Object.keys(doc).forEach((k) => { if (!skip.includes(k) && frm.fields_dict[k]) frm.doc[k] = doc[k]; });
				frm.clear_table("items");
				(doc.items || []).forEach((row) => {
					const c = frm.add_child("items");
					Object.keys(row).forEach((k) => {
						if (!["name", "parent", "parenttype", "parentfield", "idx", "doctype", "__islocal"].includes(k)) c[k] = row[k];
					});
				});
				frm.refresh_fields();
				frm.dirty();
			});
	},
	container_20: nsa_dc_calc,
	container_40: nsa_dc_calc,
	cess_and_token: nsa_dc_calc,
	do_amount: nsa_dc_calc,
	yard_amount: nsa_dc_calc,
	security_deposit_amount: nsa_dc_calc,
	other_amount: nsa_dc_calc,
});

const dc_row_events = {
	hs_code(frm, cdt, cdn) {
		const d = locals[cdt][cdn];
		if (!d.hs_code) return;
		frappe.call({ method: "nsa_import.api.get_duty_calculation_rates", args: { hs_code: d.hs_code } }).then((r) => {
			Object.entries(r.message || {}).forEach(([k, v]) => (d[k] = v));
			nsa_dc_calc(frm);
		});
	},
	items_remove: nsa_dc_calc,
};
// base % change copies to the applied rate; every value change recalculates
nsa_import.dc.ALL.forEach((key) => {
	dc_row_events[`${key}_percent`] = (frm, cdt, cdn) => {
		const d = locals[cdt][cdn];
		d[`applied_${key}_rate`] = d[`${key}_percent`];
		nsa_dc_calc(frm);
	};
	dc_row_events[`applied_${key}_rate`] = nsa_dc_calc;
});
["shipped_qty", "rate", "exchange_rate", "cf_value_fcy", "scan_av_value", "insurance_amount", "freight_amount",
	"excise_charges_percent", "stamp_charges"].forEach((f) => (dc_row_events[f] = (frm, cdt, cdn) => {
	const d = locals[cdt][cdn];
	if (["shipped_qty", "rate"].includes(f)) d.cf_value_fcy = flt(flt(d.shipped_qty) * flt(d.rate), 2);
	nsa_dc_calc(frm);
}));
frappe.ui.form.on("Duty Calculation Item", dc_row_events);
