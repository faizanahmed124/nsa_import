"""Transporter Bill - transporter billing and deductions of an import shipment (created from Duty Calculation).

Sales Tax (Transport)  = Total Bill Amount x Sales Tax %
Gross Bill             = Total Bill Amount + Sales Tax (Transport)
Income Tax (Transport) = Gross Bill x Income Tax %                    (withheld)
Net Bill Amount        = Gross Bill - Income Tax - Other Deduction
                         - Sales Tax as well when NSA Import Settings -> 'Deduct Sales Tax (Transport)' is ticked
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from nsa_import.utils import get_settings


def set_links_from_sources(doc):
	"""Duty Calculation -> Shipping Document -> Purchase Order, kept consistent on every save (draft only)."""
	if doc.docstatus != 0:
		return
	if doc.duty_calculation:
		dc = frappe.db.get_value("Duty Calculation", doc.duty_calculation,
								 ["docstatus", "shipping_document", "purchase_order", "company"], as_dict=True)
		if not dc or dc.docstatus == 2:
			frappe.throw(_("Duty Calculation {0} is not valid.").format(doc.duty_calculation))
		doc.shipping_document = dc.shipping_document
		doc.purchase_order = dc.purchase_order
		doc.company = dc.company
	if doc.shipping_document:
		sd = frappe.db.get_value("Shipping Document", doc.shipping_document,
								 ["purchase_order", "company"], as_dict=True) or frappe._dict()
		if doc.purchase_order and sd.purchase_order and doc.purchase_order != sd.purchase_order:
			frappe.throw(_("Purchase Order must match Shipping Document {0} ({1}).")
						 .format(doc.shipping_document, sd.purchase_order))
		doc.purchase_order = doc.purchase_order or sd.purchase_order
		doc.company = doc.company or sd.company
	if doc.purchase_order and not doc.company:
		doc.company = frappe.db.get_value("Purchase Order", doc.purchase_order, "company")
	if doc.purchase_order and frappe.db.get_value("Purchase Order", doc.purchase_order, "purchase_type") != "Import":
		frappe.throw(_("Purchase Order {0} is not an Import Purchase Order.").format(doc.purchase_order))


class TransporterBill(Document):
	def validate(self):
		set_links_from_sources(self)
		for f in ("total_bill_amount", "sales_tax_percent", "income_tax_percent", "other_deduction", "gross_weight",
				  "net_weight", "cbm"):
			if flt(self.get(f)) < 0:
				frappe.throw(_("{0} cannot be negative.").format(_(self.meta.get_label(f))))
		if (self.container_20 or 0) < 0 or (self.container_40 or 0) < 0:
			frappe.throw(_("Container counts cannot be negative."))
		for f in ("sales_tax_percent", "income_tax_percent"):
			if flt(self.get(f)) > 100:
				frappe.throw(_("{0} cannot be more than 100.").format(_(self.meta.get_label(f))))
		self.calculate()

	def calculate(self):
		self.sales_tax_amount = flt(flt(self.total_bill_amount) * flt(self.sales_tax_percent) / 100, 2)
		self.gross_bill = flt(flt(self.total_bill_amount) + self.sales_tax_amount, 2)
		self.income_tax_amount = flt(self.gross_bill * flt(self.income_tax_percent) / 100, 2)
		net = self.gross_bill - self.income_tax_amount - flt(self.other_deduction)
		if get_settings().withhold_transport_sales_tax:
			net -= self.sales_tax_amount
		self.net_bill_amount = flt(net, 2)
		if self.net_bill_amount < 0:
			frappe.throw(_("Deductions are more than the Gross Bill."))
