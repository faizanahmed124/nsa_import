import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class LCRetirement(Document):
	def validate(self):
		lc = frappe.db.get_value("Letter of Credit", self.letter_of_credit,
								 ["docstatus", "purchase_order", "supplier", "company", "currency", "exchange_rate",
								  "max_lc_amount", "lc_no"], as_dict=True)
		if not lc or lc.docstatus != 1:
			frappe.throw(_("Letter of Credit {0} must be submitted.").format(self.letter_of_credit))
		for f in ("purchase_order", "supplier", "company", "currency", "lc_no"):
			self.set(f, lc.get(f))
		if not flt(self.exchange_rate):
			self.exchange_rate = lc.exchange_rate
		if self.import_shipment and frappe.db.get_value("Import Shipment", self.import_shipment,
														"letter_of_credit") != self.letter_of_credit:
			frappe.throw(_("Import Shipment {0} is not against this LC.").format(self.import_shipment))

		other = flt(frappe.db.sql(
			"select coalesce(sum(amount),0) from `tabLC Retirement` where letter_of_credit=%s and docstatus=1 and name!=%s",
			(self.letter_of_credit, self.name))[0][0])
		if other + flt(self.amount) > flt(lc.max_lc_amount) + 0.01:
			frappe.throw(_("Total retirement {0} exceeds LC max amount {1}.")
						 .format(other + flt(self.amount), lc.max_lc_amount))

		self.base_amount = flt(flt(self.amount) * flt(self.exchange_rate), 2)
		self.net_bank_payment = flt(self.base_amount - flt(self.margin_adjusted) + flt(self.bank_charges), 2)

	def on_submit(self):
		frappe.get_doc("Letter of Credit", self.letter_of_credit).update_utilization()

	def on_cancel(self):
		self.ignore_linked_doctypes = ("Journal Entry", "GL Entry")
		frappe.get_doc("Letter of Credit", self.letter_of_credit).update_utilization()
