from frappe import _


def get_data():
	return {
		"fieldname": "import_shipment",
		"transactions": [
			{"label": _("Clearance & Receipt"), "items": ["Customs Clearance", "Purchase Receipt"]},
			{"label": _("Costing & Settlement"), "items": ["Import Cost Sheet", "LC Retirement", "Purchase Invoice"]},
		],
	}
