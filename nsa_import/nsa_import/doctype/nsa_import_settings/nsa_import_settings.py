import frappe
from frappe import _
from frappe.model.document import Document


class NSAImportSettings(Document):
	def validate(self):
		seen = set()
		for row in self.company_accounts:
			if row.company in seen:
				frappe.throw(_("Company {0} is repeated in accounts table.").format(row.company))
			seen.add(row.company)
