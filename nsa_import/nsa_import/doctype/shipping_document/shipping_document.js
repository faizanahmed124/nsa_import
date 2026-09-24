// NSA Import - Shipping Document (created from Letter of Credit)
frappe.provide("nsa_import.sd");

nsa_import.sd.get_items = function (frm) {
	if (!frm.doc.purchase_order) {
		frappe.msgprint(__("Select the Letter of Credit first."));
		return;
	}
	frappe.call({
		method: "nsa_import.api.get_shipment_defaults",
		args: { purchase_order: frm.doc.purchase_order, letter_of_credit: frm.doc.letter_of_credit || null },
		freeze: true,
	}).then((r) => {
		const data = r.message || {};
		Object.entries(data.header || {}).forEach(([k, v]) => {
			if (v === null || v === undefined || v === "" || !frm.fields_dict[k]) return;
			const always = ["purchase_order", "supplier", "supplier_name", "lc_no", "currency", "company", "pi_no"];
			if (always.includes(k) || !frm.doc[k]) frm.set_value(k, v);
		});
		frm.clear_table("items");
		(data.items || []).forEach((row) => frm.add_child("items", row));
		frm.refresh_field("items");
		nsa_import.sd.calculate(frm);
		if (!(data.items || []).length) frappe.msgprint(__("All items of this Purchase Order are already shipped."));
	});
};

nsa_import.sd.calculate_row = function (frm, cdt, cdn) {
	const d = locals[cdt][cdn];
	const qty = flt(flt(d.shipped_qty) * (flt(d.uom_conversion_factor) || 1), 6);
	frappe.model.set_value(cdt, cdn, "qty", qty);
	frappe.model.set_value(cdt, cdn, "amount", flt(qty * flt(d.rate), 2));
	frappe.model.set_value(cdt, cdn, "remaining_qty", flt(flt(d.ordered_qty) - flt(d.already_shipped_qty) - qty, 6));
	nsa_import.sd.calculate(frm);
};

nsa_import.sd.calculate = function (frm) {
	const d = frm.doc;
	if (d.docstatus !== 0) return;
	const items = d.items || [];
	const set = (f, v) => {
		if (flt(d[f]) !== flt(v)) frm.set_value(f, v);
	};
	const shipped_qty = items.reduce((a, r) => a + flt(r.shipped_qty), 0);
	const amount = flt(items.reduce((a, r) => a + flt(r.amount), 0), 2);
	const base = flt(amount * flt(d.exchange_rate), 2);
	set("total_shipped_qty", flt(shipped_qty, 6));
	set("invoice_amount", amount);
	set("base_invoice_amount", base);
	const commission = flt((base * flt(d.commission_percent)) / 100, 2);
	const fed = flt((commission * flt(d.fed_percent)) / 100, 2);
	set("commission_amount", commission);
	set("fed_amount", fed);
	set("total_charges", flt(commission + fed + flt(d.swift_charges), 2));
};

