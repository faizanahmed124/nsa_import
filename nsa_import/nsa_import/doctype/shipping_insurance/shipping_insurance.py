"""Shipping Insurance - insurance control document created from a Shipping Document.

Policy utilisation is tracked per policy:
  policy key          = Policy Number, or (Letter of Credit + Insurance Company) until the number is known
  Utilized by others  = sum of Insurance Amount of other submitted Shipping Insurance on the same policy
  Balance Insurance   = Insurance Total Policy - Utilized by others - this Insurance Amount
  Premium Amount      = Insurance Amount x Premium Rate / 100
  PKR amounts         = amount x Exchange Rate

Status after submit
  Submitted           policy number not yet entered
  Policy Issued       policy number entered, balance left, only this shipment on the policy
  Partially Utilized  balance left, more than one shipment on the policy
  Fully Utilized      no balance left
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate

from nsa_import.utils import get_company_currency, get_settings


def policy_key(policy_number, letter_of_credit, insurance_company, company=None):
	number = (policy_number or "").strip().upper()
	if number:
		return f"POL:{company or ''}:{number}"
	return f"LC:{letter_of_credit or ''}:{(insurance_company or '').strip().upper()}"


def refresh_policy(key):
	"""Recompute utilisation, balance and status of every submitted document on a policy."""
	if not key:
		return
	docs = frappe.get_all("Shipping Insurance", filters={"policy_key": key, "docstatus": 1},
						  fields=["name", "insurance_amount", "insurance_total_policy", "policy_number"])
	total_used = sum(flt(d.insurance_amount) for d in docs)
	for d in docs:
		balance = flt(flt(d.insurance_total_policy) - total_used, 2)
		if not d.policy_number:
			status = "Submitted"
		elif balance <= 0.005:
			status = "Fully Utilized"
		elif len(docs) > 1:
			status = "Partially Utilized"
		else:
			status = "Policy Issued"
		frappe.db.set_value("Shipping Insurance", d.name, {
			"utilized_before": flt(total_used - flt(d.insurance_amount), 2),
			"balance_insurance": balance,
			"status": status,
		}, update_modified=False)


class ShippingInsurance(Document):
	# ------------------------------------------------------------------ hooks
	def validate(self):
		self.set_source_values()
		self.validate_source()
		self.set_defaults()
		self.validate_dates()
		self.calculate_amounts()
		self.allocate_items()
		self.validate_balance()
		if self.docstatus == 0:
			self.status = "Draft"

	def before_update_after_submit(self):
		self.validate_dates()
		self.policy_key = policy_key(self.policy_number, self.letter_of_credit, self.insurance_company, self.company)
		self.validate_unique_policy_company()

	def on_update_after_submit(self):
		before = self.get_doc_before_save()
		if before and before.policy_key and before.policy_key != self.policy_key:
			refresh_policy(before.policy_key)
		refresh_policy(self.policy_key)

	def on_submit(self):
		refresh_policy(self.policy_key)

	def on_cancel(self):
		self.db_set("status", "Cancelled")
		refresh_policy(self.policy_key)

	# -------------------------------------------------------------- source
	def set_source_values(self):
		"""Shipping Document -> PO / LC / Supplier / shipment data (read-only on this document)."""
		if not self.shipping_document or self.docstatus != 0:
			return
		sd = frappe.db.get_value(
			"Shipping Document", self.shipping_document,
			["purchase_order", "letter_of_credit", "lc_no", "supplier", "supplier_name", "company", "currency",
			 "exchange_rate", "invoice_amount", "vessel_flight_no", "bl_awb_no", "eta", "port_of_loading",
			 "port_of_discharge"], as_dict=True)
		if not sd:
			frappe.throw(_("Shipping Document {0} not found.").format(self.shipping_document))
		self.update({
			"purchase_order": sd.purchase_order, "letter_of_credit": sd.letter_of_credit, "lc_no": sd.lc_no,
			"supplier": sd.supplier, "supplier_name": sd.supplier_name, "company": sd.company,
			"invoice_currency": sd.currency, "invoice_value_fc": flt(sd.invoice_amount),
		})
		for target, value in (("vessel_name", sd.vessel_flight_no), ("bl_awb_no", sd.bl_awb_no), ("eta", sd.eta),
							  ("port_of_loading", sd.port_of_loading), ("port_of_discharge", sd.port_of_discharge)):
			if not self.get(target) and value:
				self.set(target, value)
		if self.letter_of_credit:
			self.bank = frappe.db.get_value("Letter of Credit", self.letter_of_credit, "issuing_bank")
		self._sd = sd

	def validate_source(self):
		sd = frappe.db.get_value("Shipping Document", self.shipping_document,
								 ["docstatus", "purchase_order", "letter_of_credit", "supplier"], as_dict=True)
		if not sd or sd.docstatus != 1:
			frappe.throw(_("Shipping Document {0} must be submitted before creating Shipping Insurance.")
						 .format(self.shipping_document))
		if sd.purchase_order != self.purchase_order or (sd.letter_of_credit or None) != (self.letter_of_credit or None):
			frappe.throw(_("PO / Letter of Credit must match Shipping Document {0}.").format(self.shipping_document))
		if sd.supplier != self.supplier:
			frappe.throw(_("Supplier must match Shipping Document {0}.").format(self.shipping_document))
		if frappe.db.get_value("Purchase Order", self.purchase_order, "purchase_type") != "Import":
			frappe.throw(_("Shipping Insurance is only for the Import flow."))

	def set_defaults(self):
		if self.docstatus != 0:
			return
		company_ccy = get_company_currency(self.company) if self.company else None
		lc = frappe._dict()
		if self.letter_of_credit:
			lc = frappe.db.get_value("Letter of Credit", self.letter_of_credit,
									 ["insurance_company", "insurance_policy_no", "insurance_limit",
									  "insurance_expiry_date", "currency"], as_dict=True) or frappe._dict()
		if not self.insurance_company and lc.insurance_company:
			self.insurance_company = lc.insurance_company
		if not self.policy_number and lc.insurance_policy_no:
			self.policy_number = lc.insurance_policy_no
		if not self.policy_expiry_date and lc.insurance_expiry_date:
			self.policy_expiry_date = lc.insurance_expiry_date
		if not self.currency:
			self.currency = self.invoice_currency or company_ccy
		if self.currency == company_ccy:
			self.exchange_rate = 1
		elif self.currency == self.invoice_currency and (not flt(self.exchange_rate) or flt(self.exchange_rate) == 1):
			self.exchange_rate = flt(getattr(self, "_sd", {}).get("exchange_rate")) or \
				flt(frappe.db.get_value("Shipping Document", self.shipping_document, "exchange_rate"))
		if flt(self.exchange_rate) <= 0:
			frappe.throw(_("Exchange Rate must be greater than zero."))
		if not flt(self.insurance_total_policy) and lc.insurance_limit and lc.currency == self.currency:
			self.insurance_total_policy = lc.insurance_limit
		if not flt(self.insurance_amount):
			self.insurance_amount = flt(self.invoice_value_in_policy_currency()
										* (1 + flt(get_settings().insured_value_markup_percent) / 100), 2)

	def invoice_value_in_policy_currency(self):
		if self.currency == self.invoice_currency:
			return flt(self.invoice_value_fc)
		sd_rate = flt(frappe.db.get_value("Shipping Document", self.shipping_document, "exchange_rate")) or 1
		return flt(self.invoice_value_fc) * sd_rate / (flt(self.exchange_rate) or 1)

	def validate_dates(self):
		if self.policy_start_date and self.policy_expiry_date and \
				getdate(self.policy_expiry_date) < getdate(self.policy_start_date):
			frappe.throw(_("Policy Expiry Date cannot be earlier than Policy Start Date."))
		if self.policy_date and self.policy_expiry_date and getdate(self.policy_expiry_date) < getdate(self.policy_date):
			frappe.throw(_("Policy Expiry Date cannot be earlier than Policy Date."))
		if self.eta and self.policy_expiry_date and getdate(self.policy_expiry_date) < getdate(self.eta):
			frappe.msgprint(_("Policy expires before the shipment ETA."), indicator="orange", alert=True)

	def validate_unique_policy_company(self):
		"""The same policy number must belong to one insurance company."""
		if not self.policy_number:
			return
		other = frappe.db.get_value(
			"Shipping Insurance",
			{"policy_key": self.policy_key, "docstatus": ["<", 2], "name": ["!=", self.name or ""],
			 "insurance_company": ["!=", self.insurance_company]}, ["name", "insurance_company"], as_dict=True)
		if other:
			frappe.throw(_("Policy Number {0} is already used for {1} in {2}.")
						 .format(self.policy_number, other.insurance_company, other.name))

	# ------------------------------------------------------------- amounts
	def calculate_amounts(self):
		for f in ("insurance_total_policy", "insurance_amount", "marine_bill_value"):
			if flt(self.get(f)) < 0:
				frappe.throw(_("{0} cannot be negative.").format(_(self.meta.get_label(f))))
		if flt(self.insurance_amount) <= 0:
			frappe.throw(_("Insurance Amount must be greater than zero."))
		if flt(self.insurance_total_policy) <= 0:
			frappe.throw(_("Insurance Total Policy must be greater than zero."))
		if not 0 <= flt(self.premium_rate) <= 100:
			frappe.throw(_("Premium Rate must be between 0 and 100."))
		self.premium_amount = flt(flt(self.insurance_amount) * flt(self.premium_rate) / 100, 2)
		self.base_insurance_amount = flt(flt(self.insurance_amount) * flt(self.exchange_rate), 2)
		self.base_premium_amount = flt(self.premium_amount * flt(self.exchange_rate), 2)
		self.policy_key = policy_key(self.policy_number, self.letter_of_credit, self.insurance_company, self.company)
		self.validate_unique_policy_company()

	def allocate_items(self, force=False):
		"""Item Insurance Amount: auto-allocated by item Amount when empty; must add up to the header."""
		items = self.get("items") or []
		if not items:
			return
		total_alloc = sum(flt(d.insurance_amount) for d in items)
		if force or not total_alloc:
			base = sum(flt(d.amount) for d in items)
			remaining = flt(self.insurance_amount)
			for i, d in enumerate(items):
				if i == len(items) - 1:
					d.insurance_amount = flt(remaining, 2)
				else:
					share = flt(d.amount) / base if base else 1.0 / len(items)
					d.insurance_amount = flt(flt(self.insurance_amount) * share, 2)
					remaining -= d.insurance_amount
			return
		if abs(flt(total_alloc, 2) - flt(self.insurance_amount, 2)) > 0.05:
			frappe.throw(_("Item Insurance Amounts ({0}) must add up to the Insurance Amount ({1}). "
						   "Use 'Allocate Insurance Amount to Items'.").format(flt(total_alloc, 2),
																			 flt(self.insurance_amount, 2)))

	def validate_balance(self):
		used = flt(frappe.db.sql(
			"""select coalesce(sum(insurance_amount), 0) from `tabShipping Insurance`
			where policy_key=%s and docstatus=1 and name!=%s""", (self.policy_key, self.name or ""))[0][0])
		self.utilized_before = flt(used, 2)
		self.balance_insurance = flt(flt(self.insurance_total_policy) - used - flt(self.insurance_amount), 2)
		if self.balance_insurance < -0.005:
			if not self.allow_over_insurance:
				frappe.throw(_("Insurance Amount {0} exceeds the available policy balance {1}. "
							   "An authorized user can tick 'Allow Insurance Amount above Balance'.")
							 .format(flt(self.insurance_amount, 2), flt(self.insurance_total_policy - used, 2)))
			role = get_settings().insurance_override_role or "Accounts Manager"
			roles = frappe.get_roles()
			if role not in roles and "System Manager" not in roles:
				frappe.throw(_("Only users with role {0} can insure above the policy balance.").format(role),
							 frappe.PermissionError)

	@frappe.whitelist()
	def reallocate(self):
		self.allocate_items(force=True)
		return self
