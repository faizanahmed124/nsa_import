"""Freight Bill - freight charges of an import shipment (created from Duty Calculation).

Sea / Air Freight Value in PKR = Sea / Air Freight Value in USD x Conversion Rate
Total = Freight PKR + DO Charges + FCA + BL Endorsement Fee + DGM Report + Container Size 20 + Container Size 40
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate

from nsa_import.nsa_import.doctype.transporter_bill.transporter_bill import set_links_from_sources

CHARGE_FIELDS = ("do_charges", "fca", "bl_endorsement_fee", "dgm_report", "container_size_20", "container_size_40")


class FreightBill(Document):
	def validate(self):
		set_links_from_sources(self)
		for f in ("freight_value_usd", "conversion_rate") + CHARGE_FIELDS:
			if flt(self.get(f)) < 0:
				frappe.throw(_("{0} cannot be negative.").format(_(self.meta.get_label(f))))
		self.freight_value_pkr = flt(flt(self.freight_value_usd) * flt(self.conversion_rate), 2)
		self.total = flt(self.freight_value_pkr + sum(flt(self.get(f)) for f in CHARGE_FIELDS), 2)
		if self.freight_bill_paid and self.freight_bill_received and \
				getdate(self.freight_bill_paid) < getdate(self.freight_bill_received):
			frappe.msgprint(_("Freight Bill Paid date is before the Received date."), indicator="orange", alert=True)
