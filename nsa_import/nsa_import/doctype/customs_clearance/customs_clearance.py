import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate

from nsa_import.utils import refresh_po_import_status


class CustomsClearance(Document):
	def validate(self):
		self.validate_shipment()
		self.calculate_duties()
		if self.docstatus == 0 and self.status in ("Released", "Cancelled"):
			self.status = "Draft"

	def on_submit(self):
		self.db_set({"status": "Released", "release_date": self.release_date or nowdate()})
		frappe.db.set_value("Import Shipment", self.import_shipment, "status", "Cleared", update_modified=False)
		refresh_po_import_status(self.purchase_order)

	def on_cancel(self):
		self.ignore_linked_doctypes = ("Journal Entry", "GL Entry")
		self.db_set("status", "Cancelled")
		arrived = frappe.db.get_value("Import Shipment", self.import_shipment, "actual_arrival_date")
		frappe.db.set_value("Import Shipment", self.import_shipment, "status",
							"Arrived" if arrived else "In Transit", update_modified=False)
		refresh_po_import_status(self.purchase_order)

	def validate_shipment(self):
		shp = frappe.db.get_value(
			"Import Shipment", self.import_shipment,
			["docstatus", "purchase_order", "letter_of_credit", "company", "supplier", "currency", "exchange_rate",
			 "bl_awb_no"], as_dict=True)
		if not shp or shp.docstatus != 1:
			frappe.throw(_("Import Shipment {0} must be submitted.").format(self.import_shipment))
		for f in ("purchase_order", "letter_of_credit", "company", "supplier", "currency", "bl_awb_no"):
			self.set(f, shp.get(f))
		if not flt(self.exchange_rate):
			self.exchange_rate = shp.exchange_rate
		dup = frappe.db.get_value("Customs Clearance",
								  {"import_shipment": self.import_shipment, "docstatus": 1, "name": ["!=", self.name]})
		if dup:
			frappe.throw(_("Shipment {0} is already cleared under {1}.").format(self.import_shipment, dup))

	def calculate_duties(self):
		rate = flt(self.exchange_rate) or 1
		total_invoice = sum(flt(d.invoice_value) for d in self.items)
		extra = flt(self.freight_for_assessment) + flt(self.insurance_for_assessment)
		landing = flt(self.landing_charges_percent) / 100
		t = dict.fromkeys(("av", "cd", "acd", "rd", "st", "ast", "it"), 0.0)

		for d in self.items:
			share = extra * flt(d.invoice_value) / total_invoice if total_invoice else 0
			cif = flt(d.invoice_value) * rate + share
			d.assessable_value = flt(cif * (1 + landing), 2)
			d.customs_duty = flt(d.assessable_value * flt(d.customs_duty_percent) / 100, 2)
			d.acd = flt(d.assessable_value * flt(d.acd_percent) / 100, 2)
			d.rd = flt(d.assessable_value * flt(d.rd_percent) / 100, 2)
			st_base = d.assessable_value + d.customs_duty + d.acd + d.rd
			d.sales_tax = flt(st_base * flt(d.sales_tax_percent) / 100, 2)
			d.ast = flt(st_base * flt(d.ast_percent) / 100, 2)
			it_base = st_base + d.sales_tax + d.ast
			d.income_tax = flt(it_base * flt(d.income_tax_percent) / 100, 2)
			d.total_duty_taxes = flt(d.customs_duty + d.acd + d.rd + d.sales_tax + d.ast + d.income_tax, 2)
			for k, v in (("av", d.assessable_value), ("cd", d.customs_duty), ("acd", d.acd), ("rd", d.rd),
						 ("st", d.sales_tax), ("ast", d.ast), ("it", d.income_tax)):
				t[k] += v

		self.total_assessable_value = flt(t["av"], 2)
		self.total_customs_duty = flt(t["cd"], 2)
		self.total_acd = flt(t["acd"], 2)
		self.total_rd = flt(t["rd"], 2)
		self.total_sales_tax = flt(t["st"], 2)
		self.total_additional_sales_tax = flt(t["ast"], 2)
		self.total_income_tax = flt(t["it"], 2)
		self.total_duties_landed = flt(t["cd"] + t["acd"] + t["rd"], 2)
		self.total_adjustable_taxes = flt(t["st"] + t["ast"] + t["it"], 2)
		self.total_duties_and_taxes = flt(self.total_duties_landed + self.total_adjustable_taxes, 2)
