from frappe import _


def purchase_order_dashboard(data):
	data = data or {}
	data.setdefault("transactions", [])
	data["transactions"].append(
		{
			"label": _("Import"),
			"items": ["Letter of Credit", "Import Shipment", "Customs Clearance", "Import Cost Sheet", "LC Retirement"],
		}
	)
	return data
