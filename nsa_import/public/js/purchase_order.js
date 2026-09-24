// NSA Import - Purchase Order (Local / Import dynamic layout)
frappe.provide("nsa_import");

nsa_import.IMPORT_ITEM_FIELDS = [
	"hs_code", "weight_uom", "item_country_of_origin", "net_weight",
	"gross_weight", "item_freight", "item_insurance", "import_rate",
];
nsa_import.IMPORT_MANDATORY = ["mode_of_shipment", "pi_no", "pi_date", "shipping_term", "import_payment_term"];

nsa_import.po = {
	is_import(frm) {
		return frm.doc.purchase_type === "Import";
	},

	apply_layout(frm) {
		const is_import = this.is_import(frm);
		const grid = frm.fields_dict.items && frm.fields_dict.items.grid;
		if (grid) {
			nsa_import.IMPORT_ITEM_FIELDS.forEach((f) => {
				if (typeof grid.toggle_display === "function") {
					grid.toggle_display(f, is_import);
				} else {
					grid.update_docfield_property(f, "hidden", is_import ? 0 : 1);
				}
			});
		}
		frm.toggle_reqd(nsa_import.IMPORT_MANDATORY, is_import);

		const lc_required = is_import && (frm.doc.import_payment_term || "").toUpperCase().startsWith("LC");
		frm.toggle_reqd(["lc_no", "lc_date"], lc_required);

		const company_currency = frm.doc.company ? erpnext.get_currency(frm.doc.company) : null;
		const is_fx = !!(frm.doc.currency && company_currency && frm.doc.currency !== company_currency);
		frm.toggle_reqd("conversion_rate", is_fx);
	},

	set_naming_series(frm) {
		if (!frm.is_new() || !frm.fields_dict.naming_series) return;
		const options = (frm.fields_dict.naming_series.df.options || "").split("\n");
		const series = this.is_import(frm) ? "IPO-.YYYY.-" : "LPO-.YYYY.-";
		if (options.includes(series) && frm.doc.naming_series !== series) {
			frm.set_value("naming_series", series);
		}
	},

	add_buttons(frm) {
		if (frm.doc.docstatus !== 1 || !this.is_import(frm)) return;
		if (["Closed", "On Hold"].includes(frm.doc.status)) return;
		const group = __("Import");
		const open = (method) => frappe.model.open_mapped_doc({ method, frm });

		if (!frm.doc.letter_of_credit) {
			frm.add_custom_button(__("Letter of Credit"), () => open("nsa_import.api.make_letter_of_credit"), group);
		}
		if (flt(frm.doc.per_shipped) < 100) {
			frm.add_custom_button(__("Import Shipment"), () => open("nsa_import.api.make_import_shipment"), group);
		}
		frm.add_custom_button(__("Import Tracker"), () =>
			frappe.set_route("query-report", "Import Tracker", { purchase_order: frm.doc.name }), group);
	},

	// Connections -> Letter of Credit (+) : only for Import POs, opens the LC with PO data prefilled
	setup_lc_connection(frm) {
		frm.make_methods = frm.make_methods || {};
		frm.make_methods["Letter of Credit"] = () => {
			if (!this.is_import(frm)) {
				frappe.msgprint(__("Letter of Credit can only be created from an Import Purchase Order."));
				return;
			}
			frappe.model.open_mapped_doc({ method: "nsa_import.api.make_letter_of_credit", frm });
		};
		const toggle = () => {
			const area = frm.dashboard && frm.dashboard.transactions_area;
			if (area && area.find) {
				area.find('.document-link[data-doctype="Letter of Credit"]').toggle(this.is_import(frm));
			}
		};
		toggle();
		setTimeout(toggle, 600);
	},

	show_status(frm) {
		if (frm.doc.docstatus === 1 && this.is_import(frm) && frm.doc.import_status) {
			frm.dashboard.add_indicator(__("Import: {0}", [__(frm.doc.import_status)]), "blue");
			if (frm.doc.per_shipped) {
				frm.dashboard.add_indicator(__("Shipped: {0}%", [flt(frm.doc.per_shipped, 2)]), "orange");
			}
		}
	},
};

frappe.ui.form.on("Purchase Order", {
	onload(frm) {
		if (frm.is_new() && !frm.doc.purchase_type) frm.set_value("purchase_type", "Local");
	},
	refresh(frm) {
		nsa_import.po.apply_layout(frm);
		nsa_import.po.add_buttons(frm);
		nsa_import.po.setup_lc_connection(frm);
		nsa_import.po.show_status(frm);
	},
	purchase_type(frm) {
		nsa_import.po.apply_layout(frm);
		nsa_import.po.set_naming_series(frm);
		if (frm.doc.purchase_type === "Local") {
			frm.set_value("import_payment_term", "");
		}
	},
	import_payment_term(frm) {
		nsa_import.po.apply_layout(frm);
		if ((frm.doc.import_payment_term || "").startsWith("LC") && !frm.doc.payment_method) {
			frm.set_value("payment_method", "LC");
		}
	},
	currency(frm) {
		nsa_import.po.apply_layout(frm);
	},
	company(frm) {
		nsa_import.po.apply_layout(frm);
	},
	shipping_term(frm) {
		if (["CFR", "CIF", "CPT", "CIP", "DAP", "DPU", "DDP"].includes(frm.doc.shipping_term) && flt(frm.doc.freight_amount)) {
			frappe.show_alert({ message: __("Freight is normally included in the price for {0}.", [frm.doc.shipping_term]), indicator: "orange" });
		}
	},
});

frappe.ui.form.on("Purchase Order Item", {
	items_add(frm) {
		nsa_import.po.apply_layout(frm);
	},
});
