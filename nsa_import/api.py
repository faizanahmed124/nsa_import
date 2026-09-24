"""NSA Import flow:

Purchase Order (Import) -> Letter of Credit -> Shipping Document (Shipping Docs)
 -> Customs Clearance (GD) -> Purchase Receipt -> Import Cost Sheet -> Landed Cost Voucher
 -> Purchase Invoice -> LC Retirement / Payment
"""

import frappe
from frappe import _
from frappe.utils import flt, nowdate

from nsa_import.utils import (
	build_journal_entry,
	get_company_accounts,
	get_settings,
	je_row,
	require_account,
)


def _submitted(doctype, name):
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	if doc.docstatus != 1:
		frappe.throw(_("{0} {1} must be submitted.").format(_(doctype), name))
	return doc


def _import_po(name):
	po = _submitted("Purchase Order", name)
	if po.get("purchase_type") != "Import":
		frappe.throw(_("Purchase Order {0} is not an Import Purchase Order.").format(name))
	return po


# ----------------------------------------------------------------------------
# Purchase Order -> Letter of Credit
# ----------------------------------------------------------------------------
@frappe.whitelist()
def get_lc_defaults(purchase_order):
	"""Values for a new Letter of Credit. `fixed` are read-only on the LC, `defaults` fill empty fields."""
	from nsa_import.nsa_import.doctype.letter_of_credit.letter_of_credit import get_po_values

	frappe.has_permission("Purchase Order", "read", purchase_order, throw=True)
	po, fixed, defaults = get_po_values(purchase_order)
	_check_lc_allowed(purchase_order, po)
	return {"fixed": fixed, "defaults": defaults}


@frappe.whitelist()
def get_lc_settings():
	"""LC calculation settings for the client (no read permission on NSA Import Settings needed)."""
	s = get_settings()
	keys = ("allow_lc_on_draft_po", "lc_commission_base", "default_lc_commission_percent", "default_fed_percent",
			"fed_on_amendment_commission", "include_lc_after_in_charges")
	return {k: s.get(k) for k in keys}


def _check_lc_allowed(name, po):
	if po.purchase_type != "Import":
		frappe.throw(_("Letter of Credit can only be created from an Import Purchase Order. {0} is a {1} Purchase Order.")
					 .format(name, po.purchase_type or "Local"))
	allowed = (0, 1) if get_settings().allow_lc_on_draft_po else (1,)
	if po.docstatus not in allowed:
		frappe.throw(_("Purchase Order {0} must be submitted before creating a Letter of Credit.").format(name))


@frappe.whitelist()
def make_letter_of_credit(source_name, target_doc=None, args=None):
	"""Used by PO -> Import -> Letter of Credit and by PO Connections -> Letter of Credit (+)."""
	data = get_lc_defaults(source_name)
	lc = frappe.new_doc("Letter of Credit")
	lc.purchase_order = source_name
	for k, v in {**data["defaults"], **data["fixed"]}.items():
		if v not in (None, ""):
			lc.set(k, v)
	return lc


@frappe.whitelist()
def close_letter_of_credit(name):
	lc = frappe.get_doc("Letter of Credit", name)
	lc.check_permission("write")
	lc.db_set("status", "Closed")
	return lc.status


