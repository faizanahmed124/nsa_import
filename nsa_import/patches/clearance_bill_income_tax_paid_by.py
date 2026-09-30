"""Clearance Bill: Income Tax selections changed from 'Deduct By Agent / ATS' to 'Paid By Agent / ATS'."""

import frappe


def execute():
	if not frappe.db.table_exists("Clearance Bill"):
		return
	for col in ("income_tax_paid_by_agent", "income_tax_paid_by_ats"):
		if frappe.db.has_column("Clearance Bill", col):
			frappe.db.sql(f"update `tabClearance Bill` set `{col}` = 'Paid By Agent' where `{col}` = 'Deduct By Agent'")
			frappe.db.sql(f"update `tabClearance Bill` set `{col}` = 'Paid By ATS' where `{col}` = 'Deduct By ATS'")
