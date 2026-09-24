"""Shipping Document - shipment execution / documentation, created from a Letter of Credit.

Formulas
  Item  Shipped Qty (PO UOM) = Shipped Qty x Shipped-UOM-to-PO-UOM factor
  Item  Shipped Amount       = Shipped Qty (PO UOM) x PO Rate
  Item  Remaining Qty        = PO Qty - previously shipped (other submitted docs) - this shipment
  Header Shipped Qty         = sum of item Shipped Qty
  Header S/QTY Amount        = sum of item Shipped Amount            (foreign currency)
  Header S/QTY Amount (PKR)  = S/QTY Amount x Conversion Rate
  Commission                 = S/QTY Amount (PKR) x Commission % / 100
  FED on Commission          = Commission x FED % / 100
  Total Charges              = Commission + FED + SWIFT Charges
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from nsa_import.utils import (
	get_company_currency,
	get_settings,
	get_uom_factor,
	refresh_po_import_status,
	update_po_shipped_qty,
)

TRANSPORT_DOCS = ("Bill of Lading", "Airway Bill", "Truck Receipt / CMR", "Courier Receipt")
MANDATORY_ON_SUBMIT = (
	("commercial_invoice_no", "Commercial Invoice No."),
	("bl_awb_no", "Bill of Lading No."),
	("bl_awb_date", "Bill of Lading Date"),
	("packing", "Packing (Packing List tab)"),
	("packing_qty", "QTY (Packing List tab)"),
	("total_net_weight", "Net Weight (Packing List tab)"),
	("weight_uom", "Weight UOM (Packing List tab)"),
)
INACTIVE_LC = ("Closed", "Expired", "Retired", "Cancelled", "Draft")


class ShippingDocument(Document):
	# ------------------------------------------------------------------ hooks
	def validate(self):
		self.set_source_values()
		self.validate_source()
		self.set_item_values()
		self.calculate_items()
		self.validate_qty_against_po()
		self.calculate_totals()
		self.validate_lc_amount()
		self.calculate_charges()
		self.set_default_documents()
		if self.docstatus == 0:
			self.status = "Draft"

	def before_submit(self):
		missing = [_(label) for field, label in MANDATORY_ON_SUBMIT if not self.get(field)]
		if missing:
			frappe.throw(_("Please fill before submitting: {0}").format(", ".join(missing)),
						 title=_("Missing Values"))
		if not any(flt(d.shipped_qty) > 0 for d in self.items):
			frappe.throw(_("Enter Shipped Qty for at least one item."))
		self.set("items", [d for d in self.items if flt(d.shipped_qty) > 0])
		for i, d in enumerate(self.items, 1):
			d.idx = i

	def on_submit(self):
		self.db_set("status", "Arrived" if self.actual_arrival_date else "In Transit")
		self.update_linked()

	def on_cancel(self):
		self.ignore_linked_doctypes = ("Journal Entry", "GL Entry")
		self.db_set("status", "Cancelled")
		self.update_linked()

	def on_update_after_submit(self):
		if self.actual_arrival_date and self.status == "In Transit":
			self.db_set("status", "Arrived")
		refresh_po_import_status(self.purchase_order)

	def update_linked(self):
		update_po_shipped_qty(self.purchase_order)
		if self.letter_of_credit:
			frappe.get_doc("Letter of Credit", self.letter_of_credit).update_utilization()
		refresh_po_import_status(self.purchase_order)

	# -------------------------------------------------------------- source
	def set_source_values(self):
		"""LC -> PO -> Supplier / LC No. / Currency are always taken from the source documents."""
		if self.docstatus != 0:
			return
		if self.letter_of_credit:
			lc = frappe.db.get_value(
				"Letter of Credit", self.letter_of_credit,
				["purchase_order", "supplier", "supplier_name", "company", "currency", "exchange_rate", "lc_no"],
				as_dict=True)
			if not lc:
				frappe.throw(_("Letter of Credit {0} not found.").format(self.letter_of_credit))
			self.purchase_order = lc.purchase_order
			self.update({"supplier": lc.supplier, "supplier_name": lc.supplier_name, "company": lc.company,
						 "currency": lc.currency, "lc_no": lc.lc_no})
			if not flt(self.exchange_rate) or (self.is_new() and flt(self.exchange_rate) == 1):
				self.exchange_rate = lc.exchange_rate
		elif self.purchase_order:
			self.lc_no = None
		if self.purchase_order:
			po = frappe.db.get_value(
				"Purchase Order", self.purchase_order,
				["company", "supplier", "supplier_name", "currency", "conversion_rate", "pi_no",
				 "customs_clearing_agent"], as_dict=True) or frappe._dict()
			self.pi_no = po.pi_no
			if not self.letter_of_credit:
				self.update({"supplier": po.supplier, "supplier_name": po.supplier_name, "company": po.company,
							 "currency": po.currency})
				if not flt(self.exchange_rate) or (self.is_new() and flt(self.exchange_rate) == 1):
					self.exchange_rate = po.conversion_rate
			if not self.clearing_agent and po.customs_clearing_agent:
				self.clearing_agent = po.customs_clearing_agent

	def validate_source(self):
		settings = get_settings()
		if not self.letter_of_credit and not settings.allow_shipping_without_lc:
			frappe.throw(_("Shipping Document can only be created from a Letter of Credit. "
						   "Open the Letter of Credit and use Create → Shipping Document."))
		if self.letter_of_credit:
			lc = frappe.db.get_value("Letter of Credit", self.letter_of_credit,
									 ["docstatus", "status", "lc_no", "purchase_order"], as_dict=True)
			if lc.docstatus != 1:
				frappe.throw(_("Letter of Credit {0} must be submitted.").format(self.letter_of_credit))
			if self.docstatus == 0 and lc.status in INACTIVE_LC:
				frappe.throw(_("Letter of Credit {0} is {1}.").format(self.letter_of_credit, lc.status))
			if not lc.lc_no:
				frappe.throw(_("Enter the bank's LC Number on Letter of Credit {0} before creating a Shipping Document.")
							 .format(self.letter_of_credit))
		po = frappe.db.get_value("Purchase Order", self.purchase_order, ["docstatus", "purchase_type", "status"],
								 as_dict=True)
		if not po or po.docstatus != 1:
			frappe.throw(_("Purchase Order {0} must be submitted.").format(self.purchase_order))
		if po.purchase_type != "Import":
			frappe.throw(_("Shipping Document can only be created for an Import Purchase Order."))
		if self.currency and self.company and self.currency == get_company_currency(self.company):
			self.exchange_rate = 1
		if flt(self.exchange_rate) <= 0:
			frappe.throw(_("Conversion Rate must be greater than zero."))

	# --------------------------------------------------------------- items
	def set_item_values(self):
		"""Item Code, Name, Qty, Rate, Amount and PO UOM are controlled by the PO row."""
		po_details = [d.po_detail for d in self.items if d.po_detail]
		po_rows = {}
		if po_details:
			for r in frappe.get_all(
				"Purchase Order Item", filters={"name": ["in", po_details], "parent": self.purchase_order},
				fields=["name", "item_code", "item_name", "qty", "uom", "rate", "amount", "warehouse", "hs_code",
						"item_country_of_origin"]):
				po_rows[r.name] = r
		for d in self.items:
			r = po_rows.get(d.po_detail)
			if not r:
				frappe.throw(_("Row {0}: items must be fetched from Purchase Order {1} (use Get Items from Purchase Order).")
							 .format(d.idx, self.purchase_order))
			d.update({"item_code": r.item_code, "item_name": r.item_name, "ordered_qty": flt(r.qty),
					  "po_uom": r.uom, "rate": flt(r.rate), "po_amount": flt(r.amount),
					  "purchase_order": self.purchase_order})
			d.uom = d.uom or r.uom
			d.warehouse = d.warehouse or r.warehouse
			d.hs_code = d.hs_code or r.hs_code
			d.country_of_origin = d.country_of_origin or r.item_country_of_origin
			if d.uom == d.po_uom:
				d.uom_conversion_factor = 1
			elif not flt(d.uom_conversion_factor) or flt(d.uom_conversion_factor) == 1:
				d.uom_conversion_factor = get_uom_factor(d.item_code, d.uom, d.po_uom)
			if flt(d.uom_conversion_factor) <= 0:
				frappe.throw(_("Row {0}: set the Shipped UOM to PO UOM factor for {1} ({2} → {3}).")
							 .format(d.idx, d.item_code, d.uom, d.po_uom))

	def shipped_elsewhere(self):
		details = list({d.po_detail for d in self.items if d.po_detail})
		if not details:
			return {}
		return dict(frappe.db.sql(
			"""select i.po_detail, coalesce(sum(i.qty), 0) from `tabShipping Document Item` i
			join `tabShipping Document` s on s.name = i.parent
			where i.po_detail in %(details)s and s.docstatus = 1 and s.name != %(name)s
			group by i.po_detail""", {"details": details, "name": self.name or ""}))

	def calculate_items(self):
		other = self.shipped_elsewhere()
		running = {}
		for d in self.items:
			if flt(d.shipped_qty) < 0:
				frappe.throw(_("Row {0}: Shipped Qty cannot be negative.").format(d.idx))
			d.qty = flt(flt(d.shipped_qty) * flt(d.uom_conversion_factor), 6)
			d.amount = flt(d.qty * flt(d.rate), 2)
			running[d.po_detail] = running.get(d.po_detail, 0) + d.qty
			d.already_shipped_qty = flt(other.get(d.po_detail))
			d.remaining_qty = flt(flt(d.ordered_qty) - d.already_shipped_qty - running[d.po_detail], 6)
		self._shipped_elsewhere = other

	def validate_qty_against_po(self):
		tolerance = flt(get_settings().shipment_qty_tolerance)
		this = {}
		for d in self.items:
			this.setdefault(d.po_detail, [d, 0])[1] += flt(d.qty)
		for po_detail, (row, qty) in this.items():
			already = flt(self._shipped_elsewhere.get(po_detail))
			allowed = flt(row.ordered_qty) * (1 + tolerance / 100)
			if already + qty > allowed + 0.0001:
				frappe.throw(_("Item {0}: Shipped Qty {1} {2} exceeds the open PO quantity. PO Qty {3}, previously "
							   "shipped {4}, allowed over-shipment {5}%.")
							 .format(row.item_code, flt(qty, 3), row.po_uom, row.ordered_qty, flt(already, 3), tolerance))

	def calculate_totals(self):
		self.total_shipped_qty = flt(sum(flt(d.shipped_qty) for d in self.items), 6)
		self.invoice_amount = flt(sum(flt(d.amount) for d in self.items), 2)
		self.base_invoice_amount = flt(self.invoice_amount * flt(self.exchange_rate), 2)
		seen = {}
		for d in self.items:
			seen[d.po_detail] = d
		self.total_po_qty = flt(sum(flt(d.ordered_qty) for d in seen.values()), 6)
		self.total_po_amount = flt(sum(flt(d.po_amount) for d in seen.values()), 2)
		last = {}
		for d in self.items:
			last[d.po_detail] = flt(d.remaining_qty)
		self.total_remaining_qty = flt(sum(last.values()), 6)

		if not flt(self.packing_qty):
			self.packing_qty = self.total_shipped_qty
		if not flt(self.total_net_weight):
			self.total_net_weight = flt(sum(flt(d.net_weight) for d in self.items), 3) or None
		if not flt(self.total_gross_weight):
			self.total_gross_weight = flt(sum(flt(d.gross_weight) for d in self.items), 3) or None
		for f in ("packing_qty", "total_net_weight", "total_gross_weight", "no_of_packages"):
			if flt(self.get(f)) < 0:
				frappe.throw(_("{0} cannot be negative.").format(_(self.meta.get_label(f))))

	def validate_lc_amount(self):
		if not self.letter_of_credit:
			return
		max_amount = flt(frappe.db.get_value("Letter of Credit", self.letter_of_credit, "max_lc_amount"))
		other = flt(frappe.db.sql(
			"""select coalesce(sum(invoice_amount),0) from `tabShipping Document`
			where letter_of_credit=%s and docstatus=1 and name!=%s""", (self.letter_of_credit, self.name or ""))[0][0])
		if max_amount and other + flt(self.invoice_amount) > max_amount + 0.01:
			frappe.throw(_("S/QTY Amount exceeds the LC balance. LC maximum {0}, already shipped {1}, this document {2}.")
						 .format(max_amount, other, self.invoice_amount))

	# ------------------------------------------------------------- charges
	def calculate_charges(self):
		settings = get_settings()
		if self.is_new() and self.docstatus == 0:
			if not flt(self.fed_percent) and flt(settings.default_fed_percent):
				self.fed_percent = settings.default_fed_percent
			if not flt(self.commission_percent) and flt(settings.default_shipment_commission_percent):
				self.commission_percent = settings.default_shipment_commission_percent
		for f in ("commission_percent", "fed_percent"):
			if not 0 <= flt(self.get(f)) <= 100:
				frappe.throw(_("{0} must be between 0 and 100.").format(_(self.meta.get_label(f))))
		if flt(self.swift_charges) < 0:
			frappe.throw(_("SWIFT Charges cannot be negative."))
		self.commission_amount = flt(flt(self.base_invoice_amount) * flt(self.commission_percent) / 100, 2)
		self.fed_amount = flt(self.commission_amount * flt(self.fed_percent) / 100, 2)
		self.total_charges = flt(self.commission_amount + self.fed_amount + flt(self.swift_charges), 2)

	# ----------------------------------------------------------- documents
	def set_default_documents(self):
		if not self.get("documents"):
			transport = {"By Air": "Airway Bill", "By Road": "Truck Receipt / CMR", "Courier": "Courier Receipt"}
			types = [transport.get(self.mode_of_shipment, "Bill of Lading"), "Commercial Invoice", "Packing List",
					 "Certificate of Origin"]
			if self.letter_of_credit:
				types.append("Bill of Exchange")
			for t in types:
				self.append("documents", {"document_type": t})
		for d in self.documents:
			if d.document_type in TRANSPORT_DOCS:
				d.document_no = d.document_no or self.bl_awb_no
				d.document_date = d.document_date or self.bl_awb_date
			elif d.document_type == "Commercial Invoice":
				d.document_no = d.document_no or self.commercial_invoice_no
				d.document_date = d.document_date or self.commercial_invoice_date
			elif d.document_type == "Packing List":
				d.document_no = d.document_no or self.packing_list_no
