"""Insurance Policy - policy limit, validity and balance of an Insurance Company (via a Bank).

Balance Insurance = Insurance Limit - sum of Insurance Amount of submitted Shipping Insurance on this policy.
Cancelled Shipping Insurance releases its amount automatically. The balance is never typed in; the
utilization history is the list of Shipping Insurance documents (Connections / Insurance Policy Register).
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, nowdate


class InsurancePolicy(Document):
	def validate(self):
		self.policy_no = (self.policy_no or "").strip()
		if not self.policy_no:
			frappe.throw(_("Policy cannot be blank."))
		other = frappe.db.get_value("Insurance Policy", {"insurance_company": self.insurance_company,
														 "policy_no": self.policy_no, "name": ["!=", self.name or ""]},
									"name")
		if other:
			frappe.throw(_("Policy {0} already exists for Insurance Company {1} ({2}).")
						 .format(self.policy_no, self.insurance_company, other))
		if self.policy_date and self.expiry_date and getdate(self.expiry_date) < getdate(self.policy_date):
			frappe.throw(_("Expiry Date cannot be earlier than Policy Date."))
		if flt(self.insurance_limit) < 0:
			frappe.throw(_("Insurance Limit must be greater than or equal to zero."))
		if self.bank_account:
			ba = frappe.db.get_value("Bank Account", self.bank_account, ["bank", "company"], as_dict=True)
			if ba and ba.bank and ba.bank != self.bank:
				frappe.throw(_("Bank Account {0} belongs to bank {1}, not {2}.").format(self.bank_account, ba.bank,
																						self.bank))
		used_currency = frappe.db.get_value("Shipping Insurance", {"insurance_policy": self.name, "docstatus": 1},
											"currency") if not self.is_new() else None
		if used_currency and used_currency != self.currency:
			frappe.throw(_("Currency cannot be changed: the policy is already used in {0}.").format(used_currency))
		self.update_balance(save=False)
		if flt(self.insurance_limit) < flt(self.utilized_amount):
			frappe.throw(_("Insurance Limit cannot be lower than the amount already utilized ({0}).")
						 .format(flt(self.utilized_amount, 2)))

	def get_utilized(self):
		if self.is_new():
			return 0.0
		return flt(frappe.db.sql(
			"""select coalesce(sum(insurance_amount), 0) from `tabShipping Insurance`
			where insurance_policy=%s and docstatus=1""", self.name)[0][0])

	def get_status(self, balance=None):
		balance = flt(self.insurance_limit) - self.get_utilized() if balance is None else balance
		if self.suspended:
			return "Suspended"
		if self.expiry_date and getdate(self.expiry_date) < getdate(nowdate()):
			return "Expired"
		if balance <= 0.005:
			return "Fully Utilized"
		return "Active"

	def update_balance(self, save=True):
		utilized = self.get_utilized()
		self.utilized_amount = flt(utilized, 2)
		self.balance_insurance = flt(flt(self.insurance_limit) - utilized, 2)
		self.status = self.get_status(self.balance_insurance)
		if save:
			self.db_set({"utilized_amount": self.utilized_amount, "balance_insurance": self.balance_insurance,
						 "status": self.status}, update_modified=False)


def update_all_policy_status():
	"""Daily: mark expired policies, refresh balances."""
	for name in frappe.get_all("Insurance Policy", filters={"status": ["!=", "Suspended"]}, pluck="name"):
		frappe.get_doc("Insurance Policy", name).update_balance()
