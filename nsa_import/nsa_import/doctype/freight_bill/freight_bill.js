// NSA Import - Freight Bill
const nsa_fb_calc = (frm) => {
	if (frm.doc.docstatus !== 0) return;
	const d = frm.doc;
	const pkr = flt(flt(d.freight_value_usd) * flt(d.conversion_rate), 2);
	const charges = ["do_charges", "fca", "bl_endorsement_fee", "dgm_report", "container_size_20", "container_size_40"]
		.reduce((a, f) => a + flt(d[f]), 0);
	if (flt(d.freight_value_pkr) !== pkr) frm.set_value("freight_value_pkr", pkr);
	if (flt(d.total) !== flt(pkr + charges, 2)) frm.set_value("total", flt(pkr + charges, 2));
};

frappe.ui.form.on("Freight Bill", {
	setup(frm) {
		frm.set_query("purchase_order", () => ({ filters: { purchase_type: "Import", docstatus: 1 } }));
		frm.set_query("duty_calculation", () => ({ filters: { docstatus: ["<", 2] } }));
		frm.set_query("shipping_document", () => ({ filters: { docstatus: 1 } }));
	},
	duty_calculation(frm) {
		if (!frm.doc.duty_calculation) return;
		frappe.db.get_value("Duty Calculation", frm.doc.duty_calculation, ["shipping_document", "purchase_order"]).then((r) => {
			const v = r.message || {};
			frm.set_value("shipping_document", v.shipping_document);
			frm.set_value("purchase_order", v.purchase_order);
		});
	},
	freight_value_usd: nsa_fb_calc,
	conversion_rate: nsa_fb_calc,
	do_charges: nsa_fb_calc,
	fca: nsa_fb_calc,
	bl_endorsement_fee: nsa_fb_calc,
	dgm_report: nsa_fb_calc,
	container_size_20: nsa_fb_calc,
	container_size_40: nsa_fb_calc,
});
