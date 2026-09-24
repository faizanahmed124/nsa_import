"""Custom fields / property setters that extend ERPNext Purchase Order into the
NSA Local / Import Purchase Order, plus downstream documents."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

from nsa_import.constants import (
	IMPORT_PAYMENT_TERMS,
	LC_CHARGE_HEADS,
	MODE_OF_SHIPMENT,
	PAYMENT_METHODS,
	SHIPPING_TERMS,
)

IMPORT = "eval:doc.purchase_type=='Import'"
LOCAL = "eval:doc.purchase_type=='Local'"
LC_REQUIRED = "eval:doc.purchase_type=='Import' && (doc.import_payment_term||'').toUpperCase().indexOf('LC')===0"
CHILD_IMPORT = "eval:parent.purchase_type=='Import'"
COMPANY_CCY = "Company:company:default_currency"
PO_SERIES = ["LPO-.YYYY.-", "IPO-.YYYY.-"]


def after_install():
	setup()


def after_migrate():
	setup()


def setup():
	create_custom_fields(get_custom_fields(), update=True)
	make_property_setters()
	frappe.clear_cache()


def before_uninstall():
	for doctype, fields in get_custom_fields().items():
		for df in fields:
			name = f"{doctype}-{df['fieldname']}"
			if frappe.db.exists("Custom Field", name):
				frappe.delete_doc("Custom Field", name, ignore_permissions=True)


# ----------------------------------------------------------------------------
# helpers to place fields robustly regardless of ERPNext minor version
# ----------------------------------------------------------------------------
def _std_fields(doctype):
	return frappe.get_all(
		"DocField",
		filters={"parent": doctype, "parenttype": "DocType"},
		fields=["fieldname", "fieldtype"],
		order_by="idx asc",
	)


def before_section_of(doctype, fieldname, default):
	"""Fieldname just before the Section/Tab Break that contains `fieldname`."""
	fields = _std_fields(doctype)
	names = [f.fieldname for f in fields]
	if fieldname not in names:
		return default
	i = names.index(fieldname)
	while i > 0 and fields[i].fieldtype not in ("Section Break", "Tab Break"):
		i -= 1
	return fields[i - 1].fieldname if i > 0 else default


def before_next_tab(doctype, fieldname, default):
	"""Last fieldname of the tab containing `fieldname` (so a new tab lands right after it)."""
	fields = _std_fields(doctype)
	names = [f.fieldname for f in fields]
	if fieldname not in names:
		return default
	for j in range(names.index(fieldname) + 1, len(fields)):
		if fields[j].fieldtype == "Tab Break":
			return fields[j - 1].fieldname
	return names[-1] if names else default


def F(fieldname, fieldtype, label=None, options=None, **kw):
	d = {"fieldname": fieldname, "fieldtype": fieldtype}
	if label:
		d["label"] = label
	if options:
		d["options"] = options
	d.update(kw)
	return d


def chain(fields, first_insert_after):
	"""Set insert_after so the list is inserted in order after the anchor."""
	prev = first_insert_after
	for df in fields:
		df.setdefault("insert_after", prev)
		prev = df["fieldname"]
	return fields


# ----------------------------------------------------------------------------
# field definitions
# ----------------------------------------------------------------------------
def get_custom_fields():
	po = "Purchase Order"
	poi = "Purchase Order Item"

	fields = {}

	# Supplier (created first because PO fetches from it)
	fields["Supplier"] = [F("nsa_strn", "Data", "STRN (Sales Tax Reg. No.)", insert_after="tax_id")]

	# HS Code master with duty rates
	fields["Customs Tariff Number"] = chain(
		[
			F("nsa_duty_section", "Section Break", "Import Duty Rates"),
			F("cd_percent", "Percent", "Customs Duty %"),
			F("acd_percent", "Percent", "Additional Customs Duty %"),
			F("rd_percent", "Percent", "Regulatory Duty %"),
			F("nsa_duty_cb", "Column Break"),
			F("st_percent", "Percent", "Sales Tax %"),
			F("ast_percent", "Percent", "Additional Sales Tax %"),
			F("it_percent", "Percent", "Income Tax (Import) %"),
		],
		"description",
	)

	# ---------------- Purchase Order (parent) ----------------
	po_fields = [
		F("purchase_type", "Select", "Purchase Type", "Local\nImport", default="Local", reqd=1,
		  in_list_view=1, in_standard_filter=1, bold=1, insert_after="naming_series"),
		F("voucher_number", "Data", "Voucher Number", depends_on=LOCAL, insert_after="order_confirmation_date"),
		F("department", "Link", "Department", "Department", insert_after="company"),
	]

	po_fields += chain(
		[
			F("nsa_import_basic_section", "Section Break", "Import Information", depends_on=IMPORT),
			F("mode_of_shipment", "Select", "Mode of Shipment", MODE_OF_SHIPMENT, mandatory_depends_on=IMPORT),
			F("pi_no", "Data", "PI No.", mandatory_depends_on=IMPORT, in_standard_filter=1),
			F("pi_date", "Date", "PI Date", mandatory_depends_on=IMPORT),
			F("nsa_import_basic_cb", "Column Break"),
			F("shipping_term", "Select", "Shipping Term (Incoterm)", SHIPPING_TERMS, mandatory_depends_on=IMPORT),
			F("import_payment_term", "Select", "Payment Term (Import)", IMPORT_PAYMENT_TERMS, mandatory_depends_on=IMPORT),
			F("import_status", "Select", "Import Status",
			  "\nLC Opened\nShipped\nArrived\nCleared\nPartially Received\nReceived",
			  read_only=1, allow_on_submit=1, no_copy=1, in_standard_filter=1),
			F("per_shipped", "Percent", "% Shipped", read_only=1, allow_on_submit=1, no_copy=1),
		],
		before_section_of(po, "currency", "schedule_date"),
	)

	po_fields += chain(
		[
			F("nsa_import_tab", "Tab Break", "Import Details", depends_on=IMPORT),
			F("nsa_shipping_section", "Section Break", "Shipping & Ports"),
			F("port_of_loading", "Data", "Port of Loading"),
			F("port_of_discharge", "Data", "Port of Discharge"),
			F("import_country_of_origin", "Link", "Country of Origin", "Country"),
			F("nsa_shipping_cb", "Column Break"),
			F("shipment_booking_no", "Data", "Shipment / Booking No.", allow_on_submit=1),
			F("expected_shipment_date", "Date", "Expected Shipment Date", allow_on_submit=1),
			F("expected_arrival_date", "Date", "Expected Arrival Date", allow_on_submit=1),
			F("nsa_lc_section", "Section Break", "Letter of Credit / Bank"),
			F("lc_no", "Data", "LC No.", mandatory_depends_on=LC_REQUIRED, depends_on=LC_REQUIRED, allow_on_submit=1),
			F("lc_date", "Date", "LC Date", mandatory_depends_on=LC_REQUIRED, depends_on=LC_REQUIRED, allow_on_submit=1),
			F("letter_of_credit", "Link", "Letter of Credit", "Letter of Credit", read_only=1, allow_on_submit=1, no_copy=1),
			F("nsa_lc_cb", "Column Break"),
			F("lc_bank", "Link", "LC Bank (Issuing)", "Bank"),
			F("supplier_bank", "Small Text", "Supplier Bank Details"),
			F("nsa_freight_section", "Section Break", "Freight, Insurance & Clearing"),
			F("freight_currency", "Link", "Freight Currency", "Currency"),
			F("freight_amount", "Currency", "Freight Amount", "freight_currency"),
			F("insurance_amount", "Currency", "Insurance Amount (Transaction Currency)", "currency"),
			F("nsa_freight_cb", "Column Break"),
			F("customs_clearing_agent", "Link", "Customs / Clearing Agent", "Supplier"),
			F("nsa_costing_section", "Section Break", "Import Costing / Landed Cost Estimate (Company Currency)",
			  description="Freight & insurance are auto-filled from the fields above (or item-wise values) when entered."),
			F("est_freight", "Currency", "Freight", COMPANY_CCY),
			F("est_insurance", "Currency", "Insurance", COMPANY_CCY),
			F("est_customs_duty", "Currency", "Customs Duty", COMPANY_CCY),
			F("est_import_taxes", "Currency", "Import Taxes", COMPANY_CCY),
			F("nsa_costing_cb", "Column Break"),
			F("est_clearing_charges", "Currency", "Clearing Charges", COMPANY_CCY),
			F("est_port_charges", "Currency", "Port Charges", COMPANY_CCY),
			F("est_other_import_expenses", "Currency", "Other Import Expenses", COMPANY_CCY),
			F("estimated_landed_cost", "Currency", "Estimated Landed Cost", COMPANY_CCY, read_only=1, bold=1),
			F("nsa_import_remarks_section", "Section Break"),
			F("import_remarks", "Long Text", "Import Remarks"),
		],
		before_next_tab(po, "currency", "terms"),
	)

	# Address & Contact tab
	po_fields += chain(
		[
			F("supplier_ntn", "Data", "Tax ID / NTN", fetch_from="supplier.tax_id", fetch_if_empty=1),
			F("supplier_strn", "Data", "STRN", fetch_from="supplier.nsa_strn", fetch_if_empty=1),
			F("supplier_country", "Link", "Supplier Country", "Country", fetch_from="supplier.country", fetch_if_empty=1),
		],
		"address_display",
	)

	# Terms tab
	po_fields += chain(
		[
			F("payment_days", "Int", "Payment Days"),
			F("payment_method", "Select", "Payment Method", PAYMENT_METHODS),
		],
		"payment_terms_template",
	)
	po_fields.append(F("commercial_notes", "Long Text", "Notes", insert_after="terms"))
	fields[po] = po_fields

	# ---------------- Purchase Order Item ----------------
	fields[poi] = [
		F("item_remarks", "Small Text", "Remarks", insert_after="expected_delivery_date"),
		F("final_cost", "Currency", "Final Cost (per unit)", COMPANY_CCY, read_only=1, insert_after="last_purchase_rate",
		  description="Net rate + share of estimated import charges"),
		F("shipped_qty", "Float", "Shipped Qty", read_only=1, allow_on_submit=1, no_copy=1, insert_after="received_qty"),
	] + chain(
		[
			F("nsa_import_item_section", "Section Break", "Import Details", depends_on=CHILD_IMPORT),
			F("hs_code", "Data", "HS Code", depends_on=CHILD_IMPORT, in_list_view=1, columns=1,
			  fetch_from="item_code.customs_tariff_number", fetch_if_empty=1),
			F("item_country_of_origin", "Link", "Country of Origin", "Country",
			  fetch_from="item_code.country_of_origin", fetch_if_empty=1),
			F("net_weight", "Float", "Net Weight (line)"),
			F("gross_weight", "Float", "Gross Weight (line)"),
			F("nsa_import_item_cb", "Column Break"),
			F("item_freight", "Currency", "Item-wise Freight", "currency"),
			F("item_insurance", "Currency", "Item-wise Insurance", "currency"),
			F("import_rate", "Currency", "Import Rate", "currency"),
		],
		before_section_of(poi, "warehouse", "rate"),
	)

	# ---------------- Downstream documents keep Purchase Type ----------------
	for dt in ("Purchase Receipt", "Purchase Invoice"):
		fields[dt] = [
			F("purchase_type", "Select", "Purchase Type", "\nLocal\nImport", in_standard_filter=1,
			  in_list_view=1, insert_after="naming_series"),
		] + chain(
			[
				F("nsa_import_ref_section", "Section Break", "Import References", depends_on=IMPORT, collapsible=1),
				F("letter_of_credit", "Link", "Letter of Credit", "Letter of Credit"),
				F("import_shipment", "Link", "Shipping Document", "Shipping Document"),
				F("nsa_import_ref_cb", "Column Break"),
				F("customs_clearance", "Link", "Customs Clearance (GD)", "Customs Clearance"),
			],
			before_section_of(dt, "currency", "supplier"),
		)

	fields["Landed Cost Voucher"] = chain(
		[
			F("purchase_type", "Select", "Purchase Type", "\nLocal\nImport", in_standard_filter=1),
			F("import_cost_sheet", "Link", "Import Cost Sheet", "Import Cost Sheet", read_only=1),
		],
		"company",
	)
	# ---------------- Journal Entry -> Letter of Credit (Expense Booked) ----------------
	fields["Journal Entry"] = [
		F("letter_of_credit", "Link", "Letter of Credit", "Letter of Credit", insert_after="cheque_date",
		  in_standard_filter=1, search_index=1,
		  description="LC expense lines of this entry are copied to the LC's Expense Booked tab on submit"),
	]
	fields["Journal Entry Account"] = [
		F("nsa_lc_charge_head", "Select", "LC Charge Head", LC_CHARGE_HEADS, insert_after="user_remark",
		  depends_on="eval:parent.letter_of_credit"),
	]
	return fields


def make_property_setters():
	# Weight UOM column in the item grid (hidden for Local by client script)
	make_property_setter("Purchase Order Item", "weight_uom", "in_list_view", 1, "Check")

	# Separate naming series for Local / Import POs (existing series kept)
	df = frappe.get_meta("Purchase Order").get_field("naming_series")
	if df:
		options = [o for o in (df.options or "").split("\n") if o]
		changed = False
		for s in PO_SERIES:
			if s not in options:
				options.append(s)
				changed = True
		if changed:
			make_property_setter("Purchase Order", "naming_series", "options", "\n".join(options), "Text")
