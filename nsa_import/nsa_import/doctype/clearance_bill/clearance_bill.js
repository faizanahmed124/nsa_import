// NSA Import - Clearance Bill (mirrors the server formulas)
frappe.provide("nsa_import.cb");
nsa_import.cb.CHARGES = ["excise", "stamp_charges", "lolo_charges", "port_charges", "port_warfage", "weboc", "do",
	"demurrage_detention", "others", "misc", "lab_cargo"];
nsa_import.cb.is_agent = (v) => v === "Paid By Agent" || v === "Deduct By Agent";
nsa_import.cb.BILL_ITEMS = nsa_import.cb.CHARGES.concat(["agency_commission", "sales_tax"]);
nsa_import.cb.SIDES = ["agent", "ats"];

nsa_import.cb.calculate = function (frm) {
	const d = frm.doc;
	const amt = (k, s) => flt(d[`${k}_${s}`]);
	const S = nsa_import.cb.SIDES;
	const total = nsa_import.cb.CHARGES.reduce((a, k) => a + S.reduce((b, s) => b + amt(k, s), 0), 0);
	const extra = ["agency_commission", "sales_tax"].reduce((a, k) => a + S.reduce((b, s) => b + amt(k, s), 0), 0);
	const it = S.reduce((a, s) => a + amt("income_tax", s), 0);
	let by_agent = 0, by_ats = 0;
	nsa_import.cb.BILL_ITEMS.forEach((k) => S.forEach((s) => {
		if (nsa_import.cb.is_agent(d[`${k}_paid_by_${s}`])) by_agent += amt(k, s); else by_ats += amt(k, s);
	}));
	S.forEach((s) => {
		if (nsa_import.cb.is_agent(d[`income_tax_paid_by_${s}`])) by_agent -= amt("income_tax", s); else by_ats -= amt("income_tax", s);
	});
	const total_bill = flt(total + extra - it, 2);
	const set = (f, v) => { if (flt(d[f]) !== flt(v)) frm.set_value(f, v); };
	if (d.docstatus === 0) {
		set("total", flt(total, 2));
		set("total_bill", total_bill);
		set("paid_by_agent_total", flt(by_agent, 2));
		set("paid_by_ats_total", flt(by_ats, 2));
	}
	set("payable_receivable", flt(flt(d.total_bill) - flt(d.amount_paid_to_agent), 2));
};

const cb_events = {
	setup(frm) {
		frm.set_query("purchase_order", () => ({ filters: { purchase_type: "Import", docstatus: 1 } }));
		frm.set_query("duty_calculation", () => ({ filters: { docstatus: ["<", 2] } }));
		frm.set_query("shipping_document", () => ({ filters: { docstatus: 1 } }));
	},
	duty_calculation(frm) {
		if (!frm.doc.duty_calculation) return;
		frappe.db.get_value("Duty Calculation", frm.doc.duty_calculation, ["shipping_document", "purchase_order", "mbl_no"])
			.then((r) => {
				const v = r.message || {};
				frm.set_value("shipping_document", v.shipping_document);
				frm.set_value("purchase_order", v.purchase_order);
				if (!frm.doc.bl_no) frm.set_value("bl_no", v.mbl_no);
			});
	},
	amount_paid_to_agent: (frm) => nsa_import.cb.calculate(frm),
};
nsa_import.cb.BILL_ITEMS.concat(["income_tax"]).forEach((k) => nsa_import.cb.SIDES.forEach((s) => {
	cb_events[`${k}_${s}`] = (frm) => nsa_import.cb.calculate(frm);
	cb_events[`${k}_paid_by_${s}`] = (frm) => nsa_import.cb.calculate(frm);
}));
frappe.ui.form.on("Clearance Bill", cb_events);
