"""Shipment Delay Report - days between the milestone dates of Shipment Check And Delays (To Date - From Date)."""

import frappe
from frappe import _
from frappe.utils import date_diff

from nsa_import.nsa_import.doctype.shipment_check_and_delays.shipment_check_and_delays import MILESTONES


def execute(filters=None):
	filters = frappe._dict(filters or {})
	meta = frappe.get_meta("Shipment Check And Delays")
	columns = [
		{"label": _("Shipment Check"), "fieldname": "name", "fieldtype": "Link", "options": "Shipment Check And Delays",
		 "width": 130},
		{"label": _("Shipping Document"), "fieldname": "shipping_document", "fieldtype": "Link",
		 "options": "Shipping Document", "width": 130},
		{"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 150},
	]
	for key, _f, _t in MILESTONES:
		columns.append({"label": _(meta.get_label(f"{key}_section")) + " " + _("(Days)"), "fieldname": key,
						"fieldtype": "Int", "width": 120})

	conditions = {}
	for f in ("shipping_document", "supplier"):
		if filters.get(f):
			conditions[f] = filters.get(f)
	fields = ["name", "shipping_document", "supplier"] + [f"{k}_{s}" for k, _f, _t in MILESTONES for s in ("from", "to")]
	data = []
	for d in frappe.get_all("Shipment Check And Delays", filters=conditions, fields=fields, order_by="creation desc"):
		row = {"name": d.name, "shipping_document": d.shipping_document, "supplier": d.supplier}
		for key, _f, _t in MILESTONES:
			start, end = d.get(f"{key}_from"), d.get(f"{key}_to")
			row[key] = date_diff(end, start) if start and end else None
		data.append(row)
	return columns, data
