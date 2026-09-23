import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = [
		{"label": _("Purchase Type"), "fieldname": "purchase_type", "fieldtype": "Data", "width": 110},
		{"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 200},
		{"label": _("Orders"), "fieldname": "orders", "fieldtype": "Int", "width": 80},
		{"label": _("Amount (Company Currency)"), "fieldname": "amount", "fieldtype": "Currency", "width": 170},
		{"label": _("Est. Landed Cost"), "fieldname": "landed", "fieldtype": "Currency", "width": 150},
		{"label": _("Avg % Received"), "fieldname": "per_received", "fieldtype": "Percent", "width": 120},
		{"label": _("Avg % Billed"), "fieldname": "per_billed", "fieldtype": "Percent", "width": 110},
	]
	cond = ["docstatus = 1"]
	for f in ("company", "supplier", "purchase_type"):
		if filters.get(f):
			cond.append(f"{f} = %({f})s")
	if filters.from_date and filters.to_date:
		cond.append("transaction_date between %(from_date)s and %(to_date)s")
	data = frappe.db.sql(
		f"""select ifnull(purchase_type, 'Local') as purchase_type, supplier, count(name) as orders,
			sum(base_grand_total) as amount, sum(ifnull(estimated_landed_cost, 0)) as landed,
			avg(per_received) as per_received, avg(per_billed) as per_billed
		from `tabPurchase Order` where {' and '.join(cond)}
		group by ifnull(purchase_type, 'Local'), supplier order by purchase_type, amount desc""",
		filters, as_dict=True,
	)
	totals = {}
	for d in data:
		totals[d.purchase_type] = totals.get(d.purchase_type, 0) + flt(d.amount)
	chart = {
		"data": {"labels": list(totals.keys()), "datasets": [{"name": _("Amount"), "values": list(totals.values())}]},
		"type": "bar",
	}
	return columns, data, None, chart
