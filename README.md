# NSA Import

Frappe / ERPNext (v15 & v16) custom app for Local & Import purchasing with a complete import flow:
Purchase Order → Letter of Credit → Shipping Documents → Customs Clearance (GD) → GRN → Landed Cost → Purchase Invoice → LC Retirement.

The app extends ERPNext's standard **Purchase Order** (it does not replace it), so all standard features
(totals, taxes, rounding, payment schedule, connections, auto repeat, printing, workflows) keep working.

## Installation

```bash
cd ~/frappe-bench
bench get-app /path/to/nsa_import        # or: bench get-app <git-url>
bench --site your-site install-app nsa_import
bench --site your-site migrate
bench build --app nsa_import
bench restart
```

Custom fields are created on install and re-synced on every `migrate`. Uninstalling removes them.

## Setup (one time)

1. **NSA Import Settings** → add a row per company in *Company Accounts*:
   - LC Margin Account (asset), LC / Bank Charges Account (expense)
   - Customs Duty, Freight & Insurance, Clearing / Port Charges, Other Import Expense accounts —
     use **"Expenses Included In Valuation"** type accounts so the Landed Cost Voucher credit
     nets off the Journal Entry debit.
   - Input Sales Tax and Advance Income Tax accounts (these are *not* capitalised in item cost).
2. Settings also hold: HS Code mandatory for import items, shipment qty tolerance %, default LCV
   distribution (Qty / Amount), landing charges % (default 1% for Assessable Value) and whether
   sales tax is included in landed cost.
3. **Customs Tariff Number** (HS Code master) → fill CD / ACD / RD / ST / AST / IT %. Items that
   have a Customs Tariff Number auto-fetch the HS Code and duty rates.
4. Naming series: Local PO = `LPO-.YYYY.-`, Import PO = `IPO-.YYYY.-` (switched automatically).

## Flow

| Step | Document | Created from |
|---|---|---|
| 1 | Purchase Order (Purchase Type = Import) | Manual / Material Request / Supplier Quotation |
| 2 | Letter of Credit (opening, margin, charges, amendments) | PO → *Import → Letter of Credit* |
| 3 | Import Shipment (B/L / AWB, invoice, packing list, containers, shipping documents checklist) | PO or LC |
| 4 | Customs Clearance / GD (AV = CIF × (1 + landing %), CD, ACD, RD, ST, AST, IT) | Import Shipment |
| 5 | Purchase Receipt / GRN | Shipment or Customs Clearance |
| 6 | Import Cost Sheet (actual freight, insurance, duties, clearing, port, other) | Purchase Receipt / Shipment |
| 7 | Landed Cost Voucher | Import Cost Sheet |
| 8 | Purchase Invoice | Purchase Receipt (standard) |
| 9 | LC Retirement (document retirement, bank payment, margin adjustment) | LC / Shipment |

Accounting Journal Entries (LC margin & charges, duty payment, LC retirement) are created as **Draft**
from buttons on each document so accounts can review before submitting.

Purchase Type and LC / Shipment / GD references are carried to Purchase Receipt, Purchase Invoice and
Landed Cost Voucher and are available in all reports.

## Dynamic rules on Purchase Order

- **Local**: Voucher Number visible; all import sections/fields hidden and not mandatory.
- **Import**: Mode of Shipment, PI No., PI Date, Shipping Term, Payment Term mandatory; Import Details tab,
  item HS Code / Country of Origin / weights / item-wise freight & insurance / import rate shown.
- **LC No. / LC Date** mandatory only when Payment Term is *LC at Sight* or *LC Usance*. If the LC is
  opened later from the PO, the Letter of Credit document fills these fields back into the PO.
- **HS Code** mandatory on import items (can be switched off in Settings).
- **Exchange Rate** mandatory when currency ≠ company currency.
- Estimated landed cost (freight, insurance, duty, taxes, clearing, port, other) is calculated on the PO;
  actual cost goes through Import Cost Sheet → Landed Cost Voucher.

## Reports

- **Import Tracker** – PO-wise status: LC, shipment, GD, GRN, invoice, landed cost.
- **LC Register** – LCs by bank/status with utilised, balance and expiry.
- **Purchase Type Summary** – Local vs Import purchasing totals by supplier / month.

A daily scheduler marks LCs past expiry date as *Expired*.

## Spec checklist mapping

| Checklist item | Implementation |
|---|---|
| Parent PO doctype | Standard ERPNext Purchase Order, extended |
| Purchase Type Local / Import | Custom field `purchase_type` (Select, mandatory) |
| Details / Address & Contact / Terms / More Info / Connections tabs | Standard tabs + custom fields (Voucher No, Department, NTN/STRN, Country, Payment Days, Payment Method, Notes) |
| Items + Edit Row | Standard PO Item + Remarks, Final Cost, import section |
| Import fields with dynamic visibility | `depends_on` / `mandatory_depends_on` + client script |
| HS Code / weight fields | PO Item custom fields, Weight UOM shown in grid |
| Currency, totals, taxes, rounding | Standard ERPNext calculation |
| Downstream links | PR / PI / LCV fields + LC, Shipment, GD connections on dashboard |
| Landed cost integration | Import Cost Sheet → Landed Cost Voucher |

## License

MIT
