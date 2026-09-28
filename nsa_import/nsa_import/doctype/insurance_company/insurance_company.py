import frappe
from frappe import _
from frappe.model.document import Document


class InsuranceCompany(Document):
	def validate(self):
		self.insurance_company = (self.insurance_company or "").strip()
		if not self.insurance_company:
			frappe.throw(_("Insurance Company cannot be blank."))
		other = frappe.db.get_value("Insurance Company", {"insurance_company": self.insurance_company,
														  "name": ["!=", self.name or ""]}, "name")
		if other:
			frappe.throw(_("Insurance Company {0} already exists.").format(self.insurance_company))
