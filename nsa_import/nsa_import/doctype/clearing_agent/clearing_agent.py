import frappe
from frappe import _
from frappe.model.document import Document


class ClearingAgent(Document):
	def validate(self):
		self.clearing_agent_name = " ".join((self.clearing_agent_name or "").split())
		if not self.clearing_agent_name:
			frappe.throw(_("{0} cannot be blank.").format(_(self.meta.get_label("clearing_agent_name"))))
		# duplicates are also blocked when only upper / lower case or spacing differs
		other = frappe.db.sql(
			"""select name from `tabClearing Agent` where lower(clearing_agent_name) = lower(%s) and name != %s limit 1""",
			(self.clearing_agent_name, self.name or ""))
		if other:
			frappe.throw(_("Clearing Agent {0} already exists.").format(other[0][0]))
