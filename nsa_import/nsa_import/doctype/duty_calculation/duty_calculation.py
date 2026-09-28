"""Duty Calculation - item-wise customs duty / tax working for a Shipping Document.

Item formulas (PKR unless stated):
  Foreign Currency Value = Shipped QTY x Rate                              (FCY)
  CF Value FCY           = Foreign Currency Value (editable, e.g. to add freight in FCY)
  CF Value PKR           = CF Value FCY x Exchange Rate
  Insurance Amount       = entered, or 1% of CF Value PKR when left empty
  Landing Charges        = (CF Value PKR + Freight + Insurance) x Landing % (NSA Import Settings, default 1%)
  DV Value               = CF Value PKR + Freight + Insurance + Landing Charges
  Import Value           = higher of DV Value and Scan / AV Value
  Custom Duty, ACD, Regulatory Duty, Anti Dumping Duty = Import Value x Applied rate
  Value for Sales Tax    = Import Value + Custom Duty + ACD + Regulatory Duty + Anti Dumping Duty
  Sales Tax, Additional Sales Tax = Value for Sales Tax x Applied rate
  Income Tax             = (Value for Sales Tax + Sales Tax + Additional Sales Tax) x Applied rate
  Excise Charges         = Import Value x Excise Charges Percentage
  Total Duty and Taxes   = all duties and taxes + Excise Charges + Stamp Charges

Header:
  Total Import Value / Total Duty and Taxes = sums of the items
  Duty Amount            = Total Duty and Taxes
  Total Duty Amount HC   = Duty Amount + Cess and Token
  Total                  = Total Duty Amount HC + DO + Yard + Security Deposit + Other
  Containers             = Container Size 20 + Container size 40
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from nsa_import.utils import get_settings

ON_IMPORT_VALUE = ("custom_duty", "acd", "regulatory_duty", "anti_dumping_duty")
SALES_TAXES = ("sales_tax", "additional_sales_tax")
ALL_DUTIES = ON_IMPORT_VALUE + SALES_TAXES + ("income_tax",)
DEFAULT_INSURANCE_PERCENT = 1.0


class DutyCalculation(Document):
	def validate(self):
		self.set_source_values()
		self.calculate()

	def set_source_values(self):
		sd = frappe.db.get_value("Shipping Document", self.shipping_document,
								 ["docstatus", "purchase_order", "letter_of_credit", "lc_no", "supplier", "company"],
								 as_dict=True)
		if not sd or sd.docstatus != 1:
			frappe.throw(_("Shipping Document {0} must be submitted.").format(self.shipping_document))
		if frappe.db.get_value("Purchase Order", sd.purchase_order, "purchase_type") != "Import":
			frappe.throw(_("Duty Calculation is only for the Import flow."))
		if self.docstatus == 0:
			self.update({"purchase_order": sd.purchase_order, "letter_of_credit": sd.letter_of_credit,
						 "lc_no": sd.lc_no, "supplier": sd.supplier, "company": sd.company})

	def calculate(self):
		landing_pct = flt(get_settings().landing_charges_percent)
		default_rate = flt(frappe.db.get_value("Shipping Document", self.shipping_document, "exchange_rate")) or 1
		for d in self.items:
			self.calculate_item(d, landing_pct, default_rate)

		self.total_import_value = flt(sum(flt(d.import_value) for d in self.items), 2)
		self.total_duty_and_taxes = flt(sum(flt(d.total_duty_and_taxes) for d in self.items), 2)
		self.containers = (self.container_20 or 0) + (self.container_40 or 0)
		for f in ("cess_and_token", "do_amount", "yard_amount", "security_deposit_amount", "other_amount", "weight_kg",
				  "qty"):
			if flt(self.get(f)) < 0:
				frappe.throw(_("{0} cannot be negative.").format(_(self.meta.get_label(f))))
		if (self.container_20 or 0) < 0 or (self.container_40 or 0) < 0:
			frappe.throw(_("Container counts cannot be negative."))
		self.duty_amount = self.total_duty_and_taxes
		self.total_duty_amount_hc = flt(self.duty_amount + flt(self.cess_and_token), 2)
		self.total = flt(self.total_duty_amount_hc + flt(self.do_amount) + flt(self.yard_amount)
						 + flt(self.security_deposit_amount) + flt(self.other_amount), 2)

	@staticmethod
	def calculate_item(d, landing_pct, default_rate):
		for f in ("shipped_qty", "rate", "freight_amount", "insurance_amount", "scan_av_value", "stamp_charges",
				  "excise_charges_percent", "cf_value_fcy"):
			if flt(d.get(f)) < 0:
				frappe.throw(_("Row {0}: {1} cannot be negative.").format(d.idx, f.replace("_", " ").title()))
		for key in ALL_DUTIES:
			if flt(d.get(f"{key}_percent")) < 0 or flt(d.get(f"applied_{key}_rate")) < 0:
				frappe.throw(_("Row {0}: duty / tax rates cannot be negative.").format(d.idx))

		d.exchange_rate = flt(d.exchange_rate) or default_rate
		d.foreign_currency_value = flt(flt(d.shipped_qty) * flt(d.rate), 2)
		if not flt(d.cf_value_fcy):
			d.cf_value_fcy = d.foreign_currency_value
		d.cf_value_pkr = flt(flt(d.cf_value_fcy) * flt(d.exchange_rate), 2)
		if not flt(d.insurance_amount):
			d.insurance_amount = flt(d.cf_value_pkr * DEFAULT_INSURANCE_PERCENT / 100, 2)
		cif = d.cf_value_pkr + flt(d.freight_amount) + flt(d.insurance_amount)
		d.landing_charges = flt(cif * landing_pct / 100, 2)
		d.dv_value = flt(cif + d.landing_charges, 2)
		d.import_value = max(flt(d.dv_value), flt(d.scan_av_value))

		def amount(base, key):
			value = flt(base * flt(d.get(f"applied_{key}_rate")) / 100, 2)
			d.set(f"total_{key}", value)
			return value

		duties = sum(amount(d.import_value, k) for k in ON_IMPORT_VALUE)
		value_for_st = d.import_value + duties
		taxes = sum(amount(value_for_st, k) for k in SALES_TAXES)
		income_tax = amount(value_for_st + taxes, "income_tax")
		d.excise_charges = flt(d.import_value * flt(d.excise_charges_percent) / 100, 2)
		d.total_duty_and_taxes = flt(duties + taxes + income_tax + d.excise_charges + flt(d.stamp_charges), 2)
