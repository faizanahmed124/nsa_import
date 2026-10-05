"""Shipment Check And Delays - milestone dates of a shipment (created from Shipping Document).

Dates fetched when available (never overwriting a date already entered, unless 'Refresh Dates' is used):
  PI Date          Purchase Order -> PI Date
  LC Opening Date  Letter of Credit -> LC Date
  ETA              Shipping Document -> ETA
  GD Gate out      Customs Clearance (GD) -> Release Date
  ATS              first GRN (Purchase Receipt) posting date for the Shipping Document
  Empty Return     entered by the user (the same date is copied between the two Empty Return rows)
Delay days (To - From) are shown in the Shipment Delay Report.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate
from nsa_import.utils import pr_doctype

MILESTONES = (
	("pi_to_lc", "pi", "lc"),
	("lc_to_eta", "lc", "eta"),
	("eta_to_gd", "eta", "gd"),
	("gd_to_ats", "gd", "ats"),
	("pi_to_ats", "pi", "ats"),
	("eta_to_ats", "eta", "ats"),
	("eta_to_empty", "eta", None),
	("ats_to_empty", "ats", None),
)


def get_source_dates(shipping_document):
	sd = frappe.db.get_value("Shipping Document", shipping_document,
							 ["purchase_order", "letter_of_credit", "eta"], as_dict=True) or frappe._dict()
	gd = frappe.db.sql("""select max(release_date) from `tabCustoms Clearance`
		where import_shipment=%s and docstatus=1""", shipping_document)
	pr = pr_doctype()
	ats = frappe.db.sql(f"""select min(posting_date) from `tab{pr}`
		where import_shipment=%s and docstatus=1""", shipping_document) \
		if frappe.db.has_column(pr, "import_shipment") else [[None]]
	return {
		"pi": frappe.db.get_value("Purchase Order", sd.purchase_order, "pi_date") if sd.purchase_order else None,
		"lc": frappe.db.get_value("Letter of Credit", sd.letter_of_credit, "lc_date") if sd.letter_of_credit else None,
		"eta": sd.eta,
		"gd": gd[0][0] if gd else None,
		"ats": ats[0][0] if ats else None,
	}


def milestone_values(shipping_document):
	src = get_source_dates(shipping_document)
	out = {}
	for key, frm, to in MILESTONES:
		out[f"{key}_from"] = src.get(frm)
		out[f"{key}_to"] = src.get(to) if to else None
	return out


class ShipmentCheckAndDelays(Document):
	def validate(self):
		sd = frappe.db.get_value("Shipping Document", self.shipping_document, ["docstatus", "supplier",
																				 "supplier_name"], as_dict=True)
		if not sd or sd.docstatus == 2:
			frappe.throw(_("Shipping Document {0} is not valid.").format(self.shipping_document))
		self.supplier, self.supplier_name = sd.supplier, sd.supplier_name
		self.fill_dates(overwrite=False)
		# one Empty Return date for both rows
		if self.eta_to_empty_to and not self.ats_to_empty_to:
			self.ats_to_empty_to = self.eta_to_empty_to
		elif self.ats_to_empty_to and not self.eta_to_empty_to:
			self.eta_to_empty_to = self.ats_to_empty_to
		for key, _f, _t in MILESTONES:
			start, end = self.get(f"{key}_from"), self.get(f"{key}_to")
			if start and end and getdate(end) < getdate(start):
				frappe.msgprint(_("{0}: To Date is before From Date.").format(_(self.meta.get_label(f"{key}_section"))),
								indicator="orange", alert=True)

	def fill_dates(self, overwrite=False):
		for field, value in milestone_values(self.shipping_document).items():
			if value and (overwrite or not self.get(field)):
				self.set(field, value)
