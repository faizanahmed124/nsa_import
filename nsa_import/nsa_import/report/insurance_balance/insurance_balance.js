frappe.query_reports["Insurance Balance"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "insurance_company", label: __("Insurance Company"), fieldtype: "Data" },
		{ fieldname: "letter_of_credit", label: __("Letter of Credit"), fieldtype: "Link", options: "Letter of Credit" },
		{ fieldname: "supplier", label: __("Supplier"), fieldtype: "Link", options: "Supplier" },
		{ fieldname: "only_with_balance", label: __("Only Policies with Balance"), fieldtype: "Check" },
	],
};
