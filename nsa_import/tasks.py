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


def update_insurance_policies():
	from nsa_import.nsa_import.doctype.insurance_policy.insurance_policy import update_all_policy_status

	update_all_policy_status()
