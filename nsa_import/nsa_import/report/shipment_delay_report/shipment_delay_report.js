frappe.query_reports["Shipment Delay Report"] = {
	filters: [
		{ fieldname: "shipping_document", label: __("Shipping Document"), fieldtype: "Link", options: "Shipping Document" },
		{ fieldname: "supplier", label: __("Supplier"), fieldtype: "Link", options: "Supplier" },
	],
};
