from frappe import _


def get_data():
	return {
		"fieldname": "shipment_check_and_delays",
		"internal_links": {"Shipping Document": "shipping_document"},
		"transactions": [{"label": _("Source"), "items": ["Shipping Document"]}],
	}
