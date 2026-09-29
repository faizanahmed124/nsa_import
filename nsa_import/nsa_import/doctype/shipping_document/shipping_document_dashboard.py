from frappe import _


def get_data():
	return {
		"fieldname": "import_shipment",
		"non_standard_fieldnames": {
			"Shipping Insurance": "shipping_document",
			"Duty Calculation": "shipping_document",
			"Shipment Check And Delays": "shipping_document",
			"Freight Bill": "shipping_document",
			"Transporter Bill": "shipping_document",
		},
		"transactions": [
			{"label": _("Shipment"), "items": ["Shipment Check And Delays", "Duty Calculation", "Shipping Insurance"]},
			{"label": _("Bills"), "items": ["Freight Bill", "Transporter Bill"]},
			{"label": _("Clearance & Receipt"), "items": ["Customs Clearance", "Purchase Receipt"]},
			{"label": _("Costing & Settlement"), "items": ["Import Cost Sheet", "LC Retirement", "Purchase Invoice"]},
		],
	}