# ----------------------------------------------------------------------------
# Shipping Document (created from Letter of Credit)
# ----------------------------------------------------------------------------
@frappe.whitelist()
def get_shipment_defaults(purchase_order, letter_of_credit=None):
	"""Header values from LC / PO and the PO items that are still open for shipment."""
	po = _import_po(purchase_order)
	lc = None
	if letter_of_credit:
		lc = _submitted("Letter of Credit", letter_of_credit)
		if lc.purchase_order != po.name:
			frappe.throw(_("Letter of Credit {0} belongs to a different Purchase Order.").format(lc.name))
	header = {
		"company": po.company, "supplier": po.supplier, "supplier_name": po.supplier_name, "currency": po.currency,
		"exchange_rate": po.conversion_rate, "pi_no": po.get("pi_no"), "mode_of_shipment": po.get("mode_of_shipment"),
		"shipping_term": po.get("shipping_term"), "port_of_loading": po.get("port_of_loading"),
		"port_of_discharge": po.get("port_of_discharge"), "country_of_origin": po.get("import_country_of_origin"),
		"etd": po.get("expected_shipment_date"), "eta": po.get("expected_arrival_date"),
		"clearing_agent": po.get("customs_clearing_agent"),
	}
	if lc:
		header.update({"letter_of_credit": lc.name, "lc_no": lc.lc_no, "currency": lc.currency,
					   "exchange_rate": lc.exchange_rate, "supplier_name": lc.supplier_name})
		for f in ("mode_of_shipment", "shipping_term", "port_of_loading", "port_of_discharge"):
			if lc.get(f):
				header[f] = lc.get(f)
		if lc.get("place"):
			header["final_destination"] = lc.place

	items = []
	for d in po.items:
		already = flt(d.get("shipped_qty"))
		pending = flt(d.qty) - already
		if pending <= 0:
			continue
		ratio = pending / flt(d.qty) if flt(d.qty) else 1
		items.append({
			"item_code": d.item_code, "item_name": d.item_name, "ordered_qty": d.qty, "uom": d.uom,
			"po_uom": d.uom, "uom_conversion_factor": 1, "rate": d.rate, "po_amount": d.amount,
			"shipped_qty": pending, "qty": pending, "amount": flt(pending * flt(d.rate), 2),
			"already_shipped_qty": already, "remaining_qty": 0,
			"country_of_origin": d.get("item_country_of_origin") or po.get("import_country_of_origin"),
			"hs_code": d.get("hs_code"), "warehouse": d.warehouse,
			"net_weight": flt(d.get("net_weight")) * ratio, "gross_weight": flt(d.get("gross_weight")) * ratio,
			"purchase_order": po.name, "po_detail": d.name,
		})
	return {"header": header, "items": items}


def _new_shipping_document(purchase_order, letter_of_credit=None):
	data = get_shipment_defaults(purchase_order, letter_of_credit)
	if not data["items"]:
		frappe.throw(_("All items of Purchase Order {0} are already shipped.").format(purchase_order))
	shp = frappe.new_doc("Shipping Document")
	shp.purchase_order = purchase_order
	for k, v in data["header"].items():
		if v not in (None, ""):
			shp.set(k, v)
	for row in data["items"]:
		shp.append("items", row)
	settings = get_settings()
	shp.fed_percent = settings.default_fed_percent
	shp.commission_percent = settings.default_shipment_commission_percent
	shp.packing_qty = sum(flt(r["shipped_qty"]) for r in data["items"])
	shp.set_default_documents()
	return shp


@frappe.whitelist()
def make_shipping_document_from_lc(source_name, target_doc=None, args=None):
	"""Letter of Credit -> Create -> Shipping Document (the standard route)."""
	lc = _submitted("Letter of Credit", source_name)
	if lc.status in ("Closed", "Expired", "Retired"):
		frappe.throw(_("Letter of Credit {0} is {1}.").format(lc.name, lc.status))
	if not lc.lc_no:
		frappe.throw(_("Enter the bank's LC Number on Letter of Credit {0} first.").format(lc.name))
	return _new_shipping_document(lc.purchase_order, lc.name)


@frappe.whitelist()
def make_shipping_document(source_name, target_doc=None, args=None, letter_of_credit=None):
	"""Purchase Order -> Shipping Document. Only allowed without an LC when enabled in NSA Import Settings."""
	if letter_of_credit:
		return make_shipping_document_from_lc(letter_of_credit)
	if not get_settings().allow_shipping_without_lc:
		frappe.throw(_("Shipping Document can only be created from a Letter of Credit."))
	return _new_shipping_document(source_name)


# backward compatible names
make_import_shipment = make_shipping_document
make_import_shipment_from_lc = make_shipping_document_from_lc


@frappe.whitelist()
def get_item_uom_factor(item_code, from_uom, to_uom):
	from nsa_import.utils import get_uom_factor

	return get_uom_factor(item_code, from_uom, to_uom)


@frappe.whitelist()
def get_shipping_settings():
	s = get_settings()
	return {"allow_shipping_without_lc": s.allow_shipping_without_lc,
			"default_fed_percent": s.default_fed_percent,
			"default_shipment_commission_percent": s.default_shipment_commission_percent,
			"shipment_qty_tolerance": s.shipment_qty_tolerance}


