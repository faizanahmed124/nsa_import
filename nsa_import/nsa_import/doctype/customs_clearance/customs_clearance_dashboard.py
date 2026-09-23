from frappe import _


def get_data():
	return {
		"fieldname": "customs_clearance",
		"transactions": [{"label": _("Receipt & Costing"), "items": ["Purchase Receipt", "Import Cost Sheet", "Purchase Invoice"]}],
	}
