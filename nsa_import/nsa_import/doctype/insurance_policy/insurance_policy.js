// NSA Import - Insurance Policy
frappe.ui.form.on("Insurance Policy", {
	setup(frm) {
		frm.set_query("bank_account", () => {
			const filters = {};
			if (frm.doc.bank) filters.bank = frm.doc.bank;
			if (frm.doc.company) filters.company = frm.doc.company;
			return { filters };
		});
	},
	refresh(frm) {
		const colors = { Active: "green", Expired: "red", "Fully Utilized": "orange", Suspended: "grey" };
		if (!frm.is_new()) {
			frm.dashboard.add_indicator(__("Balance: {0}", [format_currency(frm.doc.balance_insurance, frm.doc.currency)]),
				colors[frm.doc.status] || "blue");
		}
	},
	company(frm) {
		if (frm.doc.company && !frm.doc.currency) frm.set_value("currency", erpnext.get_currency(frm.doc.company));
	},
	bank(frm) {
		if (frm.doc.bank_account) frm.set_value("bank_account", null);
	},
	policy_date(frm) {
		const d = frm.doc;
		if (d.policy_date && d.expiry_date && d.expiry_date < d.policy_date) frappe.msgprint(__("Expiry Date cannot be earlier than Policy Date."));
	},
	expiry_date(frm) {
		frm.trigger("policy_date");
	},
});
