import frappe
from frappe import _
from frappe.model.document import Document


class VesselName(Document):
	def validate(self):
		self.vessel_name = " ".join((self.vessel_name or "").split())
		if not self.vessel_name:
			frappe.throw(_("{0} cannot be blank.").format(_(self.meta.get_label("vessel_name"))))
		# duplicates are also blocked when only upper / lower case or spacing differs
		other = frappe.db.sql(
			"""select name from `tabVessel Name` where lower(vessel_name) = lower(%s) and name != %s limit 1""",
			(self.vessel_name, self.name or ""))
		if other:
			frappe.throw(_("Vessel Name {0} already exists.").format(other[0][0]))
