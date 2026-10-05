import frappe
from frappe import _


def get_data():
	data = {
		"fieldname": "arrival_notice",
		"internal_links": {"Purchase Order": "purchase_order", "Shipping Document": "shipping_document",
						   "Letter of Credit": "letter_of_credit", "Duty Calculation": "duty_calculation"},
		"non_standard_fieldnames": {},
		"transactions": [{"label": _("Source"), "items": ["Purchase Order", "Letter of Credit", "Shipping Document",
														   "Duty Calculation"]}],
	}
	from nsa_import.utils import pr_doctype

	receiving = []
	if frappe.get_meta(pr_doctype()).has_field("arrival_notice"):
		receiving.append(pr_doctype())
	if frappe.db.exists("DocType", "Inward Gate Pass") and frappe.get_meta("Inward Gate Pass").has_field("nsa_arrival_notice"):
		data["non_standard_fieldnames"]["Inward Gate Pass"] = "nsa_arrival_notice"
		receiving.append("Inward Gate Pass")
	if receiving:
		data["transactions"].append({"label": _("Receiving"), "items": receiving})
	return data
