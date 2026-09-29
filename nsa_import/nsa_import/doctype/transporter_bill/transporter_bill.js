// NSA Import - Transporter Bill
const nsa_tb_calc = (frm) => {
	if (frm.doc.docstatus !== 0) return;
	const d = frm.doc;
	const st = flt((flt(d.total_bill_amount) * flt(d.sales_tax_percent)) / 100, 2);
	const gross = flt(flt(d.total_bill_amount) + st, 2);
	const it = flt((gross * flt(d.income_tax_percent)) / 100, 2);
	let net = gross - it - flt(d.other_deduction);
	if (cint((frm.__nsa || {}).withhold_transport_sales_tax)) net -= st;
	const set = (f, v) => { if (flt(d[f]) !== flt(v)) frm.set_value(f, v); };
	set("sales_tax_amount", st);
	set("gross_bill", gross);
	set("income_tax_amount", it);
	set("net_bill_amount", flt(net, 2));
};

frappe.ui.form.on("Transporter Bill", {
	setup(frm) {
		frm.set_query("purchase_order", () => ({ filters: { purchase_type: "Import", docstatus: 1 } }));
		frm.set_query("duty_calculation", () => ({ filters: { docstatus: ["<", 2] } }));
		frm.set_query("shipping_document", () => ({ filters: { docstatus: 1 } }));
	},
	onload(frm) {
		frappe.call({ method: "nsa_import.api.get_transport_settings" }).then((r) => {
			frm.__nsa = r.message || {};
			nsa_tb_calc(frm);
		});
	},
	duty_calculation(frm) {
		if (!frm.doc.duty_calculation) return;
		frappe.db.get_value("Duty Calculation", frm.doc.duty_calculation,
			["shipping_document", "purchase_order", "container_20", "container_40", "mbl_no"]).then((r) => {
			const v = r.message || {};
			frm.set_value("shipping_document", v.shipping_document);
			frm.set_value("purchase_order", v.purchase_order);
			if (!frm.doc.container_20) frm.set_value("container_20", v.container_20);
			if (!frm.doc.container_40) frm.set_value("container_40", v.container_40);
			if (!frm.doc.bl_no) frm.set_value("bl_no", v.mbl_no);
		});
	},
	total_bill_amount: nsa_tb_calc,
	sales_tax_percent: nsa_tb_calc,
	income_tax_percent: nsa_tb_calc,
	other_deduction: nsa_tb_calc,
});
