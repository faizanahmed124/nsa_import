import frappe
from frappe import _
from frappe.utils import cint, flt

from nsa_import.utils import get_company_currency, get_settings

IMPORT_MANDATORY = (
	("mode_of_shipment", "Mode of Shipment"),
	("pi_no", "PI No."),
	("pi_date", "PI Date"),
	("shipping_term", "Shipping Term"),
	("import_payment_term", "Payment Term (Import)"),
)


def validate(doc, method=None):
	if not doc.get("purchase_type"):
		doc.purchase_type = "Local"
	validate_exchange_rate(doc)
	if doc.purchase_type == "Import":
		validate_import_mandatory(doc)
		validate_hs_codes(doc)
	calculate_import_estimates(doc)
	set_pkr_amounts(doc)


def set_pkr_amounts(doc):
	"""PO Amount (transaction currency) x Conversion Rate = Amount (PKR), shown when the PO is not in PKR."""
	doc.po_amount_fc = flt(doc.grand_total)
	doc.po_currency = doc.currency
	doc.po_conversion_rate = flt(doc.conversion_rate)
	doc.po_amount_pkr = flt(doc.base_grand_total) or flt(flt(doc.grand_total) * flt(doc.conversion_rate), 2)


def validate_exchange_rate(doc):
	company_currency = get_company_currency(doc.company)
	if doc.currency and doc.currency != company_currency:
		if flt(doc.conversion_rate) <= 0:
			frappe.throw(_("Exchange Rate is mandatory when currency ({0}) differs from company currency ({1}).")
						 .format(doc.currency, company_currency))
		if flt(doc.conversion_rate) == 1:
			frappe.msgprint(_("Exchange Rate is 1 for {0} → {1}. Please verify.").format(doc.currency, company_currency),
							indicator="orange", alert=True)


def validate_import_mandatory(doc):
	missing = [_(label) for field, label in IMPORT_MANDATORY if not doc.get(field)]
	if missing:
		frappe.throw(_("Following fields are mandatory for Import Purchase Order: {0}").format(", ".join(missing)),
					 title=_("Missing Import Information"))


def validate_hs_codes(doc):
	if not cint(get_settings().hs_code_mandatory):
		return
	missing = [
		f"Row {d.idx}: {d.item_code}"
		for d in doc.items
		if not d.get("hs_code") and cint(frappe.get_cached_value("Item", d.item_code, "is_stock_item"))
	]
	if missing:
		frappe.throw(_("HS Code is mandatory for import stock items:<br>{0}").format("<br>".join(missing)))


def _to_company_currency(doc, amount, currency):
	company_currency = get_company_currency(doc.company)
	currency = currency or doc.currency
	if not flt(amount):
		return 0.0
	if currency == company_currency:
		return flt(amount)
	if currency == doc.currency:
		return flt(amount) * flt(doc.conversion_rate)
	from erpnext.setup.utils import get_exchange_rate

	return flt(amount) * flt(get_exchange_rate(currency, company_currency, doc.transaction_date))


def calculate_import_estimates(doc):
	"""Final Cost per item (company currency): net rate + item-wise freight and insurance for Import POs."""
	rate = flt(doc.conversion_rate) or 1
	for d in doc.items:
		if doc.purchase_type != "Import" or not flt(d.qty):
			d.final_cost = flt(d.base_net_rate)
			continue
		extra = (flt(d.get("item_freight")) + flt(d.get("item_insurance"))) * rate
		d.final_cost = flt((flt(d.base_net_amount) + extra) / flt(d.qty), 4)
