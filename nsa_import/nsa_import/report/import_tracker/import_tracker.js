frappe.query_reports["Import Tracker"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.add_months(frappe.datetime.get_today(), -12) },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "supplier", label: __("Supplier"), fieldtype: "Link", options: "Supplier" },
		{ fieldname: "purchase_order", label: __("Purchase Order"), fieldtype: "Link", options: "Purchase Order",
		  get_query: () => ({ filters: { purchase_type: "Import" } }) },
		{ fieldname: "import_status", label: __("Import Status"), fieldtype: "Select",
		  options: "\nNot Started\nLC Opened\nShipped\nArrived\nCleared\nPartially Received\nReceived" },
	],
};