@frappe.whitelist()
def make_shipment_journal_entry(source_name):
	"""Draft JE for Shipping Document charges (Commission, FED, SWIFT), linked to the LC's Expense Booked."""
	shp = _submitted("Shipping Document", source_name)
	shp.check_permission("write")
	if shp.journal_entry and frappe.db.get_value("Journal Entry", shp.journal_entry, "docstatus") in (0, 1):
		return shp.journal_entry
	if not flt(shp.total_charges):
		frappe.throw(_("No charges to book on Shipping Document {0}.").format(shp.name))
	acc = get_company_accounts(shp.company)
	bank = None
	if shp.letter_of_credit:
		bank = frappe.db.get_value("Letter of Credit", shp.letter_of_credit, "bank_gl_account")
	bank = require_account(bank, "Bank GL Account (on the Letter of Credit)", shp.company)
	charges_acc = require_account(acc.get("bank_charges_account"), "LC / Bank Charges Account", shp.company)
	ref = shp.commercial_invoice_no or shp.name
	rows = []
	for head, amount, account in (
		("Shipment Commission", shp.commission_amount, charges_acc),
		("Shipment FED", shp.fed_amount, acc.get("fed_account") or charges_acc),
		("Shipment SWIFT Charges", shp.swift_charges, charges_acc),
	):
		if flt(amount):
			row = je_row(shp.company, account, debit=amount, remark=f"{head} - {ref} ({shp.name})")
			row["nsa_lc_charge_head"] = head
			rows.append(row)
	je = build_journal_entry(shp.company, shp.posting_date, rows, bank,
							 f"Shipping Document {shp.name} charges (LC {shp.lc_no or ''})", shp.lc_no or ref,
							 letter_of_credit=shp.letter_of_credit)
	shp.db_set("journal_entry", je.name)
	return je.name


# ----------------------------------------------------------------------------
# Customs Clearance (GD)
# ----------------------------------------------------------------------------
DUTY_MAP = {
	"cd_percent": "customs_duty_percent", "acd_percent": "acd_percent", "rd_percent": "rd_percent",
	"st_percent": "sales_tax_percent", "ast_percent": "ast_percent", "it_percent": "income_tax_percent",
}


def _duty_rates(hs_code):
	if not hs_code or not frappe.db.exists("Customs Tariff Number", hs_code):
		return {}
	meta = frappe.get_meta("Customs Tariff Number")
	fields = [f for f in DUTY_MAP if meta.has_field(f)]
	if not fields:
		return {}
	values = frappe.db.get_value("Customs Tariff Number", hs_code, fields, as_dict=True) or {}
	return {DUTY_MAP[k]: v for k, v in values.items() if v}


@frappe.whitelist()
def get_clearance_defaults(import_shipment):
	shp = _submitted("Shipping Document", import_shipment)
	header = {
		"purchase_order": shp.purchase_order, "letter_of_credit": shp.letter_of_credit, "company": shp.company,
		"supplier": shp.supplier, "clearing_agent": shp.clearing_agent, "bl_awb_no": shp.bl_awb_no,
		"currency": shp.currency, "exchange_rate": shp.exchange_rate,
		"landing_charges_percent": get_settings().landing_charges_percent,
	}
	items = []
	for d in shp.items:
		row = {"item_code": d.item_code, "item_name": d.item_name, "hs_code": d.hs_code, "qty": d.qty, "uom": d.get("po_uom") or d.uom,
			   "invoice_value": d.amount, "purchase_order": d.purchase_order, "po_detail": d.po_detail}
		row.update(_duty_rates(d.hs_code))
		items.append(row)
	return {"header": header, "items": items}


@frappe.whitelist()
def make_customs_clearance(source_name, target_doc=None, args=None):
	data = get_clearance_defaults(source_name)
	gd = frappe.new_doc("Customs Clearance")
	gd.import_shipment = source_name
	gd.posting_date = nowdate()
	for k, v in data["header"].items():
		if v is not None:
			gd.set(k, v)
	for row in data["items"]:
		gd.append("items", row)
	return gd


