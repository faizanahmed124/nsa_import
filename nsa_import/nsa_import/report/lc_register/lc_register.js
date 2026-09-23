frappe.query_reports["LC Register"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.add_months(frappe.datetime.get_today(), -12) },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "supplier", label: __("Supplier"), fieldtype: "Link", options: "Supplier" },
		{ fieldname: "issuing_bank", label: __("Issuing Bank"), fieldtype: "Link", options: "Bank" },
		{ fieldname: "status", label: __("Status"), fieldtype: "Select",
		  options: "\nOpened\nAmended\nPartially Shipped\nFully Shipped\nPartially Retired\nRetired\nExpired\nClosed" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "days_to_expiry" && data && data.days_to_expiry !== null && data.days_to_expiry <= 15) {
			value = "<span style='color:red;font-weight:bold'>" + value + "</span>";
		}
		return value;
	},
};
