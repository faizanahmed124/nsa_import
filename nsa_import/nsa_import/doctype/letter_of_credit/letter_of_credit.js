// NSA Import - Letter of Credit
// Fixed PO values (Supplier, PO Qty, PO Amount, Currency) are read-only; calculations mirror the server.
frappe.provide("nsa_import.lc");

nsa_import.lc.FIXED = ["company", "supplier", "supplier_name", "currency", "po_qty", "po_amount", "pi_no", "pi_date"];

nsa_import.lc.load_settings = function (frm) {
	return frappe
		.call({ method: "nsa_import.api.get_lc_settings" })
		.then((r) => {
			frm.__nsa = r.message || {};
		})
		.catch(() => {
			frm.__nsa = {};
		});
};

nsa_import.lc.set = function (frm, field, value) {
	if (frm.fields_dict[field] && flt(frm.doc[field]) !== flt(value)) frm.set_value(field, value);
};

nsa_import.lc.calculate = function (frm) {
	const d = frm.doc;
	const s = frm.__nsa || {};
	const set = (f, v) => nsa_import.lc.set(frm, f, flt(v, 2));
	if (d.docstatus === 0) {
		const rate = flt(d.exchange_rate) || 1;
		const tol = flt(d.tolerance_percent);
		const effective = flt(d.lc_amount) + (d.amendments || []).reduce((a, r) => a + flt(r.amount_change), 0);
		set("lc_tolerance_amount", (flt(d.po_amount) * tol) / 100);
		set("max_lc_amount", effective * (1 + tol / 100));
		set("base_lc_amount", effective * rate);
		if (flt(d.margin_percent)) set("margin_amount", (effective * rate * flt(d.margin_percent)) / 100);

		let base = flt(d.lc_amount);
		if (s.lc_commission_base === "PO Amount") base = flt(d.po_amount);
		else if (s.lc_commission_base === "LC Amount incl. Tolerance") base = flt(d.lc_amount) * (1 + tol / 100);
		const commission = flt((base * rate * flt(d.lc_commission_percent)) / 100, 2);
		const fed_base = commission + (cint(s.fed_on_amendment_commission) ? flt(d.amendment_commission) : 0);
		const fed = flt((fed_base * flt(d.fed_percent)) / 100, 2);
		const total_lc =
			commission + fed + (cint(s.include_lc_after_in_charges) ? flt(d.lc_after) : 0) +
			flt(d.swift_charges) + flt(d.amendment_commission) + flt(d.swift_charges_amended);
		const other = (d.charges || []).reduce((a, r) => a + flt(r.amount), 0);
		set("lc_commission_amount", commission);
		set("fed_on_commission", fed);
		set("total_lc_charges", total_lc);
		set("total_charges", total_lc + other);
	}
	nsa_import.lc.set(frm, "total_expense_booked",
		flt((d.expense_booked || []).reduce((a, r) => a + flt(r.expense_amount), 0), 2));
};

nsa_import.lc.validate_dates = function (frm) {
	const d = frm.doc;
	const lt = (a, b) => a && b && frappe.datetime.str_to_obj(a) < frappe.datetime.str_to_obj(b);
	if (lt(d.expiry_date, d.lc_date)) frappe.msgprint(__("LC Expiry Date cannot be earlier than LC Date."));
	if (lt(d.latest_shipment_date, d.lc_date)) frappe.msgprint(__("Latest Date of Shipment cannot be earlier than LC Date."));
	if (lt(d.expiry_date, d.latest_shipment_date)) frappe.msgprint(__("Latest Date of Shipment cannot be after LC Expiry Date."));
};

nsa_import.lc.make_je = function (frm) {
	frappe.call({
		method: "nsa_import.api.make_lc_journal_entry",
		args: { source_name: frm.doc.name },
		freeze: true,
		callback(r) {
			if (r.message) {
				frm.reload_doc();
				frappe.set_route("Form", "Journal Entry", r.message);
			}
		},
	});
};

