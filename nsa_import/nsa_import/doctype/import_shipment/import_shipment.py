import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from nsa_import.utils import get_company_currency, get_settings, refresh_po_import_status, update_po_shipped_qty


class ImportShipment(Document):
	def validate(self):
		self.validate_purchase_order()
		self.validate_letter_of_credit()
		self.calculate_totals()
		self.validate_qty_against_po()
		self.validate_lc_amount()
		self.set_default_documents()
		if self.docstatus == 0:
			self.status = "Draft"

	def on_submit(self):
		self.db_set("status", "Arrived" if self.actual_arrival_date else "In Transit")
		self.update_linked()

	def on_cancel(self):
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

	# ------------------------------------------------------------------
	def validate_purchase_order(self):
		po = frappe.db.get_value("Purchase Order", self.purchase_order,
								 ["docstatus", "purchase_type", "company", "supplier", "currency", "conversion_rate"],
								 as_dict=True)
		if not po or po.docstatus != 1:
			frappe.throw(_("Purchase Order {0} must be submitted.").format(self.purchase_order))
		if po.purchase_type != "Import":
			frappe.throw(_("Import Shipment can only be created against an Import Purchase Order."))
		self.company = po.company
		self.supplier = po.supplier
		if not self.currency:
			self.currency = po.currency
		if not flt(self.exchange_rate):
			self.exchange_rate = po.conversion_rate
		for d in self.items:
			if not d.purchase_order:
				d.purchase_order = self.purchase_order

	def validate_letter_of_credit(self):
		if not self.letter_of_credit:
			return
		lc = frappe.db.get_value("Letter of Credit", self.letter_of_credit,
								 ["docstatus", "purchase_order", "currency", "status"], as_dict=True)
		if not lc or lc.docstatus != 1:
			frappe.throw(_("Letter of Credit {0} must be submitted.").format(self.letter_of_credit))
		if lc.purchase_order != self.purchase_order:
			frappe.throw(_("Letter of Credit {0} belongs to a different Purchase Order.").format(self.letter_of_credit))
		if lc.currency != self.currency:
			frappe.throw(_("Shipment currency must match LC currency ({0}).").format(lc.currency))
		if lc.status in ("Closed", "Expired", "Retired"):
			frappe.throw(_("Letter of Credit {0} is {1}.").format(self.letter_of_credit, lc.status))

	def calculate_totals(self):
		if self.currency == get_company_currency(self.company):
			self.exchange_rate = 1
		total = net = gross = 0.0
		for d in self.items:
			d.amount = flt(flt(d.qty) * flt(d.rate), 2)
			total += d.amount
			net += flt(d.net_weight)
			gross += flt(d.gross_weight)
		self.invoice_amount = flt(total, 2)
		self.base_invoice_amount = flt(total * flt(self.exchange_rate), 2)
		self.total_net_weight = net
		self.total_gross_weight = gross

	def validate_qty_against_po(self):
		tolerance = flt(get_settings().shipment_qty_tolerance)
		this_qty = {}
		for d in self.items:
			if d.po_detail:
				this_qty[d.po_detail] = this_qty.get(d.po_detail, 0) + flt(d.qty)
		for po_detail, qty in this_qty.items():
			po_qty = flt(frappe.db.get_value("Purchase Order Item", po_detail, "qty"))
			other = flt(frappe.db.sql(
				"""select coalesce(sum(i.qty),0) from `tabImport Shipment Item` i
				join `tabImport Shipment` s on s.name = i.parent
				where i.po_detail=%s and s.docstatus=1 and s.name!=%s""", (po_detail, self.name))[0][0])
			allowed = po_qty * (1 + tolerance / 100)
			if other + qty > allowed + 0.0001:
				item = frappe.db.get_value("Purchase Order Item", po_detail, "item_code")
				frappe.throw(_("Item {0}: shipped qty {1} exceeds PO qty {2} (already shipped {3}).")
							 .format(item, qty, po_qty, other))

	def validate_lc_amount(self):
		if not self.letter_of_credit:
			return
		max_amount = flt(frappe.db.get_value("Letter of Credit", self.letter_of_credit, "max_lc_amount"))
		other = flt(frappe.db.sql(
			"""select coalesce(sum(invoice_amount),0) from `tabImport Shipment`
			where letter_of_credit=%s and docstatus=1 and name!=%s""", (self.letter_of_credit, self.name))[0][0])
		if max_amount and other + flt(self.invoice_amount) > max_amount + 0.01:
			frappe.throw(_("Shipment value exceeds LC balance. LC Max: {0}, already shipped: {1}, this shipment: {2}")
						 .format(max_amount, other, self.invoice_amount))

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
			if d.document_type in ("Bill of Lading", "Airway Bill", "Truck Receipt / CMR", "Courier Receipt"):
				d.document_no = d.document_no or self.bl_awb_no
				d.document_date = d.document_date or self.bl_awb_date
			elif d.document_type == "Commercial Invoice":
				d.document_no = d.document_no or self.commercial_invoice_no
				d.document_date = d.document_date or self.commercial_invoice_date
			elif d.document_type == "Packing List":
				d.document_no = d.document_no or self.packing_list_no