frappe.ui.form.on("Shipping Document", {
	setup(frm) {
		frm.set_query("letter_of_credit", () => ({
			filters: { docstatus: 1, status: ["not in", ["Closed", "Expired", "Retired"]] },
		}));
		frm.set_query("purchase_order", () => ({ filters: { docstatus: 1, purchase_type: "Import" } }));
		frm.set_query("warehouse", "items", () => ({ filters: { company: frm.doc.company, is_group: 0 } }));
		frm.set_query("clearing_agent", () => ({ filters: { disabled: 0 } }));
	},
	onload(frm) {
		frappe.call({ method: "nsa_import.api.get_shipping_settings" }).then((r) => {
			frm.__nsa = r.message || {};
			frm.toggle_reqd("letter_of_credit", !cint(frm.__nsa.allow_shipping_without_lc));
			if (frm.is_new() && frm.doc.docstatus === 0) {
				if (!flt(frm.doc.fed_percent) && flt(frm.__nsa.default_fed_percent)) {
					frm.set_value("fed_percent", frm.__nsa.default_fed_percent);
				}
				if (!flt(frm.doc.commission_percent) && flt(frm.__nsa.default_shipment_commission_percent)) {
					frm.set_value("commission_percent", frm.__nsa.default_shipment_commission_percent);
				}
			}
		});
	},
	refresh(frm) {
		frm.toggle_enable("letter_of_credit", frm.is_new());
		if (frm.doc.docstatus !== 1) return;
		const open = (method) => frappe.model.open_mapped_doc({ method, frm });
		if (["In Transit", "Arrived"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Customs Clearance (GD)"), () => open("nsa_import.api.make_customs_clearance"), __("Create"));
		}
		if (["Arrived", "Cleared"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Purchase Receipt"), () => open("nsa_import.api.make_purchase_receipt_from_shipment"), __("Create"));
		}
		frm.add_custom_button(__("Shipping Insurance"), () => open("nsa_import.api.make_shipping_insurance"), __("Create"));
		if (frm.doc.letter_of_credit) {
			frm.add_custom_button(__("LC Retirement"), () => open("nsa_import.api.make_lc_retirement_from_shipment"), __("Create"));
		}
		if (flt(frm.doc.total_charges) && !frm.doc.journal_entry) {
			frm.add_custom_button(__("Book Charges (Journal Entry)"), () =>
				frappe.call({ method: "nsa_import.api.make_shipment_journal_entry", args: { source_name: frm.doc.name }, freeze: true })
					.then((r) => {
						if (r.message) {
							frm.reload_doc();
							frappe.set_route("Form", "Journal Entry", r.message);
						}
					}), __("Create"));
		}
		if (frm.doc.status === "In Transit") {
			frm.add_custom_button(__("Mark as Arrived"), () => {
				frappe.prompt(
					{ fieldtype: "Date", fieldname: "date", label: __("Actual Arrival Date"), default: frappe.datetime.get_today(), reqd: 1 },
					(v) => { frm.set_value("actual_arrival_date", v.date); frm.save("Update"); },
					__("Mark as Arrived"));
			});
		}
		frm.dashboard.add_indicator(__("Remaining Qty: {0}", [flt(frm.doc.total_remaining_qty, 3)]),
			flt(frm.doc.total_remaining_qty) > 0 ? "orange" : "green");
		const tracking = [
			["docs_received_from_bank_date", __("Bank")], ["original_doc_sent_to_agent", __("Agent")],
			["original_doc_received_in_ats", __("ATS")], ["original_doc_paid", __("Paid")],
		];
		const done = tracking.filter(([f]) => frm.doc[f]).length;
		frm.dashboard.add_indicator(__("Original Docs: {0}/{1}", [done, tracking.length]), done === tracking.length ? "green" : "red");
	},
	get_items(frm) {
		nsa_import.sd.get_items(frm);
	},
	letter_of_credit(frm) {
		if (!frm.doc.letter_of_credit) return;
		frappe.db.get_value("Letter of Credit", frm.doc.letter_of_credit, ["purchase_order", "lc_no"]).then((r) => {
			const v = r.message || {};
			if (!v.lc_no) {
				frappe.msgprint(__("Enter the bank's LC Number on Letter of Credit {0} first.", [frm.doc.letter_of_credit]));
			}
			frm.set_value("purchase_order", v.purchase_order).then(() => nsa_import.sd.get_items(frm));
		});
	},
	purchase_order(frm) {
		if (frm.doc.purchase_order && !frm.doc.letter_of_credit && !(frm.doc.items || []).length) nsa_import.sd.get_items(frm);
	},
	exchange_rate: (frm) => nsa_import.sd.calculate(frm),
	commission_percent: (frm) => nsa_import.sd.calculate(frm),
	fed_percent: (frm) => nsa_import.sd.calculate(frm),
	swift_charges: (frm) => nsa_import.sd.calculate(frm),
	total_shipped_qty(frm) {
		if (frm.doc.docstatus === 0 && !flt(frm.doc.packing_qty)) frm.set_value("packing_qty", frm.doc.total_shipped_qty);
	},
});

frappe.ui.form.on("Shipping Document Item", {
	shipped_qty: (frm, cdt, cdn) => nsa_import.sd.calculate_row(frm, cdt, cdn),
	uom_conversion_factor: (frm, cdt, cdn) => nsa_import.sd.calculate_row(frm, cdt, cdn),
	uom(frm, cdt, cdn) {
		const d = locals[cdt][cdn];
		if (!d.uom || d.uom === d.po_uom) {
			frappe.model.set_value(cdt, cdn, "uom_conversion_factor", 1);
			return;
		}
		frappe.call({
			method: "nsa_import.api.get_item_uom_factor",
			args: { item_code: d.item_code, from_uom: d.uom, to_uom: d.po_uom },
		}).then((r) => {
			const f = flt(r.message);
			if (!f) frappe.msgprint(__("No UOM conversion found for {0}: set the factor manually in Quantity Tracking.", [d.item_code]));
			frappe.model.set_value(cdt, cdn, "uom_conversion_factor", f || 1);
		});
	},
	items_remove: (frm) => nsa_import.sd.calculate(frm),
});
