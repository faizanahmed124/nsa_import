"""Shared hooks for Purchase Receipt and Purchase Invoice: keep Purchase Type downstream."""
import frappe

from nsa_import.utils import refresh_po_import_status


def _first_po(doc):
	return next((d.purchase_order for d in doc.items if d.get("purchase_order")), None)


def validate(doc, method=None):
	po = _first_po(doc)
	if po:
		po_data = frappe.db.get_value("Purchase Order", po, ["purchase_type", "letter_of_credit"], as_dict=True) or {}
		if po_data.get("purchase_type"):
			doc.purchase_type = po_data.purchase_type
		if not doc.get("letter_of_credit") and po_data.get("letter_of_credit"):
			doc.letter_of_credit = po_data.letter_of_credit
	if not doc.get("purchase_type"):
		doc.purchase_type = "Local"

	if doc.doctype == "Purchase Invoice" and doc.purchase_type == "Import" and not doc.get("import_shipment"):
		pr = next((d.purchase_receipt for d in doc.items if d.get("purchase_receipt")), None)
		if pr:
			refs = frappe.db.get_value("Purchase Receipt", pr, ["import_shipment", "customs_clearance"], as_dict=True)
			doc.import_shipment = refs.import_shipment
			doc.customs_clearance = refs.customs_clearance


def on_submit(doc, method=None):
	if doc.get("import_shipment"):
		frappe.db.set_value("Import Shipment", doc.import_shipment, "status", "Received", update_modified=False)
	for po in {d.purchase_order for d in doc.items if d.get("purchase_order")}:
		refresh_po_import_status(po)


def on_cancel(doc, method=None):
	if doc.get("import_shipment"):
		shp = doc.import_shipment
		cleared = frappe.db.exists("Customs Clearance", {"import_shipment": shp, "docstatus": 1})
		arrived = frappe.db.get_value("Import Shipment", shp, "actual_arrival_date")
		status = "Cleared" if cleared else ("Arrived" if arrived else "In Transit")
		frappe.db.set_value("Import Shipment", shp, "status", status, update_modified=False)
	for po in {d.purchase_order for d in doc.items if d.get("purchase_order")}:
		refresh_po_import_status(po)
