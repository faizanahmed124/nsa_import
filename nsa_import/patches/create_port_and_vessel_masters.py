"""Port of Loading / Port of Discharge / Vessel Name became Link fields: create master records for the values
already typed on Letters of Credit, Shipping Documents, Shipping Insurance and Duty Calculation, and move the old
Shipping Document 'vessel_flight_no' text into the new 'vessel_name' link."""

import frappe

SOURCES = {
	"Port Of Loading": ("port", [("Letter of Credit", "port_of_loading"), ("Shipping Document", "port_of_loading"),
								 ("Shipping Insurance", "port_of_loading")]),
	"Port Of Discharge": ("port", [("Letter of Credit", "port_of_discharge"), ("Shipping Document", "port_of_discharge"),
								   ("Shipping Insurance", "port_of_discharge"), ("Duty Calculation", "clearance_port")]),
	"Clearing Agent": ("clearing_agent_name", [("Shipping Document", "clearing_agent"),
											   ("Customs Clearance", "clearing_agent")]),
	"Vessel Name": ("vessel_name", [("Shipping Document", "vessel_flight_no"), ("Shipping Document", "vessel_name"),
									("Shipping Insurance", "vessel_name")]),
}


def execute():
	if frappe.db.table_exists("Shipping Document") and frappe.db.has_column("Shipping Document", "vessel_flight_no") \
			and frappe.db.has_column("Shipping Document", "vessel_name"):
		frappe.db.sql("""update `tabShipping Document` set vessel_name = trim(vessel_flight_no)
			where ifnull(vessel_name, '') = '' and ifnull(vessel_flight_no, '') != ''""")

	for master, (field, sources) in SOURCES.items():
		if not frappe.db.table_exists(master):
			continue
		values = set()
		for doctype, column in sources:
			if frappe.db.table_exists(doctype) and frappe.db.has_column(doctype, column):
				frappe.db.sql(f"update `tab{doctype}` set `{column}` = trim(`{column}`) where `{column}` != trim(`{column}`)")
				values.update(v[0].strip() for v in frappe.db.sql(
					f"select distinct `{column}` from `tab{doctype}` where ifnull(`{column}`, '') != ''") if v[0].strip())
		for value in sorted(values):
			if not frappe.db.exists(master, value):
				doc = frappe.get_doc({"doctype": master, field: value})
				doc.flags.ignore_validate = True
				doc.insert(ignore_permissions=True, ignore_if_duplicate=True)
