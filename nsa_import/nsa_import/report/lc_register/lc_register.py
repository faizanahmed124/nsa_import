import frappe
from frappe import _
from frappe.utils import date_diff, flt, nowdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = [
		{"label": _("Letter of Credit"), "fieldname": "name", "fieldtype": "Link", "options": "Letter of Credit", "width": 140},
		{"label": _("LC No."), "fieldname": "lc_no", "fieldtype": "Data", "width": 120},
		{"label": _("LC Date"), "fieldname": "lc_date", "fieldtype": "Date", "width": 95},
		{"label": _("LC Type"), "fieldname": "lc_type", "fieldtype": "Data", "width": 90},
		{"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 150},
		{"label": _("Purchase Order"), "fieldname": "purchase_order", "fieldtype": "Link", "options": "Purchase Order", "width": 140},
		{"label": _("Issuing Bank"), "fieldname": "issuing_bank", "fieldtype": "Link", "options": "Bank", "width": 130},
		{"label": _("Currency"), "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "width": 70},
		{"label": _("LC Amount"), "fieldname": "lc_amount", "fieldtype": "Currency", "options": "currency", "width": 120},
		{"label": _("Shipped"), "fieldname": "shipped_amount", "fieldtype": "Currency", "options": "currency", "width": 120},
		{"label": _("Retired"), "fieldname": "retired_amount", "fieldtype": "Currency", "options": "currency", "width": 120},
		{"label": _("Balance"), "fieldname": "balance_amount", "fieldtype": "Currency", "options": "currency", "width": 120},
		{"label": _("Margin (Co. Ccy)"), "fieldname": "margin_amount", "fieldtype": "Currency", "width": 120},
		{"label": _("Latest Shipment"), "fieldname": "latest_shipment_date", "fieldtype": "Date", "width": 100},
		{"label": _("Expiry"), "fieldname": "expiry_date", "fieldtype": "Date", "width": 95},
		{"label": _("Days to Expiry"), "fieldname": "days_to_expiry", "fieldtype": "Int", "width": 100},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 120},
	]
	conditions = {"docstatus": 1}
	for f in ("company", "supplier", "issuing_bank", "status"):
		if filters.get(f):
			conditions[f] = filters.get(f)
	if filters.from_date and filters.to_date:
		conditions["lc_date"] = ["between", [filters.from_date, filters.to_date]]
	data = frappe.get_all("Letter of Credit", filters=conditions, order_by="expiry_date asc",
						  fields=["name", "lc_no", "lc_date", "lc_type", "supplier", "purchase_order", "issuing_bank",
								  "currency", "lc_amount", "shipped_amount", "retired_amount", "balance_amount",
								  "margin_amount", "latest_shipment_date", "expiry_date", "status"])
	today = nowdate()
	for d in data:
		active = d.status not in ("Retired", "Closed", "Fully Shipped")
		d.days_to_expiry = date_diff(d.expiry_date, today) if d.expiry_date and active else None
	return columns, data
