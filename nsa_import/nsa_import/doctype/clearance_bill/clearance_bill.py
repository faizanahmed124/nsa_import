"""Clearance Bill - clearing agent's bill for an import shipment (created from Duty Calculation).

Every charge has an Agent amount and an ATS amount, each with its own 'Paid By' selection.
  Total             = all Agent + ATS charges except Agency Commission, Sales Tax and Income Tax
  Total Bill        = Total + Agency Commission + Sales Tax - Income Tax
  Paid By Agent     = amounts marked 'Paid By Agent' - income tax marked 'Paid By Agent'
  Paid By ATS       = amounts marked 'Paid By ATS'   - income tax marked 'Paid By ATS'
  PAYABLE/RECEIVABLE = Total Bill - Amount Paid to C Agent
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from nsa_import.nsa_import.doctype.transporter_bill.transporter_bill import set_links_from_sources

CHARGES = ("excise", "stamp_charges", "lolo_charges", "port_charges", "port_warfage", "weboc", "do",
		   "demurrage_detention", "others", "misc", "lab_cargo")
AGENT_VALUES = ("Paid By Agent", "Deduct By Agent")  # "Deduct By ..." kept for bills saved before v1.1
BILL_ITEMS = CHARGES + ("agency_commission", "sales_tax")
SIDES = ("agent", "ats")


class ClearanceBill(Document):
	def validate(self):
		set_links_from_sources(self)
		for key in BILL_ITEMS + ("income_tax",):
			for side in SIDES:
				if flt(self.get(f"{key}_{side}")) < 0:
					frappe.throw(_("{0} cannot be negative.").format(_(self.meta.get_label(f"{key}_{side}"))))
		if flt(self.amount_paid_to_agent) < 0:
			frappe.throw(_("Amount Paid to C Agent cannot be negative."))
		self.calculate()

	def before_update_after_submit(self):
		self.payable_receivable = flt(flt(self.total_bill) - flt(self.amount_paid_to_agent), 2)

	def calculate(self):
		amount = lambda key, side: flt(self.get(f"{key}_{side}"))  # noqa: E731
		self.total = flt(sum(amount(k, s) for k in CHARGES for s in SIDES), 2)
		income_tax = sum(amount("income_tax", s) for s in SIDES)
		self.total_bill = flt(self.total + sum(amount(k, s) for k in ("agency_commission", "sales_tax") for s in SIDES)
							  - income_tax, 2)
		by_agent = by_ats = 0.0
		for key in BILL_ITEMS:
			for side in SIDES:
				if self.get(f"{key}_paid_by_{side}") in AGENT_VALUES:
					by_agent += amount(key, side)
				else:
					by_ats += amount(key, side)
		for side in SIDES:
			if self.get(f"income_tax_paid_by_{side}") in AGENT_VALUES:
				by_agent -= amount("income_tax", side)
			else:
				by_ats -= amount("income_tax", side)
		self.paid_by_agent_total = flt(by_agent, 2)
		self.paid_by_ats_total = flt(by_ats, 2)
		self.payable_receivable = flt(self.total_bill - flt(self.amount_paid_to_agent), 2)
