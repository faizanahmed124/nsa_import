from frappe import _


def get_data():
	return {
		"fieldname": "letter_of_credit",
		"transactions": [
			{"label": _("Shipping"), "items": ["Import Shipment", "Customs Clearance"]},
			{"label": _("Receipt & Costing"), "items": ["Purchase Receipt", "Import Cost Sheet"]},
			{"label": _("Settlement"), "items": ["LC Retirement", "Purchase Invoice"]},
			{"label": _("Accounting"), "items": ["Journal Entry"]},
		],
	}
