// NSA Import - Arrival Notice
const nsa_an_calc = (frm) => {
	(frm.doc.items || []).forEach((d) => {
		d.pending_qty = Math.max(flt(flt(d.shipped_qty) - flt(d.grn_qty), 6), 0);
	});
	frm.refresh_field("items");
	const all_done = (frm.doc.items || []).length && (frm.doc.items || []).every((d) => flt(d.pending_qty) <= 0);
	const status = all_done ? "Received" : "Pending";
	if (frm.doc.grn_status !== status) frm.set_value("grn_status", status);
};

frappe.ui.form.on("Arrival Notice", {
	setup(frm) {
		frm.set_query("warehouse", "items", () => ({ filters: { company: frm.doc.company, is_group: 0 } }));
	},
	refresh(frm) {
		const make_grn = () => frappe.model.open_mapped_doc({ method: "nsa_import.api.make_purchase_receipt_from_arrival_notice", frm });
		frm.make_methods = Object.assign(frm.make_methods || {}, { "Purchase Receipt": make_grn });
		if (frm.doc.docstatus === 1 && frm.doc.grn_status !== "Received") {
			frm.add_custom_button(__("Purchase Receipt"), make_grn, __("Create"));
		}
		if (frm.doc.docstatus < 2 && !frm.is_new()) {
			frm.add_custom_button(__("Update GRN QTY from GRNs"), () =>
				frappe.call({ method: "nsa_import.api.refresh_arrival_notice_grn", args: { name: frm.doc.name }, freeze: true })
					.then(() => frm.reload_doc()));
		}
		const color = frm.doc.grn_status === "Received" ? "green" : "orange";
		frm.dashboard.add_indicator(__("GRN Status: {0}", [__(frm.doc.grn_status || "Pending")]), color);
	},
	container_20(frm) {
		frm.set_value("containers", cint(frm.doc.container_20) + cint(frm.doc.container_40));
	},
	container_40(frm) {
		frm.set_value("containers", cint(frm.doc.container_20) + cint(frm.doc.container_40));
	},
});

frappe.ui.form.on("Arrival Notice Item", {
	grn_qty(frm, cdt, cdn) {
		const d = locals[cdt][cdn];
		if (flt(d.grn_qty) < 0) {
			frappe.msgprint(__("GRN QTY cannot be negative."));
			frappe.model.set_value(cdt, cdn, "grn_qty", 0);
			return;
		}
		nsa_an_calc(frm);
	},
});
