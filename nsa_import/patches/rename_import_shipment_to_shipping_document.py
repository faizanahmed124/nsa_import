"""Import Shipment -> Shipping Document (runs before DocType sync, keeps existing data).

Order matters: the old documents-checklist child used the name "Shipping Document Item",
which now belongs to the PO items child.
"""

import frappe

RENAMES = (
	("Shipping Document Item", "Shipping Document Checklist"),  # old documents checklist
	("Import Shipment Item", "Shipping Document Item"),
	("Import Shipment", "Shipping Document"),
)


def execute():
	if not frappe.db.exists("DocType", "Import Shipment"):
		return  # fresh install or already renamed
	for old, new in RENAMES:
		if frappe.db.exists("DocType", old) and not frappe.db.exists("DocType", new):
			frappe.rename_doc("DocType", old, new, force=True)
	frappe.db.commit()
