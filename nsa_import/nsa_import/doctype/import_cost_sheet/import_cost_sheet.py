import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from nsa_import.constants import BUYER_PAYS_FREIGHT, SELLER_PAYS_INSURANCE
from nsa_import.utils import get_company_accounts, get_settings


class ImportCostSheet(Document):
	def validate(self):
		self.set_receipt_details()
		if not self.get("items"):
			self.set_items_from_receipt()
		self.allocate_charges()

	def before_submit(self):
		missing = [str(c.idx) for c in self.charges if c.include_in_landed_cost and flt(c.amount) and not c.expense_account]
		if missing:
			frappe.throw(_("Expense Account is required in charge rows: {0}").format(", ".join(missing)))
		if not flt(self.total_landed_charges):
			frappe.throw(_("There are no charges to include in landed cost."))

	def on_cancel(self):
		self.ignore_linked_doctypes = ("Landed Cost Voucher",)
		lcv = self.landed_cost_voucher
		if lcv and frappe.db.get_value("Landed Cost Voucher", lcv, "docstatus") == 1:
			frappe.throw(_("Cancel Landed Cost Voucher {0} first.").format(lcv))

	# ------------------------------------------------------------------
	def set_receipt_details(self):
		pr = frappe.db.get_value(
			"Purchase Receipt", self.purchase_receipt,
			["docstatus", "company", "supplier", "import_shipment", "customs_clearance", "letter_of_credit"], as_dict=True)
		if not pr or pr.docstatus != 1:
			frappe.throw(_("Purchase Receipt {0} must be submitted.").format(self.purchase_receipt))
		self.company = pr.company
		self.supplier = pr.supplier
		for f in ("import_shipment", "customs_clearance", "letter_of_credit"):
			if pr.get(f):
				self.set(f, pr.get(f))
		if not self.purchase_order:
			self.purchase_order = frappe.db.get_value(
				"Purchase Receipt Item", {"parent": self.purchase_receipt, "purchase_order": ["is", "set"]}, "purchase_order")
		if not self.distribute_charges_based_on:
			self.distribute_charges_based_on = get_settings().default_distribution or "Amount"

	@frappe.whitelist()
	def set_items_from_receipt(self):
		self.set("items", [])
		pr = frappe.get_doc("Purchase Receipt", self.purchase_receipt)
		for d in pr.items:
			self.append("items", {
				"item_code": d.item_code, "item_name": d.item_name, "qty": d.qty, "uom": d.uom,
				"base_amount": d.base_net_amount,
				"total_weight": flt(d.get("total_weight")) or flt(d.get("weight_per_unit")) * flt(d.stock_qty),
				"purchase_receipt_item": d.name, "po_detail": d.get("purchase_order_item"),
			})

	@frappe.whitelist()
	def load_receipt(self):
		self.set_receipt_details()
		self.set_items_from_receipt()
		self.fetch_charges()

	@frappe.whitelist()
	def fetch_charges(self):
		"""Rebuild auto charges (rows with a Source); manually entered rows are kept."""
		acc = get_company_accounts(self.company)
		settings = get_settings()
		self.set("charges", [c for c in self.charges if not c.source])
		receipt_value = sum(flt(d.base_amount) for d in self.items)

		def add(charge_type, amount, account, source, description=None):
			if flt(amount) > 0:
				self.append("charges", {"charge_type": charge_type, "amount": flt(amount, 2), "expense_account": account,
										"description": description or charge_type, "source": source,
										"include_in_landed_cost": 1})

		has_gd = False
		if self.customs_clearance and frappe.db.get_value("Customs Clearance", self.customs_clearance, "docstatus") == 1:
			has_gd = True
			gd = frappe.get_doc("Customs Clearance", self.customs_clearance)
			src = f"GD {gd.gd_no}"
			add("Customs Duty", gd.total_customs_duty, acc.get("customs_duty_account"), src)
			add("Additional Customs Duty", gd.total_acd, acc.get("customs_duty_account"), src)
			add("Regulatory Duty", gd.total_rd, acc.get("customs_duty_account"), src)
			if settings.include_sales_tax_in_landed_cost:
				add("Sales Tax (Non-adjustable)", flt(gd.total_sales_tax) + flt(gd.total_additional_sales_tax),
					acc.get("customs_duty_account"), src)

		if self.letter_of_credit and frappe.db.get_value("Letter of Credit", self.letter_of_credit, "docstatus") == 1:
			lc = frappe.db.get_value("Letter of Credit", self.letter_of_credit,
									 ["total_charges", "base_lc_amount", "lc_no"], as_dict=True)
			share = min(receipt_value / flt(lc.base_lc_amount), 1) if flt(lc.base_lc_amount) else 1
			add("LC / Bank Charges", flt(lc.total_charges) * share, acc.get("bank_charges_account"), f"LC {lc.lc_no}")

		if self.import_shipment and frappe.db.get_value("Shipping Document", self.import_shipment, "docstatus") == 1:
			shp = frappe.db.get_value("Shipping Document", self.import_shipment,
									  ["total_charges", "base_invoice_amount", "commercial_invoice_no"], as_dict=True)
			share = min(receipt_value / flt(shp.base_invoice_amount), 1) if flt(shp.base_invoice_amount) else 1
			add("LC / Bank Charges", flt(shp.total_charges) * share, acc.get("bank_charges_account"),
				f"Shipping Doc {self.import_shipment}", f"Shipment charges CI {shp.commercial_invoice_no or ''}")

		if self.purchase_order:
			po = frappe.get_doc("Purchase Order", self.purchase_order)
			share = min(receipt_value / flt(po.base_net_total), 1) if flt(po.base_net_total) else 0
			src = "PO Estimate"
			if po.get("shipping_term") in BUYER_PAYS_FREIGHT:
				add("Freight", flt(po.get("est_freight")) * share, acc.get("freight_account"), src)
			if po.get("shipping_term") not in SELLER_PAYS_INSURANCE:
				add("Insurance", flt(po.get("est_insurance")) * share, acc.get("freight_account"), src)
			if not has_gd:
				add("Customs Duty", flt(po.get("est_customs_duty")) * share, acc.get("customs_duty_account"), src)
				add("Import Taxes", flt(po.get("est_import_taxes")) * share, acc.get("customs_duty_account"), src)
			add("Clearing Charges", flt(po.get("est_clearing_charges")) * share, acc.get("clearing_account"), src)
			add("Port Charges", flt(po.get("est_port_charges")) * share, acc.get("clearing_account"), src)
			add("Other Import Expenses", flt(po.get("est_other_import_expenses")) * share,
				acc.get("other_import_expense_account"), src)
		self.allocate_charges()

	def allocate_charges(self):
		basis_field = {"Amount": "base_amount", "Qty": "qty", "Weight": "total_weight"}.get(
			self.distribute_charges_based_on or "Amount", "base_amount")
		self.total_item_value = flt(sum(flt(d.base_amount) for d in self.items), 2)
		self.total_charges = flt(sum(flt(c.amount) for c in self.charges), 2)
		landed = flt(sum(flt(c.amount) for c in self.charges if c.include_in_landed_cost), 2)
		self.total_landed_charges = landed
		total_basis = sum(flt(d.get(basis_field)) for d in self.items)
		if landed and not total_basis:
			frappe.throw(_("Cannot distribute charges: total {0} of items is zero.")
						 .format(self.distribute_charges_based_on))
		allocated_sum = 0.0
		for i, d in enumerate(self.items):
			if i == len(self.items) - 1:
				d.allocated_charges = flt(landed - allocated_sum, 2)
			else:
				d.allocated_charges = flt(landed * flt(d.get(basis_field)) / total_basis, 2) if total_basis else 0
				allocated_sum += d.allocated_charges
			d.landed_cost_amount = flt(flt(d.base_amount) + d.allocated_charges, 2)
			d.landed_cost_per_unit = flt(d.landed_cost_amount / flt(d.qty), 4) if flt(d.qty) else 0
		self.estimated_landed_cost = flt(self.total_item_value + landed, 2)
		self.landed_cost_percent = flt(landed / self.total_item_value * 100, 2) if self.total_item_value else 0
