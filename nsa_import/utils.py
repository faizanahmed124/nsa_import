import frappe
from frappe import _
from frappe.utils import flt


def get_settings():
	return frappe.get_cached_doc("NSA Import Settings")


def get_company_accounts(company):
	for row in get_settings().get("company_accounts") or []:
		if row.company == company:
			return row
	return frappe._dict()


def get_company_currency(company):
	return frappe.get_cached_value("Company", company, "default_currency")


def require_account(account, label, company):
	if not account:
		frappe.throw(
			_("Please set <b>{0}</b> for company {1} in NSA Import Settings.").format(_(label), company)
		)
	return account


def is_lc_payment_term(term):
	return (term or "").strip().upper().startswith("LC")


# ----------------------------------------------------------------------------
# Purchase Order tracking
# ----------------------------------------------------------------------------
def update_po_shipped_qty(purchase_order):
	if not purchase_order:
		return
	rows = frappe.get_all("Purchase Order Item", filters={"parent": purchase_order}, fields=["name", "qty"])
	shipped = dict(
		frappe.db.sql(
			"""select i.po_detail, sum(i.qty) from `tabImport Shipment Item` i
			join `tabImport Shipment` s on s.name = i.parent
			where s.docstatus = 1 and s.purchase_order = %s group by i.po_detail""",
			purchase_order,
		)
	)
	total_qty = total_shipped = 0.0
	for r in rows:
		sq = flt(shipped.get(r.name))
		frappe.db.set_value("Purchase Order Item", r.name, "shipped_qty", sq, update_modified=False)
		total_qty += flt(r.qty)
		total_shipped += min(sq, flt(r.qty))
	per = flt(total_shipped / total_qty * 100, 2) if total_qty else 0
	frappe.db.set_value("Purchase Order", purchase_order, "per_shipped", per, update_modified=False)


def refresh_po_import_status(purchase_order):
	if not purchase_order or not frappe.db.exists("Purchase Order", purchase_order):
		return
	po = frappe.db.get_value("Purchase Order", purchase_order, ["per_received", "purchase_type"], as_dict=True)
	if po.purchase_type != "Import":
		return
	status = ""
	if flt(po.per_received) >= 100:
		status = "Received"
	elif flt(po.per_received) > 0:
		status = "Partially Received"
	elif frappe.db.exists("Customs Clearance", {"purchase_order": purchase_order, "docstatus": 1}):
		status = "Cleared"
	elif frappe.db.exists(
		"Import Shipment", {"purchase_order": purchase_order, "docstatus": 1, "actual_arrival_date": ["is", "set"]}
	):
		status = "Arrived"
	elif frappe.db.exists("Import Shipment", {"purchase_order": purchase_order, "docstatus": 1}):
		status = "Shipped"
	elif frappe.db.exists("Letter of Credit", {"purchase_order": purchase_order, "docstatus": 1}):
		status = "LC Opened"
	frappe.db.set_value("Purchase Order", purchase_order, "import_status", status, update_modified=False)


# ----------------------------------------------------------------------------
# Journal Entry builder (always created as DRAFT for review)
# ----------------------------------------------------------------------------
def je_row(company, account, debit=0.0, credit=0.0, party_type=None, party=None,
		   exchange_rate=None, amount_in_account_currency=None, remark=None):
	company_currency = get_company_currency(company)
	account_currency = frappe.get_cached_value("Account", account, "account_currency") or company_currency
	amount = flt(debit) or flt(credit)
	row = {
		"account": account,
		"party_type": party_type,
		"party": party,
		"user_remark": remark,
		"cost_center": frappe.get_cached_value("Company", company, "cost_center"),
	}
	if account_currency != company_currency:
		rate = flt(exchange_rate) or 1
		acc_amount = flt(amount_in_account_currency) if amount_in_account_currency else flt(amount / rate, 2)
		row.update({"account_currency": account_currency, "exchange_rate": rate})
	else:
		rate, acc_amount = 1, amount
		row.update({"exchange_rate": 1})
	row["debit_in_account_currency"] = acc_amount if flt(debit) else 0
	row["credit_in_account_currency"] = acc_amount if flt(credit) else 0
	row["_base"] = flt(acc_amount * rate, 2)
	return row


def build_journal_entry(company, posting_date, rows, balancing_account, remark, reference=None,
						letter_of_credit=None):
	je = frappe.new_doc("Journal Entry")
	if letter_of_credit:
		je.letter_of_credit = letter_of_credit
	je.voucher_type = "Journal Entry"
	je.company = company
	je.posting_date = posting_date
	je.user_remark = remark
	if reference:
		je.cheque_no = reference
		je.cheque_date = posting_date
	debit = credit = 0.0
	for r in rows:
		base = r.pop("_base")
		if flt(r.get("debit_in_account_currency")):
			debit += base
		else:
			credit += base
		je.append("accounts", r)
	diff = flt(debit - credit, 2)
	if diff:
		bal = je_row(company, balancing_account, credit=diff if diff > 0 else 0, debit=-diff if diff < 0 else 0,
					 remark=remark)
		bal.pop("_base")
		je.append("accounts", bal)
	je.insert()
	return je