@frappe.whitelist()
def get_hs_duty_rates(hs_code):
	return _duty_rates(hs_code)


# ----------------------------------------------------------------------------
# Purchase Receipt (GRN)
# ----------------------------------------------------------------------------
def _make_pr(shipment, clearance=None):
	from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt

	qty_map, wh_map = {}, {}
	for d in shipment.items:
		if d.po_detail:
			qty_map[d.po_detail] = qty_map.get(d.po_detail, 0) + flt(d.qty)
			if d.get("warehouse"):
				wh_map[d.po_detail] = d.warehouse

	pr = make_purchase_receipt(shipment.purchase_order)
	items = []
	for d in pr.items:
		if d.get("purchase_order_item") in qty_map:
			qty = min(qty_map[d.purchase_order_item], flt(d.qty))
			if qty <= 0:
				continue
			d.qty = d.received_qty = qty
			d.rejected_qty = 0
			d.stock_qty = d.received_stock_qty = qty * flt(d.conversion_factor or 1)
			if wh_map.get(d.purchase_order_item):
				d.warehouse = wh_map[d.purchase_order_item]
			items.append(d)
	if not items:
		frappe.throw(_("Nothing pending to receive for shipment {0}.").format(shipment.name))
	pr.set("items", [])
	for i, d in enumerate(items, 1):
		d.idx = i
		pr.append("items", d)

	pr.purchase_type = "Import"
	pr.import_shipment = shipment.name
	pr.letter_of_credit = shipment.letter_of_credit
	pr.customs_clearance = clearance.name if clearance else None
	pr.supplier_delivery_note = shipment.commercial_invoice_no
	pr.run_method("calculate_taxes_and_totals")
	return pr


@frappe.whitelist()
def make_purchase_receipt_from_shipment(source_name, target_doc=None, args=None):
	shp = _submitted("Shipping Document", source_name)
	gd = frappe.db.get_value("Customs Clearance", {"import_shipment": shp.name, "docstatus": 1}, "name")
	return _make_pr(shp, frappe.get_doc("Customs Clearance", gd) if gd else None)


@frappe.whitelist()
def make_purchase_receipt_from_clearance(source_name, target_doc=None, args=None):
	gd = _submitted("Customs Clearance", source_name)
	return _make_pr(frappe.get_doc("Shipping Document", gd.import_shipment), gd)


# ----------------------------------------------------------------------------
# Import Cost Sheet -> Landed Cost Voucher
# ----------------------------------------------------------------------------
@frappe.whitelist()
def make_import_cost_sheet(source_name, target_doc=None, args=None):
	pr = _submitted("Purchase Receipt", source_name)
	cs = frappe.new_doc("Import Cost Sheet")
	cs.purchase_receipt = pr.name
	cs.posting_date = nowdate()
	cs.load_receipt()
	return cs


@frappe.whitelist()
def make_landed_cost_voucher(source_name):
	cs = _submitted("Import Cost Sheet", source_name)
	if cs.landed_cost_voucher and frappe.db.exists("Landed Cost Voucher", cs.landed_cost_voucher):
		return cs.landed_cost_voucher
	pr = frappe.get_doc("Purchase Receipt", cs.purchase_receipt)

	lcv = frappe.new_doc("Landed Cost Voucher")
	lcv.company = cs.company
	lcv.posting_date = cs.posting_date
	lcv.distribute_charges_based_on = "Distribute Manually" if cs.distribute_charges_based_on == "Weight" \
		else cs.distribute_charges_based_on
	lcv.append("purchase_receipts", {
		"receipt_document_type": "Purchase Receipt", "receipt_document": pr.name, "supplier": pr.supplier,
		"posting_date": pr.posting_date, "grand_total": pr.base_grand_total,
	})
	lcv.get_items_from_purchase_receipts()

	company_currency = frappe.get_cached_value("Company", cs.company, "default_currency")
	for c in cs.charges:
		if c.include_in_landed_cost and flt(c.amount):
			lcv.append("taxes", {
				"expense_account": c.expense_account, "description": f"{c.charge_type}: {c.description or ''}".strip(": "),
				"amount": flt(c.amount), "base_amount": flt(c.amount), "exchange_rate": 1,
				"account_currency": company_currency,
			})

	if lcv.distribute_charges_based_on == "Distribute Manually":
		alloc = {d.purchase_receipt_item: flt(d.allocated_charges) for d in cs.items}
		for d in lcv.items:
			d.applicable_charges = alloc.get(d.purchase_receipt_item, 0)

	lcv.purchase_type = "Import"
	lcv.import_cost_sheet = cs.name
	lcv.insert()
	cs.db_set("landed_cost_voucher", lcv.name)
	return lcv.name


