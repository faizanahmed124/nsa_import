from frappe import _


def get_data():
	return {
		"fieldname": "import_shipment",
		"non_standard_fieldnames": {"Shipping Insurance": "shipping_document"},
		"transactions": [
			{"label": _("Insurance"), "items": ["Shipping Insurance"]},
			{"label": _("Clearance & Receipt"), "items": ["Customs Clearance", "Purchase Receipt"]},
			{"label": _("Costing & Settlement"), "items": ["Import Cost Sheet", "LC Retirement", "Purchase Invoice"]},
		],
	}
