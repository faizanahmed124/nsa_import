import frappe
from frappe import _
from frappe.utils import cint, flt

from nsa_import.utils import get_company_currency, get_settings, is_lc_payment_term

IMPORT_MANDATORY = (
	("mode_of_shipment", "Mode of Shipment"),
	("pi_no", "PI No."),
	("pi_date", "PI Date"),
	("shipping_term", "Shipping Term"),
	("import_payment_term", "Payment Term (Import)"),
)
EST_FIELDS = (
	"est_freight", "est_insurance", "est_customs_duty", "est_import_taxes",
	"est_clearing_charges", "est_port_charges", "est_other_import_expenses",
)


def validate(doc, method=None):
	if not doc.get("purchase_type"):
		doc.purchase_type = "Local"
	validate_exchange_rate(doc)
	if doc.purchase_type == "Import":
		validate_import_mandatory(doc)
		validate_hs_codes(doc)
	calculate_import_estimates(doc)


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
	if is_lc_payment_term(doc.get("import_payment_term")):
		if not doc.get("lc_no"):
			missing.append(_("LC No."))
		if not doc.get("lc_date"):
			missing.append(_("LC Date"))
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
	if doc.purchase_type != "Import":
		for d in doc.items:
			d.final_cost = flt(d.base_net_rate)
		doc.estimated_landed_cost = 0
		return

	rate = flt(doc.conversion_rate) or 1
	item_freight = sum(flt(d.get("item_freight")) for d in doc.items)
	item_insurance = sum(flt(d.get("item_insurance")) for d in doc.items)

	if flt(doc.get("freight_amount")):
		doc.est_freight = _to_company_currency(doc, doc.freight_amount, doc.get("freight_currency"))
	elif item_freight:
		doc.est_freight = item_freight * rate

	if flt(doc.get("insurance_amount")):
		doc.est_insurance = flt(doc.insurance_amount) * rate
	elif item_insurance:
		doc.est_insurance = item_insurance * rate

	charges = sum(flt(doc.get(f)) for f in EST_FIELDS)
	doc.estimated_landed_cost = flt(flt(doc.base_net_total) + charges, doc.precision("base_net_total"))

	total = flt(doc.base_net_total)
	for d in doc.items:
		share = charges * flt(d.base_net_amount) / total if total else 0
		d.final_cost = flt((flt(d.base_net_amount) + share) / flt(d.qty), 4) if flt(d.qty) else 0