# ----------------------------------------------------------------------------
# LC Retirement
# ----------------------------------------------------------------------------
@frappe.whitelist()
def get_retirement_defaults(letter_of_credit):
	lc = _submitted("Letter of Credit", letter_of_credit)
	balance = flt(lc.shipped_amount) - flt(lc.retired_amount)
	margin_left = flt(lc.margin_amount) - flt(frappe.db.sql(
		"select coalesce(sum(margin_adjusted),0) from `tabLC Retirement` where letter_of_credit=%s and docstatus=1",
		lc.name)[0][0])
	return {
		"purchase_order": lc.purchase_order, "supplier": lc.supplier, "company": lc.company, "currency": lc.currency,
		"lc_no": lc.lc_no, "exchange_rate": lc.exchange_rate, "amount": balance if balance > 0 else 0,
		"margin_adjusted": margin_left if margin_left > 0 else 0,
	}


@frappe.whitelist()
def make_lc_retirement(source_name, target_doc=None, args=None):
	doc = frappe.new_doc("LC Retirement")
	doc.letter_of_credit = source_name
	for k, v in get_retirement_defaults(source_name).items():
		doc.set(k, v)
	return doc


@frappe.whitelist()
def make_lc_retirement_from_shipment(source_name, target_doc=None, args=None):
	shp = _submitted("Shipping Document", source_name)
	if not shp.letter_of_credit:
		frappe.throw(_("Shipment {0} is not against a Letter of Credit.").format(shp.name))
	doc = make_lc_retirement(shp.letter_of_credit)
	doc.import_shipment = shp.name
	doc.amount = shp.invoice_amount
	return doc


# ----------------------------------------------------------------------------
# Draft Journal Entries
# ----------------------------------------------------------------------------
@frappe.whitelist()
def make_lc_journal_entry(source_name):
	"""Draft Journal Entry for LC margin (first time) and all LC charges not yet booked.

	Charge lines are tagged with their charge head; when the JE is submitted they are copied to the
	LC's Expense Booked tab automatically.
	"""
	lc = _submitted("Letter of Credit", source_name)
	lc.check_permission("write")
	draft = frappe.db.get_value("Journal Entry", {"letter_of_credit": lc.name, "docstatus": 0}, "name")
	if draft:
		frappe.msgprint(_("Draft Journal Entry {0} already exists for this LC.").format(draft), alert=True)
		return draft

	acc = get_company_accounts(lc.company)
	bank = require_account(lc.bank_gl_account, "Bank GL Account (on the LC)", lc.company)
	ref = lc.lc_no or lc.name
	rows = []

	# margin is booked once, with the first LC journal entry
	if flt(lc.margin_amount) and not lc.journal_entry:
		rows.append(je_row(lc.company, require_account(acc.get("lc_margin_account"), "LC Margin Account", lc.company),
						   debit=lc.margin_amount, remark=f"LC Margin {ref}"))

	def charges_account():
		return require_account(acc.get("bank_charges_account"), "LC / Bank Charges Account", lc.company)

	def tagged(row, head):
		row["nsa_lc_charge_head"] = head
		return row

	pending = lc.pending_by_head()
	booked = lc.booked_by_head()
	for head, amount in pending.items():
		if head == "Other Bank Charges" and not flt(booked.get(head)):
			for c in lc.charges:  # nothing booked yet: book row by row with their own accounts
				if flt(c.amount):
					rows.append(tagged(je_row(lc.company, c.account or charges_account(), debit=c.amount,
											  remark=f"{c.charge_type} - LC {ref}"), head))
			continue
		account = charges_account()
		if head == "FED on Commission" and acc.get("fed_account"):
			account = acc.get("fed_account")
		rows.append(tagged(je_row(lc.company, account, debit=amount, remark=f"{head} - LC {ref}"), head))

	if not rows:
		frappe.throw(_("Nothing to book: margin is already booked and all LC charges are in Expense Booked."))
	je = build_journal_entry(lc.company, lc.lc_date or nowdate(), rows, bank,
							 f"LC {ref} margin & charges ({lc.name})", ref, letter_of_credit=lc.name)
	if not lc.journal_entry:
		lc.db_set("journal_entry", je.name)
	return je.name


