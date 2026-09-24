// NSA Import - Settings
frappe.ui.form.on("NSA Import Settings", {
	setup(frm) {
		[
			"lc_margin_account", "bank_charges_account", "fed_account", "customs_duty_account", "sales_tax_account",
			"income_tax_account", "freight_account", "clearing_account", "other_import_expense_account",
		].forEach((field) => {
			frm.set_query(field, "company_accounts", (doc, cdt, cdn) => ({
				filters: { company: locals[cdt][cdn].company, is_group: 0 },
			}));
		});
	},
});
