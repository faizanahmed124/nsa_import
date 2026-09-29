import frappe
from frappe import _
from frappe.model.document import Document


class PortOfLoading(Document):
	def validate(self):
		self.port = " ".join((self.port or "").split())
		if not self.port:
			frappe.throw(_("{0} cannot be blank.").format(_(self.meta.get_label("port"))))
		# duplicates are also blocked when only upper / lower case or spacing differs
		other = frappe.db.sql(
			"""select name from `tabPort Of Loading` where lower(port) = lower(%s) and name != %s limit 1""",
			(self.port, self.name or ""))
		if other:
			frappe.throw(_("Port Of Loading {0} already exists.").format(other[0][0]))
