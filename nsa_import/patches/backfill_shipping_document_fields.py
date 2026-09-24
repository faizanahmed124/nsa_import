"""Fill the new Shipping Document fields on documents created before the redesign."""

import frappe


def execute():
	if not frappe.db.table_exists("Shipping Document Item") or not frappe.db.has_column("Shipping Document Item", "shipped_qty"):
		return
	frappe.db.sql("""update `tabShipping Document Item`
		set shipped_qty = qty where ifnull(shipped_qty, 0) = 0 and ifnull(qty, 0) != 0""")
	frappe.db.sql("""update `tabShipping Document Item`
		set uom_conversion_factor = 1 where ifnull(uom_conversion_factor, 0) = 0""")
	frappe.db.sql("""update `tabShipping Document Item` set po_uom = uom where ifnull(po_uom, '') = ''""")
	frappe.db.sql("""update `tabShipping Document Item`
		set po_amount = ifnull(ordered_qty, 0) * ifnull(rate, 0) where ifnull(po_amount, 0) = 0""")
	frappe.db.sql("""update `tabShipping Document` s
		join `tabLetter of Credit` l on l.name = s.letter_of_credit
		set s.lc_no = l.lc_no where ifnull(s.lc_no, '') = ''""")
	frappe.db.sql("""update `tabShipping Document` s
		set s.total_shipped_qty = (select coalesce(sum(i.shipped_qty), 0) from `tabShipping Document Item` i
			where i.parent = s.name and i.parenttype = 'Shipping Document')
		where ifnull(s.total_shipped_qty, 0) = 0""")
