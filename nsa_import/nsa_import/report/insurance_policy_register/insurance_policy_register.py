"""Insurance Policy Register.

One report for: Insurance Policy Register, Insurance Company-wise policies (filter Insurance Company),
Policy Utilization (tick 'Show Utilization'), Expired Policies (Status = Expired) and
Fully Utilized Policies (Status = Fully Utilized).
"""

import frappe
from frappe import _


def execute(filters=None):
	filters = frappe._dict(filters or {})
	detail = bool(filters.get("show_utilization"))

	def col(label, fieldname, fieldtype="Data", options=None, width=120):
		c = {"label": _(label), "fieldname": fieldname, "fieldtype": fieldtype, "width": width}
		if options:
			c["options"] = options
		return c

	columns = [
		col("Insurance Company", "insurance_company", "Link", "Insurance Company", 170),
		col("Policy", "policy_no", width=130),
		col("Insurance Policy", "name", "Link", "Insurance Policy", 120),
		col("Bank", "bank", "Link", "Bank", 130),
		col("Bank Account", "bank_account", "Link", "Bank Account", 150),
		col("Currency", "currency", "Link", "Currency", 70),
		col("Insurance Limit", "insurance_limit", "Currency", "currency", 130),
		col("Utilized", "utilized_amount", "Currency", "currency", 130),
		col("Balance Insurance", "balance_insurance", "Currency", "currency", 130),
		col("Policy Date", "policy_date", "Date", width=100),
		col("Expiry Date", "expiry_date", "Date", width=100),
		col("Status", "status", width=110),
	]
	if detail:
		columns += [
			col("Shipping Insurance", "shipping_insurance", "Link", "Shipping Insurance", 130),
			col("Date", "si_date", "Date", width=90),
			col("Shipping Document", "shipping_document", "Link", "Shipping Document", 130),
			col("LC No.", "lc_no", width=110),
			col("PO No.", "purchase_order", "Link", "Purchase Order", 130),
			col("Insured Amount", "si_amount", "Currency", "currency", 130),
		]

	conditions = {}
	for f in ("insurance_company", "bank", "company", "status"):
		if filters.get(f):
			conditions[f] = filters.get(f)
	policies = frappe.get_all("Insurance Policy", filters=conditions, order_by="insurance_company, policy_no",
							  fields=["name", "insurance_company", "policy_no", "bank", "bank_account", "currency",
									  "insurance_limit", "utilized_amount", "balance_insurance", "policy_date",
									  "expiry_date", "status"])
	if not detail:
		return columns, policies

	rows = frappe.get_all("Shipping Insurance",
						  filters={"insurance_policy": ["in", [p.name for p in policies] or [""]], "docstatus": 1},
						  fields=["name", "insurance_policy", "posting_date", "shipping_document", "lc_no",
								  "purchase_order", "insurance_amount"], order_by="posting_date")
	by_policy = {}
	for r in rows:
		by_policy.setdefault(r.insurance_policy, []).append(r)
	data = []
	for p in policies:
		data.append(p)
		for r in by_policy.get(p.name, []):
			data.append({"currency": p.currency, "shipping_insurance": r.name, "si_date": r.posting_date,
						 "shipping_document": r.shipping_document, "lc_no": r.lc_no,
						 "purchase_order": r.purchase_order, "si_amount": r.insurance_amount, "indent": 1})
	return columns, data
