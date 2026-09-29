from frappe import _


def get_data():
	return {
		"fieldname": "duty_calculation",
		"internal_links": {"Shipping Document": "shipping_document", "Purchase Order": "purchase_order",
						   "Letter of Credit": "letter_of_credit"},
		"transactions": [
			{"label": _("Source"), "items": ["Purchase Order", "Letter of Credit", "Shipping Document"]},
			{"label": _("Bills"), "items": ["Freight Bill", "Transporter Bill"]},
		],
	}
