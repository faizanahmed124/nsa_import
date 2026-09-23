// NSA Import - Import Shipment (Shipping Documents)
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

function nsa_get_shipment_items(frm) {
	frappe.call({
		method: "nsa_import.api.get_shipment_defaults",
		args: { purchase_order: frm.doc.purchase_order, letter_of_credit: frm.doc.letter_of_credit || null },
		freeze: true,
	}).then((r) => {
		const data = r.message || {};
		nsa_set_if_empty(frm, data.header);
		frm.clear_table("items");
		(data.items || []).forEach((row) => frm.add_child("items", row));
		frm.refresh_field("items");
		if (!(data.items || []).length) frappe.msgprint(__("All items of this Purchase Order are already shipped."));
	});
}

frappe.ui.form.on("Import Shipment", {
	setup(frm) {
		frm.set_query("purchase_order", () => ({ filters: { docstatus: 1, purchase_type: "Import" } }));
		frm.set_query("letter_of_credit", () => ({ filters: { docstatus: 1, purchase_order: frm.doc.purchase_order } }));
	},
	refresh(frm) {
		if (frm.doc.docstatus === 0 && frm.doc.purchase_order) {
			frm.add_custom_button(__("Get Pending Items"), () => nsa_get_shipment_items(frm));
		}
		if (frm.doc.docstatus !== 1) return;
		const open = (method) => frappe.model.open_mapped_doc({ method, frm });
		if (["In Transit", "Arrived"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Customs Clearance (GD)"), () => open("nsa_import.api.make_customs_clearance"), __("Create"));
		}
		if (["Arrived", "Cleared"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Purchase Receipt"), () => open("nsa_import.api.make_purchase_receipt_from_shipment"), __("Create"));
		}
		if (frm.doc.letter_of_credit) {
			frm.add_custom_button(__("LC Retirement"), () => open("nsa_import.api.make_lc_retirement_from_shipment"), __("Create"));
		}
		if (frm.doc.status === "In Transit") {
			frm.add_custom_button(__("Mark as Arrived"), () => {
				frappe.prompt(
					{ fieldtype: "Date", fieldname: "date", label: __("Actual Arrival Date"), default: frappe.datetime.get_today(), reqd: 1 },
					(v) => { frm.set_value("actual_arrival_date", v.date); frm.save("Update"); },
					__("Mark as Arrived"));
			});
		}
		const docs = frm.doc.documents || [];
		const pending = docs.filter((d) => !d.original_received).length;
		frm.dashboard.add_indicator(__("Original documents pending: {0}", [pending]), pending ? "red" : "green");
	},
	purchase_order(frm) {
		if (frm.doc.purchase_order && !(frm.doc.items || []).filter((d) => d.item_code).length) nsa_get_shipment_items(frm);
	},
});

frappe.ui.form.on("Import Shipment Item", {
	qty(frm, cdt, cdn) {
		const d = locals[cdt][cdn];
		frappe.model.set_value(cdt, cdn, "amount", flt(d.qty) * flt(d.rate));
	},
	rate(frm, cdt, cdn) {
		const d = locals[cdt][cdn];
		frappe.model.set_value(cdt, cdn, "amount", flt(d.qty) * flt(d.rate));
	},
});
