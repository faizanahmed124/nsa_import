// NSA Import - Shipping Insurance (created from Shipping Document)
frappe.provide("nsa_import.si");

nsa_import.si.allocate = function (frm) {
	const items = frm.doc.items || [];
	if (!items.length) return;
	const total = flt(frm.doc.insurance_amount);
	const base = items.reduce((a, d) => a + flt(d.amount), 0);
	let remaining = total;
	items.forEach((d, i) => {
		let v;
		if (i === items.length - 1) v = flt(remaining, 2);
		else {
			v = flt(total * (base ? flt(d.amount) / base : 1 / items.length), 2);
			remaining -= v;
		}
		frappe.model.set_value(d.doctype, d.name, "insurance_amount", v);
	});
};

nsa_import.si.calculate = function (frm) {
	if (frm.doc.docstatus !== 0) return;
	const d = frm.doc;
	const set = (f, v) => {
		if (flt(d[f]) !== flt(v)) frm.set_value(f, v);
	};
	const premium = flt((flt(d.insurance_amount) * flt(d.premium_rate)) / 100, 2);
	set("premium_amount", premium);
	set("base_insurance_amount", flt(flt(d.insurance_amount) * flt(d.exchange_rate), 2));
	set("base_premium_amount", flt(premium * flt(d.exchange_rate), 2));
	set("balance_insurance", flt(flt(d.insurance_total_policy) - flt(d.utilized_before) - flt(d.insurance_amount), 2));
};

nsa_import.si.render_related = function (frm) {
	const field = frm.fields_dict.related_documents_html;
	if (!field || !frm.doc.shipping_document) return;
	frappe.call({
		method: "nsa_import.api.get_insurance_related_documents",
		args: { shipping_document: frm.doc.shipping_document },
	}).then((r) => {
		const rows = (r.message || []).map((row) => {
			let links;
			if (row.missing) {
				links = `<span class="text-muted">${__("Not set up yet")}</span>`;
			} else if (!(row.names || []).length) {
				links = `<span class="text-muted">${__("None")}</span>`;
			} else {
				links = row.names
					.map((n) => `<a href="/app/${frappe.router.slug(row.doctype)}/${encodeURIComponent(n)}">${frappe.utils.escape_html(n)}</a>`)
					.join(", ");
				if (row.note) links += ` <span class="text-muted">(${__(row.note)})</span>`;
			}
			return `<tr><td style="width:35%"><b>${__(row.label)}</b></td><td>${links}</td></tr>`;
		});
		field.$wrapper.html(`<table class="table table-bordered table-sm" style="margin:0">${rows.join("")}</table>`);
	});
};

frappe.ui.form.on("Shipping Insurance", {
	setup(frm) {
		frm.set_query("shipping_document", () => ({ filters: { docstatus: 1 } }));
	},
	refresh(frm) {
		frm.toggle_enable("shipping_document", frm.is_new());
		nsa_import.si.render_related(frm);
		if (frm.doc.docstatus === 1) {
			const color = { "Fully Utilized": "red", "Partially Utilized": "orange", "Policy Issued": "green" }[frm.doc.status] || "blue";
			frm.dashboard.add_indicator(__("Balance Insurance: {0}", [format_currency(frm.doc.balance_insurance, frm.doc.currency)]), color);
			if (!frm.doc.policy_number) {
				frm.dashboard.set_headline(__("Enter the Policy Number when the policy is issued (editable after submit)."));
			}
		}
	},
	shipping_document(frm) {
		if (!frm.doc.shipping_document || !frm.is_new()) return;
		frappe.model.with_doctype("Shipping Insurance", () => {
			frappe.call({ method: "nsa_import.api.make_shipping_insurance", args: { source_name: frm.doc.shipping_document }, freeze: true })
				.then((r) => {
					const doc = r.message;
					if (!doc) return;
					const skip = ["name", "doctype", "docstatus", "__islocal", "__unsaved", "owner", "creation", "modified", "naming_series"];
					Object.keys(doc).forEach((k) => {
						if (!skip.includes(k) && k !== "items" && frm.fields_dict[k] && doc[k] !== null && doc[k] !== undefined) {
							frm.doc[k] = doc[k];
						}
					});
					frm.clear_table("items");
					(doc.items || []).forEach((row) => {
						const c = frm.add_child("items");
						Object.keys(row).forEach((k) => {
							if (!["name", "parent", "parenttype", "parentfield", "idx", "doctype", "__islocal"].includes(k)) c[k] = row[k];
						});
					});
					frm.refresh_fields();
					frm.dirty();
					nsa_import.si.calculate(frm);
					nsa_import.si.render_related(frm);
				});
		});
	},
	allocate_insurance(frm) {
		nsa_import.si.allocate(frm);
	},
	insurance_amount(frm) {
		nsa_import.si.allocate(frm);
		nsa_import.si.calculate(frm);
	},
	premium_rate: (frm) => nsa_import.si.calculate(frm),
	exchange_rate: (frm) => nsa_import.si.calculate(frm),
	insurance_total_policy: (frm) => nsa_import.si.calculate(frm),
	currency(frm) {
		if (frm.doc.company && frm.doc.currency === erpnext.get_currency(frm.doc.company)) frm.set_value("exchange_rate", 1);
	},
	policy_start_date(frm) {
		const d = frm.doc;
		if (d.policy_start_date && d.policy_expiry_date && d.policy_expiry_date < d.policy_start_date) {
			frappe.msgprint(__("Policy Expiry Date cannot be earlier than Policy Start Date."));
		}
	},
});