frappe.ui.form.on("Letter of Credit", {
	setup(frm) {
		frm.set_query("purchase_order", () => ({
			filters: {
				purchase_type: "Import",
				docstatus: cint((frm.__nsa || {}).allow_lc_on_draft_po) ? ["<", 2] : 1,
			},
		}));
		frm.set_query("lc_bank_account", () => {
			const filters = { is_company_account: 1 };
			if (frm.doc.company) filters.company = frm.doc.company;
			if (frm.doc.issuing_bank) filters.bank = frm.doc.issuing_bank;
			return { filters };
		});
		frm.set_query("bank_gl_account", () => ({ filters: { company: frm.doc.company, is_group: 0, account_type: "Bank" } }));
		frm.set_query("account", "charges", () => ({ filters: { company: frm.doc.company, is_group: 0 } }));
		frm.set_query("expense_account", "expense_booked", () => ({ filters: { company: frm.doc.company, is_group: 0 } }));
		frm.set_query("reference_doctype", "expense_booked", () => ({
			filters: { name: ["in", ["Journal Entry", "Payment Entry", "Purchase Invoice"]] },
		}));
	},
	onload(frm) {
		nsa_import.lc.load_settings(frm).then(() => {
			if (frm.is_new() && frm.doc.docstatus === 0) {
				const s = frm.__nsa;
				if (!frm.doc.fed_percent && flt(s.default_fed_percent)) frm.set_value("fed_percent", s.default_fed_percent);
				if (!frm.doc.lc_commission_percent && flt(s.default_lc_commission_percent)) {
					frm.set_value("lc_commission_percent", s.default_lc_commission_percent);
				}
			}
			nsa_import.lc.calculate(frm);
		});
	},
	refresh(frm) {
		frm.toggle_enable("purchase_order", frm.is_new());
		if (frm.doc.docstatus !== 1) return;
		const open = (method) => frappe.model.open_mapped_doc({ method, frm });
		const locked = ["Closed", "Expired", "Retired"].includes(frm.doc.status);

		if (!locked) {
			frm.add_custom_button(__("Shipping Document"), () => open("nsa_import.api.make_shipping_document_from_lc"), __("Create"));
		}
		if (!["Retired", "Closed"].includes(frm.doc.status)) {
			frm.add_custom_button(__("LC Retirement"), () => open("nsa_import.api.make_lc_retirement"), __("Create"));
		}
		const margin_pending = flt(frm.doc.margin_amount) && !frm.doc.journal_entry;
		if (margin_pending || flt(frm.doc.pending_lc_charges) > 0) {
			frm.add_custom_button(__("Book LC Charges (Journal Entry)"), () => nsa_import.lc.make_je(frm), __("Create"));
		}
		frm.add_custom_button(__("Refresh Expense Booked"), () =>
			frappe.call({ method: "nsa_import.api.sync_lc_expenses", args: { name: frm.doc.name }, freeze: true })
				.then(() => frm.reload_doc()), __("Actions"));
		if (["Fully Shipped", "Retired", "Partially Retired", "Expired"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Close LC"), () =>
				frappe.confirm(__("Close this Letter of Credit?"), () =>
					frappe.call({ method: "nsa_import.api.close_letter_of_credit", args: { name: frm.doc.name } })
						.then(() => frm.reload_doc())), __("Actions"));
		}

		frm.dashboard.add_indicator(__("Balance: {0}", [format_currency(frm.doc.balance_amount, frm.doc.currency)]),
			flt(frm.doc.balance_amount) > 0 ? "orange" : "green");
		frm.dashboard.add_indicator(__("Expense Booked: {0}", [format_currency(frm.doc.total_expense_booked, frm.doc.company_currency)]), "blue");
		if (flt(frm.doc.pending_lc_charges) > 0) {
			frm.dashboard.add_indicator(__("Charges not booked: {0}", [format_currency(frm.doc.pending_lc_charges, frm.doc.company_currency)]), "red");
		}
		if (frm.doc.expiry_date && !locked) {
			const days = frappe.datetime.get_day_diff(frm.doc.expiry_date, frappe.datetime.get_today());
			if (days <= 15) frm.dashboard.add_indicator(__("Expires in {0} day(s)", [days]), days < 0 ? "red" : "orange");
		}
	},
	purchase_order(frm) {
		if (!frm.doc.purchase_order) {
			nsa_import.lc.FIXED.forEach((f) => frm.set_value(f, null));
			return;
		}
		frappe.call({ method: "nsa_import.api.get_lc_defaults", args: { purchase_order: frm.doc.purchase_order } })
			.then((r) => {
				const data = r.message || {};
				Object.entries(data.fixed || {}).forEach(([k, v]) => frm.set_value(k, v));
				Object.entries(data.defaults || {}).forEach(([k, v]) => {
					if (v !== null && v !== undefined && v !== "" && !frm.doc[k] && frm.fields_dict[k]) frm.set_value(k, v);
				});
				if (!frm.doc.lc_amount) frm.set_value("lc_amount", (data.fixed || {}).po_amount);
			})
			.catch(() => frm.set_value("purchase_order", null));
	},
	lc_payment_term(frm) {
		if (frm.doc.lc_payment_term === "LC Usance") frm.set_value("lc_type", "Usance");
		else if (frm.doc.lc_payment_term === "LC at Sight") frm.set_value("lc_type", "Sight");
	},
	lc_bank_account(frm) {
		if (!frm.doc.lc_bank_account) return;
		frappe.db.get_value("Bank Account", frm.doc.lc_bank_account, ["bank", "account"]).then((r) => {
			const v = r.message || {};
			if (v.bank && !frm.doc.issuing_bank) frm.set_value("issuing_bank", v.bank);
			if (v.account) frm.set_value("bank_gl_account", v.account);
		});
	},
	tolerance_percent: (frm) => nsa_import.lc.calculate(frm),
	lc_amount: (frm) => nsa_import.lc.calculate(frm),
	po_amount: (frm) => nsa_import.lc.calculate(frm),
	exchange_rate: (frm) => nsa_import.lc.calculate(frm),
	margin_percent: (frm) => nsa_import.lc.calculate(frm),
	lc_commission_percent: (frm) => nsa_import.lc.calculate(frm),
	fed_percent: (frm) => nsa_import.lc.calculate(frm),
	lc_after: (frm) => nsa_import.lc.calculate(frm),
	swift_charges: (frm) => nsa_import.lc.calculate(frm),
	amendment_commission: (frm) => nsa_import.lc.calculate(frm),
	swift_charges_amended: (frm) => nsa_import.lc.calculate(frm),
	lc_date: (frm) => nsa_import.lc.validate_dates(frm),
	expiry_date: (frm) => nsa_import.lc.validate_dates(frm),
	latest_shipment_date: (frm) => nsa_import.lc.validate_dates(frm),
});

frappe.ui.form.on("LC Charge", {
	amount: (frm) => nsa_import.lc.calculate(frm),
	charges_remove: (frm) => nsa_import.lc.calculate(frm),
});

frappe.ui.form.on("LC Amendment", {
	amount_change: (frm) => nsa_import.lc.calculate(frm),
	amendments_remove: (frm) => nsa_import.lc.calculate(frm),
});

frappe.ui.form.on("LC Expense Booked", {
	expense_amount: (frm) => nsa_import.lc.calculate(frm),
	expense_booked_remove: (frm) => nsa_import.lc.calculate(frm),
	expense_booked_add(frm, cdt, cdn) {
		frappe.model.set_value(cdt, cdn, "posting_date", frappe.datetime.get_today());
	},
});
