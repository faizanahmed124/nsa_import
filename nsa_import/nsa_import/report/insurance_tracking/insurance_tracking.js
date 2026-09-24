frappe.query_reports["Insurance Tracking"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.add_months(frappe.datetime.get_today(), -12) },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "insurance_company", label: __("Insurance Company"), fieldtype: "Data" },
		{ fieldname: "policy_number", label: __("Policy Number"), fieldtype: "Data" },
		{ fieldname: "letter_of_credit", label: __("Letter of Credit"), fieldtype: "Link", options: "Letter of Credit" },
		{ fieldname: "purchase_order", label: __("Purchase Order"), fieldtype: "Link", options: "Purchase Order" },
		{ fieldname: "supplier", label: __("Supplier"), fieldtype: "Link", options: "Supplier" },
		{ fieldname: "shipping_document", label: __("Shipping Document"), fieldtype: "Link", options: "Shipping Document" },
		{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: "\nSubmitted\nPolicy Issued\nPartially Utilized\nFully Utilized" },
		{ fieldname: "show_items", label: __("Show Items"), fieldtype: "Check" },
	],
};
