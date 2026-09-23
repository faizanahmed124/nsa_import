import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate

from nsa_import.utils import get_company_currency, refresh_po_import_status


class LetterofCredit(Document):
	def validate(self):
		self.set_missing_values()
		self.validate_purchase_order()
		self.calculate_amounts()
		self.validate_dates()
		if self.docstatus == 0:
			self.status = "Draft"

	def before_update_after_submit(self):
		self.calculate_amounts()
		self.validate_dates()

	def on_update_after_submit(self):
		self.update_utilization()

	def on_submit(self):
		self.db_set("status", "Opened")
		frappe.db.set_value(
			"Purchase Order", self.purchase_order,
			{"letter_of_credit": self.name, "lc_no": self.lc_no, "lc_date": self.lc_date},
			update_modified=False,
		)
		refresh_po_import_status(self.purchase_order)

	def on_cancel(self):
		self.ignore_linked_doctypes = ("Purchase Order", "Journal Entry", "GL Entry")
		self.db_set("status", "Cancelled")
		if frappe.db.get_value("Purchase Order", self.purchase_order, "letter_of_credit") == self.name:
			frappe.db.set_value("Purchase Order", self.purchase_order, "letter_of_credit", None, update_modified=False)
		refresh_po_import_status(self.purchase_order)

	# ------------------------------------------------------------------
	def set_missing_values(self):
		if not self.purchase_order:
			return
		po = frappe.db.get_value(
			"Purchase Order", self.purchase_order,
			["company", "supplier", "currency", "conversion_rate", "grand_total", "lc_no", "lc_date", "lc_bank",
			 "shipping_term", "mode_of_shipment", "port_of_loading", "port_of_discharge", "expected_shipment_date",
			 "supplier_bank"],
			as_dict=True,
		) or {}
		mapping = {
			"company": "company", "supplier": "supplier", "currency": "currency", "exchange_rate": "conversion_rate",
			"lc_amount": "grand_total", "lc_no": "lc_no", "issuing_bank": "lc_bank", "shipping_term": "shipping_term",
			"mode_of_shipment": "mode_of_shipment", "port_of_loading": "port_of_loading",
			"port_of_discharge": "port_of_discharge", "latest_shipment_date": "expected_shipment_date",
			"beneficiary_bank": "supplier_bank",
		}
		for target, source in mapping.items():
			if not self.get(target) and po.get(source):
				self.set(target, po.get(source))

	def validate_purchase_order(self):
		po = frappe.db.get_value("Purchase Order", self.purchase_order, ["docstatus", "purchase_type", "company"], as_dict=True)
		if not po or po.docstatus != 1:
			frappe.throw(_("Purchase Order {0} must be submitted before opening an LC.").format(self.purchase_order))
		if po.purchase_type != "Import":
			frappe.throw(_("Letter of Credit can only be opened against an Import Purchase Order."))
		if self.company != po.company:
			frappe.throw(_("Company must match the Purchase Order company ({0}).").format(po.company))
		other = frappe.db.get_value(
			"Letter of Credit", {"purchase_order": self.purchase_order, "docstatus": 1, "name": ["!=", self.name]}, "name"
		)
		if other and self.docstatus == 0:
			frappe.msgprint(_("Letter of Credit {0} already exists against this Purchase Order.").format(other),
							indicator="orange", alert=True)

	def validate_dates(self):
		if self.expiry_date and self.lc_date and getdate(self.expiry_date) < getdate(self.lc_date):
			frappe.throw(_("Expiry Date cannot be before LC Date."))
		if self.latest_shipment_date and self.expiry_date and getdate(self.latest_shipment_date) > getdate(self.expiry_date):
			frappe.throw(_("Latest Shipment Date cannot be after Expiry Date."))

	def effective_amount(self):
		return flt(self.lc_amount) + sum(flt(d.amount_change) for d in self.get("amendments") or [])

	def calculate_amounts(self):
		if self.currency == get_company_currency(self.company):
			self.exchange_rate = 1
		if flt(self.exchange_rate) <= 0:
			frappe.throw(_("Exchange Rate must be greater than zero."))

		# latest amendment dates override the original ones
		rows = sorted(self.get("amendments") or [], key=lambda d: (getdate(d.amendment_date), d.idx))
		for d in rows:
			if d.new_expiry_date:
				self.expiry_date = d.new_expiry_date
			if d.new_latest_shipment_date:
				self.latest_shipment_date = d.new_latest_shipment_date

		effective = self.effective_amount()
		self.max_lc_amount = flt(effective * (1 + flt(self.tolerance_percent) / 100), 2)
		self.base_lc_amount = flt(effective * flt(self.exchange_rate), 2)
		if flt(self.margin_percent):
			self.margin_amount = flt(self.base_lc_amount * flt(self.margin_percent) / 100, 2)
		self.total_charges = flt(
			sum(flt(d.amount) for d in self.get("charges") or [])
			+ sum(flt(d.amendment_charges) for d in self.get("amendments") or []), 2
		)
		self.balance_amount = flt(self.max_lc_amount - flt(self.shipped_amount), 2)

	def update_utilization(self):
		if self.docstatus != 1:
			return
		shipped = flt(frappe.db.sql(
			"select coalesce(sum(invoice_amount),0) from `tabImport Shipment` where letter_of_credit=%s and docstatus=1",
			self.name)[0][0])
		retired = flt(frappe.db.sql(
			"select coalesce(sum(amount),0) from `tabLC Retirement` where letter_of_credit=%s and docstatus=1",
			self.name)[0][0])
		full = self.effective_amount() * (1 - flt(self.tolerance_percent) / 100)

		if self.status == "Closed":
			status = "Closed"
		elif retired and retired >= full:
			status = "Retired"
		elif retired:
			status = "Partially Retired"
		elif shipped and shipped >= full:
			status = "Fully Shipped"
		elif shipped:
			status = "Partially Shipped"
		elif self.get("amendments"):
			status = "Amended"
		else:
			status = "Opened"

		self.db_set(
			{"shipped_amount": shipped, "retired_amount": retired,
			 "balance_amount": flt(flt(self.max_lc_amount) - shipped, 2), "status": status},
			update_modified=False,
		)
