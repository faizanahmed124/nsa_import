"""Arrival Notice - arrival / delivery of a shipment and receiving progress (created from Duty Calculation).

Item Pending QTY = Shipped QTY - GRN QTY
GRN QTY          = quantity received in submitted GRNs (Purchase Receipts) of the Shipping Document; it can also be
				   entered by hand while receiving. Submitting / cancelling a GRN refreshes it automatically.
GRN Status       = Received when every item has Pending QTY 0, otherwise Pending
Containers       = Container 20 + Container 40;  QTY = sum of item Shipped QTY
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from nsa_import.utils import get_settings


class ArrivalNotice(Document):
	def validate(self):
		self.set_source_values()
		self.validate_duplicate()
		if not self.get("items"):
			frappe.throw(_("Add at least one item."))
		if (self.container_20 or 0) < 0 or (self.container_40 or 0) < 0:
			frappe.throw(_("Container quantities cannot be negative."))
		self.containers = (self.container_20 or 0) + (self.container_40 or 0)
		self.qty = flt(sum(flt(d.shipped_qty) for d in self.items), 6)
		self.calculate()

	def before_update_after_submit(self):
		self.calculate()

	def set_source_values(self):
		if self.docstatus != 0 or not self.shipping_document:
			return
		sd = frappe.db.get_value("Shipping Document", self.shipping_document,
								 ["docstatus", "purchase_order", "letter_of_credit", "company"], as_dict=True)
		if not sd or sd.docstatus != 1:
			frappe.throw(_("Shipping Document {0} must be submitted.").format(self.shipping_document))
		self.update({"purchase_order": sd.purchase_order, "letter_of_credit": sd.letter_of_credit,
					 "company": sd.company})
		if self.duty_calculation and frappe.db.get_value("Duty Calculation", self.duty_calculation,
														  "shipping_document") != self.shipping_document:
			frappe.throw(_("Duty Calculation {0} belongs to another Shipping Document.").format(self.duty_calculation))

	def validate_duplicate(self):
		if get_settings().allow_multiple_arrival_notices:
			return
		other = frappe.db.get_value("Arrival Notice", {"shipping_document": self.shipping_document,
													   "docstatus": ["<", 2], "name": ["!=", self.name or ""]}, "name")
		if other:
			frappe.throw(_("Arrival Notice {0} already exists for Shipping Document {1}. Tick 'Allow more than one "
						   "Arrival Notice' in NSA Import Settings for partial deliveries.")
						 .format(other, self.shipping_document))

	def calculate(self):
		tolerance = flt(get_settings().shipment_qty_tolerance)
		for d in self.items:
			if flt(d.grn_qty) < 0:
				frappe.throw(_("Row {0}: GRN QTY cannot be negative.").format(d.idx))
			if flt(d.grn_qty) > flt(d.shipped_qty) * (1 + tolerance / 100) + 0.0001:
				frappe.throw(_("Row {0}: GRN QTY {1} is more than Shipped QTY {2} (allowed over-receipt {3}%).")
							 .format(d.idx, flt(d.grn_qty, 3), flt(d.shipped_qty, 3), tolerance))
			d.pending_qty = max(flt(flt(d.shipped_qty) - flt(d.grn_qty), 6), 0)
		self.grn_status = "Received" if all(flt(d.pending_qty) <= 0 for d in self.items) else "Pending"

	def update_from_grns(self, save=True, reset=False):
		"""GRN QTY from submitted Purchase Receipts of the Shipping Document (per PO item, filled row by row)."""
		received = dict(frappe.db.sql(
			"""select pri.purchase_order_item, sum(pri.qty) from `tabPurchase Receipt Item` pri
			join `tabPurchase Receipt` pr on pr.name = pri.parent
			where pr.docstatus = 1 and pr.import_shipment = %s group by pri.purchase_order_item""",
			self.shipping_document))
		if not received and not reset:
			return  # no GRN yet: keep quantities entered by hand
		for d in self.items:
			left = flt(received.get(d.po_detail))
			d.grn_qty = min(left, flt(d.shipped_qty))
			received[d.po_detail] = left - flt(d.grn_qty)
		self.calculate()
		if save:
			self.flags.ignore_permissions = True
			self.save()


def update_arrival_notices(shipping_document, reset=False):
	"""Called when a GRN of the Shipping Document is submitted (reset=False) or cancelled (reset=True)."""
	if not shipping_document:
		return
	for name in frappe.get_all("Arrival Notice", filters={"shipping_document": shipping_document,
														  "docstatus": ["<", 2]}, pluck="name"):
		frappe.get_doc("Arrival Notice", name).update_from_grns(reset=reset)
