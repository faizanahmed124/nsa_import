from frappe import _


def get_data():
	return {
		"fieldname": "transporter_bill",
		"internal_links": {"Purchase Order": "purchase_order", "Shipping Document": "shipping_document",
						   "Duty Calculation": "duty_calculation"},
		"transactions": [{"label": _("Source"), "items": ["Purchase Order", "Shipping Document", "Duty Calculation"]}],
	}
