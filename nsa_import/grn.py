"""Show ERPNext "Purchase Receipt" as "GRN" everywhere in the UI - without renaming the DocType.

Renaming the core DocType would break ERPNext (stock ledger, GL, Landed Cost Voucher, Purchase Invoice mapping
and reports use the name "Purchase Receipt" in code, and every ERPNext update recreates it). Instead this adds
user translations, so every label, title, breadcrumb, list, button, link field, connection and print heading that
shows "Purchase Receipt" shows "GRN", plus a GRN naming series.

Controlled by NSA Import Settings -> "Show Purchase Receipt as GRN" (default on).
Apply manually:  bench --site <site> execute nsa_import.grn.apply
Remove:          bench --site <site> execute nsa_import.grn.remove
"""

import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

GRN_SERIES = "GRN-.YYYY.-"

GRN_TRANSLATIONS = {
	"Purchase Receipt": "GRN",
	"Purchase Receipts": "GRNs",
	"Purchase Receipt Item": "GRN Item",
	"Purchase Receipt Items": "GRN Items",
	"Purchase Receipt Item Supplied": "GRN Item Supplied",
	"Purchase Receipt No": "GRN No",
	"Purchase Receipt Detail": "GRN Detail",
	"Purchase Receipt Details": "GRN Details",
	"Purchase Receipt Required": "GRN Required",
	"Purchase Receipt Trends": "GRN Trends",
	"Purchase Receipt Amount": "GRN Amount",
	"Purchase Receipt Date": "GRN Date",
	"Create Purchase Receipt": "Create GRN",
	"Make Purchase Receipt": "Make GRN",
	"New Purchase Receipt": "New GRN",
	"Purchase Receipt Series": "GRN Series",
	"Against Purchase Receipt": "Against GRN",
	"Purchase Receipt Qty": "GRN Qty",
}


def is_enabled():
	"""On by default: until NSA Import Settings are saved, the value is not stored yet."""
	row = frappe.db.sql("""select value from `tabSingles`
		where doctype='NSA Import Settings' and field='show_purchase_receipt_as_grn'""")
	return True if not row else bool(int(row[0][0] or 0))


def _languages():
	langs = {"en"}
	for lang in (frappe.db.get_default("lang"), frappe.db.get_single_value("System Settings", "language")):
		if lang:
			langs.add(lang)
	return sorted(langs)


def apply():
	created = 0
	for lang in _languages():
		for source, target in GRN_TRANSLATIONS.items():
			name = frappe.db.get_value("Translation", {"language": lang, "source_text": source}, "name")
			if name:
				if frappe.db.get_value("Translation", name, "translated_text") != target:
					frappe.db.set_value("Translation", name, "translated_text", target)
				continue
			frappe.get_doc({"doctype": "Translation", "language": lang, "source_text": source,
							"translated_text": target}).insert(ignore_permissions=True)
			created += 1
	_set_grn_series()
	frappe.db.commit()
	frappe.clear_cache()
	print(f"NSA Import: Purchase Receipt is shown as GRN ({created} translations added).")


def remove():
	for source, target in GRN_TRANSLATIONS.items():
		for name in frappe.get_all("Translation", filters={"source_text": source, "translated_text": target},
								   pluck="name"):
			frappe.delete_doc("Translation", name, ignore_permissions=True)
	frappe.db.commit()
	frappe.clear_cache()
	print("NSA Import: GRN labels removed (naming series left unchanged).")


def _set_grn_series():
	df = frappe.get_meta("Purchase Receipt").get_field("naming_series")
	if not df:
		return
	options = [o for o in (df.options or "").split("\n") if o]
	if GRN_SERIES not in options:
		make_property_setter("Purchase Receipt", "naming_series", "options", "\n".join([GRN_SERIES] + options),
							 "Text")
	make_property_setter("Purchase Receipt", "naming_series", "default", GRN_SERIES, "Text")


def sync():
	"""Called from install.setup and when NSA Import Settings are saved."""
	if is_enabled():
		apply()
	else:
		remove()
