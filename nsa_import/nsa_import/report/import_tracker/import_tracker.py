import frappe
from frappe import _


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def col(label, fieldname, fieldtype="Data", options=None, width=120):
	return {"label": _(label), "fieldname": fieldname, "fieldtype": fieldtype, "options": options, "width": width}


def get_columns():
	return [
		col("Purchase Order", "purchase_order", "Link", "Purchase Order", 150),
		col("Date", "transaction_date", "Date", width=95),
		col("Supplier", "supplier", "Link", "Supplier", 160),
		col("PI No.", "pi_no", width=110),
		col("Payment Term", "import_payment_term", width=130),
		col("Currency", "currency", "Link", "Currency", 70),
		col("PO Amount", "grand_total", "Currency", "currency", 120),
		col("Letter of Credit", "letter_of_credit", "Link", "Letter of Credit", 140),
		col("LC No.", "lc_no", width=110),
		col("LC Status", "lc_status", width=110),
		col("LC Expiry", "lc_expiry", "Date", width=95),
		col("Shipments", "shipments", width=160),
		col("B/L / AWB", "bl_awb", width=150),
		col("ETA", "eta", "Date", width=95),
		col("GD No.", "gd_no", width=130),
		col("% Shipped", "per_shipped", "Percent", width=90),
		col("% Received", "per_received", "Percent", width=90),
		col("% Billed", "per_billed", "Percent", width=90),
		col("Import Status", "import_status", width=130),
	]


def get_data(filters):
	conditions = {"docstatus": 1, "purchase_type": "Import"}
	if filters.company:
		conditions["company"] = filters.company
	if filters.supplier:
		conditions["supplier"] = filters.supplier
	if filters.purchase_order:
		conditions["name"] = filters.purchase_order
	elif filters.from_date and filters.to_date:
		conditions["transaction_date"] = ["between", [filters.from_date, filters.to_date]]

	pos = frappe.get_all(
		"Purchase Order", filters=conditions,
		fields=["name", "transaction_date", "supplier", "pi_no", "import_payment_term", "currency", "grand_total",
				"per_shipped", "per_received", "per_billed", "import_status"],
		order_by="transaction_date desc",
	)
	data = []
	for po in pos:
		status = po.import_status or "Not Started"
		if filters.import_status and filters.import_status != status:
			continue
		lc = frappe.db.get_value("Letter of Credit", {"purchase_order": po.name, "docstatus": 1},
								 ["name", "lc_no", "status", "expiry_date"], as_dict=True) or frappe._dict()
		shipments = frappe.get_all("Import Shipment", filters={"purchase_order": po.name, "docstatus": 1},
								   fields=["name", "bl_awb_no", "eta"], order_by="posting_date asc")
		gds = frappe.get_all("Customs Clearance", filters={"purchase_order": po.name, "docstatus": 1}, pluck="gd_no")
		data.append({
			"purchase_order": po.name, "transaction_date": po.transaction_date, "supplier": po.supplier,
			"pi_no": po.pi_no, "import_payment_term": po.import_payment_term, "currency": po.currency,
			"grand_total": po.grand_total, "letter_of_credit": lc.get("name"), "lc_no": lc.get("lc_no"),
			"lc_status": lc.get("status"), "lc_expiry": lc.get("expiry_date"),
			"shipments": ", ".join(s.name for s in shipments),
			"bl_awb": ", ".join(s.bl_awb_no for s in shipments if s.bl_awb_no),
			"eta": shipments[-1].eta if shipments else None, "gd_no": ", ".join(g for g in gds if g),
			"per_shipped": po.per_shipped, "per_received": po.per_received, "per_billed": po.per_billed,
			"import_status": status,
		})
	return data
