"""Custom fields / property setters that extend ERPNext Purchase Order into the
NSA Local / Import Purchase Order, plus downstream documents."""

import re

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
FOREIGN_CCY = "eval:doc.currency && flt(doc.conversion_rate) != 1"
LC_REQUIRED = "eval:doc.purchase_type=='Import' && (doc.import_payment_term||'').toUpperCase().indexOf('LC')===0"
CHILD_IMPORT = "eval:parent.purchase_type=='Import'"
COMPANY_CCY = "Company:company:default_currency"
PO_SERIES = ["LPO-.YYYY.-", "IPO-.YYYY.-"]


def after_install():
	setup()


def after_migrate():
	setup()


def setup():
	"""Create custom fields doctype by doctype, so one failing doctype does not block the others.

	Run manually to see the result:  bench --site <site> execute nsa_import.install.setup
	"""
	errors = []
	for doctype, fields in get_custom_fields().items():
		if not frappe.db.exists("DocType", doctype):
			errors.append(f"{doctype}: DocType not found (skipped)")
			continue
		clashes = _clashing_user_fields(doctype, fields)
		if clashes:
			errors.append(f"{doctype}: other fields already use these labels, check for duplicates: {', '.join(clashes)}")
		try:
			create_custom_fields({doctype: fields}, update=True)
			frappe.db.commit()
		except Exception as e:
			frappe.db.rollback()
			errors.append(f"{doctype}: {e}")
			frappe.log_error(title=f"NSA Import: custom fields for {doctype}", message=frappe.get_traceback())
	try:
		if frappe.db.has_column("Purchase Order", "po_amount_pkr"):
			frappe.db.sql("""update `tabPurchase Order`
				set po_amount_fc = grand_total, po_currency = currency, po_conversion_rate = conversion_rate,
					po_amount_pkr = base_grand_total
				where ifnull(po_amount_pkr, 0) = 0 and docstatus < 2""")
			frappe.db.commit()
	except Exception as e:
		errors.append(f"PKR amounts on Purchase Order: {e}")
	try:
		removed = remove_import_details_tab() + remove_duplicate_po_fields()
		if removed:
			print("NSA Import: removed Purchase Order fields: " + ", ".join(removed))
	except Exception as e:
		errors.append(f"Removing old / duplicate Purchase Order fields: {e}")
		frappe.log_error(title="NSA Import: remove PO fields", message=frappe.get_traceback())
	try:
		make_property_setters()
	except Exception as e:
		errors.append(f"Property setters: {e}")
		frappe.log_error(title="NSA Import: property setters", message=frappe.get_traceback())
	try:
		from nsa_import.grn import sync as sync_grn

		sync_grn()
	except Exception as e:
		errors.append(f"GRN labels: {e}")
		frappe.log_error(title="NSA Import: GRN labels", message=frappe.get_traceback())
	frappe.clear_cache()

	print("NSA Import: custom fields synced." if not errors else "NSA Import: finished with warnings:")
	for msg in errors:
		print("  - " + msg)
	return errors


def _clashing_user_fields(doctype, fields):
	"""Labels of our fields that also exist on another (e.g. manually created custom_...) field."""
	ours = {df["fieldname"] for df in fields}
	labels = {(df.get("label") or "").strip().lower(): df["fieldname"] for df in fields
			  if df.get("label") and df.get("fieldtype") not in ("Section Break", "Column Break", "Tab Break")}
	others = frappe.get_all("Custom Field", filters={"dt": doctype}, fields=["fieldname", "label"])
	return sorted({f"{o.label} ({o.fieldname})" for o in others
				   if o.fieldname not in ours and (o.label or "").strip().lower() in labels})


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
			F("add_percent", "Percent", "Anti Dumping Duty %"),
			F("excise_percent", "Percent", "Excise Charges %"),
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
			F("nsa_pkr_section", "Section Break", "Amount in PKR", depends_on=FOREIGN_CCY),
			F("po_amount_fc", "Currency", "PO Amount", "currency", read_only=1, no_copy=1),
			F("po_currency", "Link", "Currency", "Currency", read_only=1, no_copy=1),
			F("nsa_pkr_cb", "Column Break"),
			F("po_conversion_rate", "Float", "Conversion Rate", read_only=1, no_copy=1, precision="9"),
			F("po_amount_pkr", "Currency", "Amount (PKR)", COMPANY_CCY, read_only=1, no_copy=1, bold=1,
			  description="PO Amount x Conversion Rate (Grand Total in company currency)"),
		],
		before_section_of(po, "currency", "schedule_date"),
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


