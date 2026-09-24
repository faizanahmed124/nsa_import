from frappe import _


def get_data():
	return {
		"fieldname": "shipping_insurance",
		"internal_links": {
			"Letter of Credit": "letter_of_credit",
			"Shipping Document": "shipping_document",
			"Purchase Order": "purchase_order",
		},
		"transactions": [
			{"label": _("Source"), "items": ["Purchase Order", "Letter of Credit", "Shipping Document"]},
		],
	}
