from frappe import _


def purchase_order_dashboard(data):
	data = data or {}
	data.setdefault("transactions", [])
	data["transactions"].append(
		{
			"label": _("Import"),
			"items": ["Letter of Credit", "Shipping Document", "Shipping Insurance", "Duty Calculation", "Arrival Notice",
					  "Import Cost Sheet", "LC Retirement"],
		}
	)
	return data


def purchase_receipt_dashboard(data):
	"""GRN connections: Arrival Notice (internal link) and Inward Gate Pass (if the gate pass app is installed)."""
	import frappe

	from nsa_import.api import igp_link_field

	data = data or {}
	data.setdefault("transactions", [])
	data.setdefault("internal_links", {})
	data.setdefault("non_standard_fieldnames", {})
	items = []
	if frappe.get_meta("Purchase Receipt").has_field("arrival_notice"):
		data["internal_links"]["Arrival Notice"] = "arrival_notice"
		items.append("Arrival Notice")
	field = igp_link_field("Purchase Receipt")
	if field:
		data["non_standard_fieldnames"]["Inward Gate Pass"] = field
		items.append("Inward Gate Pass")
	if items:
		data["transactions"].append({"label": _("Import / Gate"), "items": items})
	return data