# ----------------------------------------------------------------------------
# Purchase Order clean-up: old "Import Details" tab and duplicate (manually created) fields
# ----------------------------------------------------------------------------
REMOVED_PO_FIELDS = (
	"nsa_import_tab", "nsa_shipping_section", "port_of_loading", "port_of_discharge", "import_country_of_origin",
	"nsa_shipping_cb", "shipment_booking_no", "expected_shipment_date", "expected_arrival_date", "nsa_lc_section",
	"lc_no", "lc_date", "letter_of_credit", "nsa_lc_cb", "lc_bank", "supplier_bank", "nsa_freight_section",
	"freight_currency", "freight_amount", "insurance_amount", "nsa_freight_cb", "customs_clearing_agent",
	"nsa_costing_section", "est_freight", "est_insurance", "est_customs_duty", "est_import_taxes", "nsa_costing_cb",
	"est_clearing_charges", "est_port_charges", "est_other_import_expenses", "estimated_landed_cost",
	"nsa_import_remarks_section", "import_remarks",
)

# label of a manually created field -> NSA Import field it duplicates
DUPLICATE_ALIASES = {
	"purchase type": "purchase_type",
	"pi no": "pi_no", "pi number": "pi_no", "proforma invoice no": "pi_no",
	"pi date": "pi_date", "proforma invoice date": "pi_date",
	"department": "department",
	"payment term": "import_payment_term", "payment terms": "import_payment_term",
	"voucher number": "voucher_number", "voucher no": "voucher_number",
	"mode of shipment": "mode_of_shipment",
	"shipping term": "shipping_term", "incoterm": "shipping_term",
}


def _norm(label):
	return " ".join(re.sub(r"[^a-z0-9]+", " ", (label or "").lower()).split())


def remove_import_details_tab():
	removed = []
	for fieldname in REMOVED_PO_FIELDS:
		name = f"Purchase Order-{fieldname}"
		if frappe.db.exists("Custom Field", name):
			frappe.delete_doc("Custom Field", name, ignore_permissions=True)
			removed.append(fieldname)
	frappe.db.commit()
	return removed


def _copy_values(doctype, old, target):
	"""Copy data from a duplicate field into the NSA Import field where that is still empty."""
	table = f"tab{doctype}"
	if not (frappe.db.has_column(doctype, old.fieldname) and frappe.db.has_column(doctype, target.fieldname)):
		return
	same_kind = old.fieldtype == target.fieldtype or (target.fieldtype == "Select" and old.fieldtype in ("Select", "Data"))
	if not same_kind:
		return
	condition = ""
	values = {}
	if target.fieldtype == "Select":
		options = [o for o in (target.options or "").split("\n") if o]
		if not options:
			return
		condition = f" and `{old.fieldname}` in %(options)s"
		values["options"] = options
	if target.fieldtype == "Link" and target.options:
		condition = f" and `{old.fieldname}` in (select name from `tab{target.options}`)"
	frappe.db.sql(
		f"""update `{table}` set `{target.fieldname}` = `{old.fieldname}`
		where ifnull(`{target.fieldname}`, '') = '' and ifnull(`{old.fieldname}`, '') != ''{condition}""", values)


def remove_duplicate_po_fields():
	"""Delete manually created Purchase Order fields that duplicate NSA Import fields (data is copied first).

	The database columns are not dropped, so no data is lost.
	"""
	doctype = "Purchase Order"
	ours = {df["fieldname"] for df in get_custom_fields().get(doctype, [])}
	meta = frappe.get_meta(doctype)
	removed = []
	for cf in frappe.get_all("Custom Field", filters={"dt": doctype},
							 fields=["name", "fieldname", "label", "fieldtype", "options"]):
		if cf.fieldname in ours:
			continue
		target_name = DUPLICATE_ALIASES.get(_norm(cf.label))
		target = meta.get_field(target_name) if target_name else None
		if not target:
			continue
		try:
			_copy_values(doctype, cf, target)
		except Exception:
			frappe.log_error(title=f"NSA Import: copy {cf.fieldname} -> {target_name}", message=frappe.get_traceback())
		frappe.delete_doc("Custom Field", cf.name, ignore_permissions=True)
		removed.append(f"{cf.label} ({cf.fieldname})")
	frappe.db.commit()
	frappe.clear_cache(doctype=doctype)
	return removed
