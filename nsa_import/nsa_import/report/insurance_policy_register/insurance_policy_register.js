frappe.query_reports["Insurance Policy Register"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "insurance_company", label: __("Insurance Company"), fieldtype: "Link", options: "Insurance Company" },
		{ fieldname: "bank", label: __("Bank"), fieldtype: "Link", options: "Bank" },
		{ fieldname: "status", label: __("Policy Status"), fieldtype: "Select", options: "\nActive\nExpired\nFully Utilized\nSuspended" },
		{ fieldname: "show_utilization", label: __("Show Utilization"), fieldtype: "Check" },
	],
};
