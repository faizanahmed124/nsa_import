from frappe import _


def get_data():
	return {
		"fieldname": "arrival_notice",
		"internal_links": {"Purchase Order": "purchase_order", "Shipping Document": "shipping_document",
						   "Letter of Credit": "letter_of_credit", "Duty Calculation": "duty_calculation"},
		"transactions": [{"label": _("Source"), "items": ["Purchase Order", "Letter of Credit", "Shipping Document",
														   "Duty Calculation"]}],
	}
