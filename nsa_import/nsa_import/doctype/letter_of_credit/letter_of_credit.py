"""Letter of Credit - separate document linked to an Import Purchase Order.

Calculation rules (all charges in company currency):
  PO Qty                 = Purchase Order total qty
  PO Amount              = Purchase Order grand total (PO currency)
  LC Tolerance           = PO Amount x LC Tolerance % / 100            (PO / LC currency)
  LC Commission Amount   = Commission Base x Exchange Rate x LC Commission % / 100
                           Commission Base (Settings): LC Amount | PO Amount | LC Amount incl. Tolerance
  FED on Commission      = (LC Commission Amount [+ Amendment Commission]) x FED % / 100
  Total LC Charges       = Commission + FED + [LC AFTER] + SWIFT + Amendment Commission + SWIFT Amended
  Total Bank Charges     = Total LC Charges + Other Bank Charges table
  Total Expense Booked   = sum of Expense Booked rows
"""

from collections import OrderedDict

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, nowdate

from nsa_import.constants import LC_PAYMENT_TERMS
from nsa_import.utils import get_company_currency, get_settings, refresh_po_import_status

LOCKED_STATUSES = ("Closed", "Expired")
PERCENT_FIELDS = ("tolerance_percent", "lc_commission_percent", "fed_percent", "margin_percent")
NON_NEGATIVE_FIELDS = ("insurance_limit", "lc_after", "swift_charges", "amendment_commission",
					   "swift_charges_amended", "margin_amount")

PO_FIELDS = ["docstatus", "purchase_type", "company", "supplier", "supplier_name", "currency", "conversion_rate",
			 "grand_total", "total_qty", "pi_no", "pi_date", "import_payment_term", "lc_no", "lc_date", "lc_bank",
			 "shipping_term", "mode_of_shipment", "port_of_loading", "port_of_discharge",
			 "expected_shipment_date", "supplier_bank"]


def get_po_values(purchase_order):
	"""Return (fixed, defaults) for an LC created from `purchase_order`.

	fixed    - always taken from the PO and read-only on the LC
	defaults - pre-filled only when empty; user may change them
	"""
	po = frappe.db.get_value("Purchase Order", purchase_order, PO_FIELDS, as_dict=True)
	if not po:
		frappe.throw(_("Purchase Order {0} not found.").format(purchase_order))
	fixed = {
		"company": po.company, "supplier": po.supplier, "supplier_name": po.supplier_name,
		"currency": po.currency, "po_qty": flt(po.total_qty), "po_amount": flt(po.grand_total),
		"pi_no": po.pi_no, "pi_date": po.pi_date,
	}
	settings = get_settings()
	term = po.import_payment_term if po.import_payment_term in LC_PAYMENT_TERMS else None
	defaults = {
		"exchange_rate": po.conversion_rate, "lc_amount": po.grand_total, "lc_payment_term": term,
		"lc_type": "Usance" if term == "LC Usance" else "Sight", "lc_no": po.lc_no, "lc_date": po.lc_date,
		"issuing_bank": po.lc_bank, "shipping_term": po.shipping_term, "mode_of_shipment": po.mode_of_shipment,
		"port_of_loading": po.port_of_loading, "port_of_discharge": po.port_of_discharge,
		"latest_shipment_date": po.expected_shipment_date, "beneficiary_bank": po.supplier_bank,
		"lc_commission_percent": settings.default_lc_commission_percent,
		"fed_percent": settings.default_fed_percent,
	}
	return po, fixed, defaults


