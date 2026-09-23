import frappe
from frappe.utils import nowdate


def mark_expired_lcs():
	names = frappe.get_all(
		"Letter of Credit",
		filters={
			"docstatus": 1,
			"status": ["in", ["Opened", "Amended", "Partially Shipped"]],
			"expiry_date": ["<", nowdate()],
		},
		pluck="name",
	)
	for name in names:
		frappe.db.set_value("Letter of Credit", name, "status", "Expired", update_modified=False)
