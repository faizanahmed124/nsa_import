"""Keep Letter of Credit -> Expense Booked in sync with Journal Entries linked to the LC."""

import frappe


def on_submit(doc, method=None):
	_sync(doc)


def on_cancel(doc, method=None):
	_sync(doc)


def _sync(doc):
	name = doc.get("letter_of_credit")
	if not name or not frappe.db.exists("Letter of Credit", name):
		return
	lc = frappe.get_doc("Letter of Credit", name)
	if lc.docstatus != 1:
		return
	lc.sync_expense_booked()