class LetterofCredit(Document):
	# ------------------------------------------------------------------ hooks
	def validate(self):
		self.set_po_values()
		self.validate_purchase_order()
		self.validate_lc_no()
		self.validate_values()
		self.apply_amendments()
		self.validate_dates()
		self.calculate_amounts()
		if self.docstatus == 0:
			self.status = "Draft"

	def before_submit(self):
		po_status = frappe.db.get_value("Purchase Order", self.purchase_order, "docstatus")
		if po_status != 1:
			frappe.throw(_("Submit Purchase Order {0} before submitting the Letter of Credit.")
						 .format(self.purchase_order))

	def before_update_after_submit(self):
		self.check_locked()
		self.validate_values()
		self.apply_amendments()
		self.validate_dates()
		self.calculate_amounts()

	def on_update_after_submit(self):
		self.update_utilization()

	def on_submit(self):
		self.db_set("status", "Opened")
		values = {"letter_of_credit": self.name}
		if self.lc_no:
			values["lc_no"] = self.lc_no
		if self.lc_date:
			values["lc_date"] = self.lc_date
		frappe.db.set_value("Purchase Order", self.purchase_order, values, update_modified=False)
		refresh_po_import_status(self.purchase_order)

	def on_cancel(self):
		self.ignore_linked_doctypes = ("Purchase Order", "Journal Entry", "GL Entry")
		self.db_set("status", "Cancelled")
		if frappe.db.get_value("Purchase Order", self.purchase_order, "letter_of_credit") == self.name:
			frappe.db.set_value("Purchase Order", self.purchase_order, "letter_of_credit", None, update_modified=False)
		refresh_po_import_status(self.purchase_order)

	# ------------------------------------------------------------ PO values
	def set_po_values(self):
		if not self.purchase_order or self.docstatus != 0:
			return
		_po, fixed, defaults = get_po_values(self.purchase_order)
		for k, v in fixed.items():
			self.set(k, v)  # read-only on the LC, always in sync with the PO
		for k, v in defaults.items():
			if not self.get(k) and v not in (None, ""):
				self.set(k, v)

	def validate_purchase_order(self):
		if not self.purchase_order:
			frappe.throw(_("Purchase Order is mandatory."))
		po = frappe.db.get_value("Purchase Order", self.purchase_order,
								 ["docstatus", "purchase_type", "company"], as_dict=True)
		if not po:
			frappe.throw(_("Purchase Order {0} not found.").format(self.purchase_order))
		if po.purchase_type != "Import":
			frappe.throw(_("Letter of Credit can only be linked with an Import Purchase Order. "
						   "{0} is a {1} Purchase Order.").format(self.purchase_order, po.purchase_type or "Local"))
		allowed = (0, 1) if get_settings().allow_lc_on_draft_po else (1,)
		if po.docstatus not in allowed:
			frappe.throw(_("Purchase Order {0} must be submitted before creating a Letter of Credit.")
						 .format(self.purchase_order) if po.docstatus == 0
						 else _("Purchase Order {0} is cancelled.").format(self.purchase_order))
		if self.company != po.company:
			frappe.throw(_("Company must match the Purchase Order company ({0}).").format(po.company))
		if self.docstatus == 0:
			other = frappe.db.get_value("Letter of Credit", {"purchase_order": self.purchase_order,
															 "docstatus": 1, "name": ["!=", self.name]}, "name")
			if other:
				frappe.msgprint(_("Letter of Credit {0} already exists against this Purchase Order.").format(other),
								indicator="orange", alert=True)

	def validate_lc_no(self):
		self.lc_no = (self.lc_no or "").strip() or None
		if not self.lc_no or not get_settings().lc_no_unique:
			return
		other = frappe.db.get_value("Letter of Credit", {"lc_no": self.lc_no, "docstatus": ["<", 2],
														 "name": ["!=", self.name]}, "name")
		if other:
			frappe.throw(_("LC Number {0} is already used in Letter of Credit {1}.").format(self.lc_no, other))

	def validate_values(self):
		for f in PERCENT_FIELDS:
			if not 0 <= flt(self.get(f)) <= 100:
				frappe.throw(_("{0} must be between 0 and 100.").format(_(self.meta.get_label(f))))
		for f in NON_NEGATIVE_FIELDS:
			if flt(self.get(f)) < 0:
				frappe.throw(_("{0} cannot be negative.").format(_(self.meta.get_label(f))))
		if flt(self.lc_amount) <= 0:
			frappe.throw(_("LC Amount must be greater than zero."))
		for d in self.get("charges") or []:
			if flt(d.amount) < 0:
				frappe.throw(_("Row {0}: Other Bank Charge cannot be negative.").format(d.idx))

	def apply_amendments(self):
		"""Latest amendment dates override the original ones."""
		rows = sorted(self.get("amendments") or [], key=lambda d: (getdate(d.amendment_date), d.idx))
		for d in rows:
			if d.new_expiry_date:
				self.expiry_date = d.new_expiry_date
			if d.new_latest_shipment_date:
				self.latest_shipment_date = d.new_latest_shipment_date

	def validate_dates(self):
		lc_date = getdate(self.lc_date) if self.lc_date else None
		expiry = getdate(self.expiry_date) if self.expiry_date else None
		latest = getdate(self.latest_shipment_date) if self.latest_shipment_date else None

		if lc_date and expiry and expiry < lc_date:
			frappe.throw(_("LC Expiry Date cannot be earlier than LC Date."))
		if lc_date and latest and latest < lc_date:
			frappe.throw(_("Latest Date of Shipment cannot be earlier than LC Date."))
		if expiry and latest and latest > expiry:
			frappe.throw(_("Latest Date of Shipment cannot be after LC Expiry Date."))

		warnings = []
		if self.plan_to_move and latest and getdate(self.plan_to_move) > latest:
			warnings.append(_("Plan To Move is after the Latest Date of Shipment."))
		if self.fi_validity and latest and getdate(self.fi_validity) < latest:
			warnings.append(_("FI Validity expires before the Latest Date of Shipment."))
		if self.insurance_expiry_date and latest and getdate(self.insurance_expiry_date) < latest:
			warnings.append(_("Insurance expires before the Latest Date of Shipment."))
		for w in warnings:
			frappe.msgprint(w, indicator="orange", alert=True)

	def check_locked(self):
		"""Closed / Expired LCs can only be changed by the role set in NSA Import Settings."""
		if self.flags.ignore_lock:
			return
		before = self.get_doc_before_save()
		status = before.status if before else self.status
		if status not in LOCKED_STATUSES:
			return
		role = get_settings().lc_closed_edit_role or "Accounts Manager"
		roles = frappe.get_roles()
		if role not in roles and "System Manager" not in roles:
			frappe.throw(_("Letter of Credit {0} is {1}. Only users with role {2} can modify it.")
						 .format(self.name, status, role), frappe.PermissionError)

	# ----------------------------------------------------------- amounts
	def effective_amount(self):
		return flt(self.lc_amount) + sum(flt(d.amount_change) for d in self.get("amendments") or [])

	def commission_base(self):
		basis = get_settings().lc_commission_base or "LC Amount"
		if basis == "PO Amount":
			amount = flt(self.po_amount)
		elif basis == "LC Amount incl. Tolerance":
			amount = flt(self.lc_amount) * (1 + flt(self.tolerance_percent) / 100)
		else:
			amount = flt(self.lc_amount)
		return amount * flt(self.exchange_rate)

	def calculate_amounts(self):
		settings = get_settings()
		if self.currency and self.company and self.currency == get_company_currency(self.company):
			self.exchange_rate = 1
		if flt(self.exchange_rate) <= 0:
			frappe.throw(_("Exchange Rate must be greater than zero."))

		effective = self.effective_amount()
		self.lc_tolerance_amount = flt(flt(self.po_amount) * flt(self.tolerance_percent) / 100, 2)
		self.max_lc_amount = flt(effective * (1 + flt(self.tolerance_percent) / 100), 2)
		self.base_lc_amount = flt(effective * flt(self.exchange_rate), 2)
		if flt(self.margin_percent):
			self.margin_amount = flt(self.base_lc_amount * flt(self.margin_percent) / 100, 2)

		self.lc_commission_amount = flt(self.commission_base() * flt(self.lc_commission_percent) / 100, 2)
		fed_base = flt(self.lc_commission_amount)
		if settings.fed_on_amendment_commission:
			fed_base += flt(self.amendment_commission)
		self.fed_on_commission = flt(fed_base * flt(self.fed_percent) / 100, 2)

		self.total_lc_charges = flt(sum(self.charge_heads(include_other=False).values()), 2)
		self.total_charges = flt(self.total_lc_charges + sum(flt(d.amount) for d in self.get("charges") or []), 2)
		self.balance_amount = flt(self.max_lc_amount - flt(self.shipped_amount), 2)
		self.calculate_expense_booked()

	def charge_heads(self, include_other=True):
		heads = OrderedDict([
			("LC Commission", flt(self.lc_commission_amount)),
			("FED on Commission", flt(self.fed_on_commission)),
			("LC AFTER", flt(self.lc_after) if get_settings().include_lc_after_in_charges else 0),
			("SWIFT Charges", flt(self.swift_charges)),
			("Amendment Commission", flt(self.amendment_commission)),
			("SWIFT Charges Amended", flt(self.swift_charges_amended)),
		])
		if include_other:
			heads["Other Bank Charges"] = sum(flt(d.amount) for d in self.get("charges") or [])
		return heads

	def booked_by_head(self):
		booked = {}
		for d in self.get("expense_booked") or []:
			booked[d.charge_head or "Other"] = booked.get(d.charge_head or "Other", 0) + flt(d.expense_amount)
		return booked

	def pending_by_head(self):
		booked = self.booked_by_head()
		return OrderedDict((h, flt(a - flt(booked.get(h)), 2)) for h, a in self.charge_heads().items()
						   if flt(a - flt(booked.get(h)), 2) > 0)

	def calculate_expense_booked(self):
		self.total_expense_booked = flt(sum(flt(d.expense_amount) for d in self.get("expense_booked") or []), 2)
		self.pending_lc_charges = flt(sum(self.pending_by_head().values()), 2)

	# ------------------------------------------------------- expense booked
	def sync_expense_booked(self, save=True):
		"""Rebuild auto rows from submitted Journal Entries linked to this LC; manual rows are kept."""
		lines = frappe.db.sql(
			"""select je.name as voucher, je.posting_date, jea.account, jea.nsa_lc_charge_head as head,
				(jea.debit - jea.credit) as amount, jea.user_remark, acc.root_type
			from `tabJournal Entry Account` jea
			join `tabJournal Entry` je on je.name = jea.parent
			left join `tabAccount` acc on acc.name = jea.account
			where je.docstatus = 1 and je.letter_of_credit = %s
			order by je.posting_date, je.name, jea.idx""",
			self.name, as_dict=True,
		)
		by_voucher = OrderedDict()
		for ln in lines:
			by_voucher.setdefault(ln.voucher, []).append(ln)

		auto = []
		for voucher, rows in by_voucher.items():
			tagged = [r for r in rows if r.head]
			# untagged manual JE: take debit lines on expense accounts
			use = tagged or [r for r in rows if r.root_type == "Expense" and flt(r.amount) > 0]
			for r in use:
				if flt(r.amount):
					auto.append({
						"charge_head": r.head or "Other", "expense_account": r.account,
						"expense_amount": flt(r.amount), "posting_date": r.posting_date,
						"reference_doctype": "Journal Entry", "reference_name": voucher,
						"remarks": r.user_remark, "is_auto": 1,
					})

		manual = [d for d in self.get("expense_booked") or [] if not d.is_auto]
		self.set("expense_booked", manual)
		for row in auto:
			self.append("expense_booked", row)
		for i, d in enumerate(self.expense_booked, 1):
			d.idx = i

		# a cancelled margin / charges JE is no longer the LC's journal entry
		if self.journal_entry and frappe.db.get_value("Journal Entry", self.journal_entry, "docstatus") == 2:
			self.journal_entry = None

		self.calculate_expense_booked()
		if save:
			self.flags.ignore_lock = True
			self.flags.ignore_permissions = True
			self.save()

	# ------------------------------------------------------- utilization
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

		still_expired = self.status == "Expired" and (
			not self.expiry_date or getdate(self.expiry_date) < getdate(nowdate()))
		if self.status == "Closed" or still_expired:
			status = self.status
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
