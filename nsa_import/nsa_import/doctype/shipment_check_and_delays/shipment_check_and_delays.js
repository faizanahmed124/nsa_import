// NSA Import - Shipment Check And Delays
frappe.ui.form.on("Shipment Check And Delays", {
	setup(frm) {
		frm.set_query("shipping_document", () => ({ filters: { docstatus: ["<", 2] } }));
	},
	shipping_document(frm) {
		if (frm.doc.shipping_document) frm.trigger("load_dates");
	},
	fetch_dates(frm) {
		frm.trigger("load_dates");
	},
	load_dates(frm) {
		if (!frm.doc.shipping_document) return;
		frappe.call({ method: "nsa_import.api.get_shipment_milestone_dates", args: { shipping_document: frm.doc.shipping_document } })
			.then((r) => {
				let changed = 0;
				Object.entries(r.message || {}).forEach(([f, v]) => {
					if (v && frm.doc[f] !== v) { frm.set_value(f, v); changed++; }
				});
				frappe.show_alert({ message: __("{0} date(s) updated from import documents", [changed]), indicator: "green" });
			});
	},
	eta_to_empty_to(frm) {
		if (frm.doc.eta_to_empty_to && !frm.doc.ats_to_empty_to) frm.set_value("ats_to_empty_to", frm.doc.eta_to_empty_to);
	},
	ats_to_empty_to(frm) {
		if (frm.doc.ats_to_empty_to && !frm.doc.eta_to_empty_to) frm.set_value("eta_to_empty_to", frm.doc.ats_to_empty_to);
	},
});