@frappe.whitelist()
def sync_lc_expenses(name):
	lc = frappe.get_doc("Letter of Credit", name)
	lc.check_permission("write")
	lc.sync_expense_booked()
	return lc.total_expense_booked


@frappe.whitelist()
def make_duty_journal_entry(source_name):
	gd = _submitted("Customs Clearance", source_name)
	if gd.journal_entry:
		return gd.journal_entry
	acc = get_company_accounts(gd.company)
	settings = get_settings()
	paid_through = require_account(gd.paid_through, "Paid Through (on the GD)", gd.company)
	duty_acc = require_account(acc.get("customs_duty_account"), "Customs Duty Account", gd.company)
	date = gd.payment_date or gd.gd_date
	rows = []
	duties = flt(gd.total_duties_landed)
	st = flt(gd.total_sales_tax) + flt(gd.total_additional_sales_tax)
	if settings.include_sales_tax_in_landed_cost:
		duties += st
		st = 0
	if duties:
		rows.append(je_row(gd.company, duty_acc, debit=duties, remark=f"Customs duties GD {gd.gd_no}"))
	if st:
		rows.append(je_row(gd.company, require_account(acc.get("sales_tax_account"), "Input Sales Tax Account", gd.company),
						   debit=st, remark=f"Import sales tax GD {gd.gd_no}"))
	if flt(gd.total_income_tax):
		rows.append(je_row(gd.company, require_account(acc.get("income_tax_account"), "Advance Income Tax Account", gd.company),
						   debit=gd.total_income_tax, remark=f"Import income tax GD {gd.gd_no}"))
	if not rows:
		frappe.throw(_("No duties or taxes to book."))
	je = build_journal_entry(gd.company, date, rows, paid_through, f"Duty & taxes GD {gd.gd_no} ({gd.name})",
							 gd.psid_no or gd.gd_no)
	gd.db_set("journal_entry", je.name)
	return je.name


@frappe.whitelist()
def make_retirement_journal_entry(source_name):
	doc = _submitted("LC Retirement", source_name)
	if doc.journal_entry:
		return doc.journal_entry
	from erpnext.accounts.party import get_party_account

	acc = get_company_accounts(doc.company)
	paid_from = require_account(doc.paid_from_account, "Paid From (Bank / Loan Account)", doc.company)
	payable = get_party_account("Supplier", doc.supplier, doc.company)
	payable_ccy = frappe.get_cached_value("Account", payable, "account_currency")

	rows = [je_row(doc.company, payable, debit=doc.base_amount, party_type="Supplier", party=doc.supplier,
				   exchange_rate=doc.exchange_rate,
				   amount_in_account_currency=doc.amount if payable_ccy == doc.currency else None,
				   remark=f"LC {doc.lc_no} retirement")]
	if flt(doc.bank_charges):
		charge_row = je_row(doc.company, require_account(acc.get("bank_charges_account"), "LC / Bank Charges Account",
															  doc.company), debit=doc.bank_charges,
							 remark=f"Retirement charges LC {doc.lc_no}")
		charge_row["nsa_lc_charge_head"] = "Retirement Charges"
		rows.append(charge_row)
	if flt(doc.margin_adjusted):
		rows.append(je_row(doc.company, require_account(acc.get("lc_margin_account"), "LC Margin Account", doc.company),
						   credit=doc.margin_adjusted, remark=f"Margin adjusted LC {doc.lc_no}"))
	je = build_journal_entry(doc.company, doc.posting_date, rows, paid_from,
							 f"LC {doc.lc_no} retirement ({doc.name})", doc.lc_no,
							 letter_of_credit=doc.letter_of_credit)
	doc.db_set("journal_entry", je.name)
	return je.name
