"""Insurance Balance - policy total, utilised amount and remaining balance per policy."""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = [
		{"label": _("Insurance Company"), "fieldname": "insurance_company", "fieldtype": "Data", "width": 170},
		{"label": _("Policy Number"), "fieldname": "policy_number", "fieldtype": "Data", "width": 140},
		{"label": _("Letter of Credit"), "fieldname": "letter_of_credit", "fieldtype": "Link",
		 "options": "Letter of Credit", "width": 130},
		{"label": _("LC No."), "fieldname": "lc_no", "fieldtype": "Data", "width": 110},
		{"label": _("Supplier"), "fieldname": "supplier_name", "fieldtype": "Data", "width": 150},
		{"label": _("Currency"), "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "width": 70},
		{"label": _("Insurance Total Policy"), "fieldname": "insurance_total_policy", "fieldtype": "Currency",
		 "options": "currency", "width": 140},
		{"label": _("Utilized"), "fieldname": "utilized", "fieldtype": "Currency", "options": "currency", "width": 130},
		{"label": _("Balance"), "fieldname": "balance", "fieldtype": "Currency", "options": "currency", "width": 130},
		{"label": _("Shipments"), "fieldname": "shipments", "fieldtype": "Int", "width": 90},
		{"label": _("Premium (PKR)"), "fieldname": "premium", "fieldtype": "Currency", "width": 120},
		{"label": _("Policy Expiry"), "fieldname": "policy_expiry_date", "fieldtype": "Date", "width": 100},
	]
	conditions = {"docstatus": 1}
	for f in ("company", "letter_of_credit", "supplier"):
		if filters.get(f):
			conditions[f] = filters.get(f)
	if filters.get("insurance_company"):
		conditions["insurance_company"] = ["like", f"%{filters.insurance_company}%"]

	docs = frappe.get_all("Shipping Insurance", filters=conditions, order_by="posting_date asc",
						  fields=["policy_key", "insurance_company", "policy_number", "letter_of_credit", "lc_no",
								  "supplier_name", "currency", "insurance_total_policy", "insurance_amount",
								  "base_premium_amount", "policy_expiry_date"])
	groups = {}
	for d in docs:
		g = groups.get(d.policy_key)
		if not g:
			g = groups[d.policy_key] = frappe._dict(d, utilized=0.0, shipments=0, premium=0.0)
		g.utilized += flt(d.insurance_amount)
		g.shipments += 1
		g.premium += flt(d.base_premium_amount)
		g.insurance_total_policy = d.insurance_total_policy  # latest document's policy total
		if d.policy_expiry_date:
			g.policy_expiry_date = d.policy_expiry_date
	data = []
	for g in groups.values():
		g.balance = flt(flt(g.insurance_total_policy) - g.utilized, 2)
		if filters.get("only_with_balance") and g.balance <= 0:
			continue
		data.append(g)
	return columns, data
