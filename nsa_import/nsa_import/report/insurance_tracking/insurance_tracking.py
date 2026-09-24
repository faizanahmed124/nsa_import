"""Insurance Tracking - one report for company / LC-wise / PO-wise / shipment-wise insurance views.

Use the filters (LC, PO, Supplier, Shipping Document, Policy) for LC-wise, PO-wise or shipment views and
tick 'Show Items' for item-wise insurance allocation.
"""

import frappe
from frappe import _


def execute(filters=None):
	filters = frappe._dict(filters or {})
	show_items = bool(filters.get("show_items"))

	def col(label, fieldname, fieldtype="Data", options=None, width=120):
		c = {"label": _(label), "fieldname": fieldname, "fieldtype": fieldtype, "width": width}
		if options:
			c["options"] = options
		return c

	columns = [
		col("Shipping Insurance", "name", "Link", "Shipping Insurance", 140),
		col("Date", "posting_date", "Date", width=90),
		col("Insurance Company", "insurance_company", width=150),
		col("Policy Number", "policy_number", width=120),
		col("Letter of Credit", "letter_of_credit", "Link", "Letter of Credit", 130),
		col("LC No.", "lc_no", width=110),
		col("PO No.", "purchase_order", "Link", "Purchase Order", 130),
		col("Supplier", "supplier_name", width=150),
		col("Shipping Document", "shipping_document", "Link", "Shipping Document", 130),
		col("BL / AWB No.", "bl_awb_no", width=110),
		col("Vessel", "vessel_name", width=110),
		col("ETA", "eta", "Date", width=90),
		col("Port Of Loading", "port_of_loading", width=110),
		col("Port Of Discharge", "port_of_discharge", width=110),
	]
	if show_items:
		columns += [
			col("Item", "item_code", "Link", "Item", 130),
			col("Qty", "qty", "Float", width=80),
			col("Item Amount", "item_amount", "Currency", "invoice_currency", 120),
			col("Item Insurance", "item_insurance", "Currency", "currency", 120),
		]
	columns += [
		col("Invoice Currency", "invoice_currency", "Link", "Currency", 70),
		col("Invoice Value in FC", "invoice_value_fc", "Currency", "invoice_currency", 130),
		col("Policy Currency", "currency", "Link", "Currency", 70),
		col("Insurance Total Policy", "insurance_total_policy", "Currency", "currency", 130),
		col("Insurance Amount", "insurance_amount", "Currency", "currency", 120),
		col("Premium (PKR)", "base_premium_amount", "Currency", width=120),
		col("Balance Insurance", "balance_insurance", "Currency", "currency", 130),
		col("Status", "status", width=120),
	]

	conditions = {"docstatus": 1}
	for f in ("company", "letter_of_credit", "purchase_order", "supplier", "shipping_document", "policy_number",
			  "status"):
		if filters.get(f):
			conditions[f] = filters.get(f)
	if filters.get("insurance_company"):
		conditions["insurance_company"] = ["like", f"%{filters.insurance_company}%"]
	if filters.get("from_date") and filters.get("to_date"):
		conditions["posting_date"] = ["between", [filters.from_date, filters.to_date]]

	docs = frappe.get_all("Shipping Insurance", filters=conditions, order_by="posting_date desc, name desc",
						  fields=["name", "posting_date", "insurance_company", "policy_number", "letter_of_credit",
								  "lc_no", "purchase_order", "supplier_name", "shipping_document", "bl_awb_no",
								  "vessel_name", "eta", "port_of_loading", "port_of_discharge", "invoice_currency",
								  "invoice_value_fc", "currency", "insurance_total_policy", "insurance_amount",
								  "base_premium_amount", "balance_insurance", "status"])
	if not show_items:
		return columns, docs

	data = []
	items = frappe.get_all("Shipping Insurance Item", filters={"parent": ["in", [d.name for d in docs] or [""]]},
						   fields=["parent", "item_code", "qty", "amount", "insurance_amount"], order_by="idx")
	by_parent = {}
	for it in items:
		by_parent.setdefault(it.parent, []).append(it)
	for d in docs:
		for it in by_parent.get(d.name, []):
			row = dict(d)
			row.update({"item_code": it.item_code, "qty": it.qty, "item_amount": it.amount,
						"item_insurance": it.insurance_amount})
			data.append(row)
	return columns, data
