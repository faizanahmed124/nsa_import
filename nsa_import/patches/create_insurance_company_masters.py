"""Insurance Company became a Link: create master records for names already typed on LCs / Shipping Insurance."""

import frappe


def execute():
	if not frappe.db.table_exists("Insurance Company"):
		return
	names = set()
	for doctype in ("Letter of Credit", "Shipping Insurance"):
		if frappe.db.table_exists(doctype) and frappe.db.has_column(doctype, "insurance_company"):
			names.update(n.strip() for n in frappe.get_all(doctype, filters={"insurance_company": ["is", "set"]},
														   pluck="insurance_company", distinct=True) if n and n.strip())
	for name in sorted(names):
		if not frappe.db.exists("Insurance Company", name):
			frappe.get_doc({"doctype": "Insurance Company", "insurance_company": name}).insert(ignore_permissions=True)
