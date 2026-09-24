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
| 3 | Shipping Document (PO items, packing list, charges, Bill of Lading, original documents tracking) | Letter of Credit |
| 3a | Shipping Insurance (policy, insured amount, premium, balance, item allocation) | Shipping Document |
| 4 | Customs Clearance / GD (AV = CIF × (1 + landing %), CD, ACD, RD, ST, AST, IT) | Shipping Document |
| 5 | Purchase Receipt / GRN | Shipment or Customs Clearance |
| 6 | Import Cost Sheet (actual freight, insurance, duties, clearing, port, other) | Purchase Receipt / Shipment |
| 7 | Landed Cost Voucher | Import Cost Sheet |
| 8 | Purchase Invoice | Purchase Receipt (standard) |
| 9 | LC Retirement (document retirement, bank payment, margin adjustment) | LC / Shipment |

Accounting Journal Entries (LC margin & charges, duty payment, LC retirement) are created as **Draft**
from buttons on each document so accounts can review before submitting.

Purchase Type and LC / Shipment / GD references are carried to Purchase Receipt, Purchase Invoice and
Landed Cost Voucher and are available in all reports.

## Letter of Credit

A separate submittable document, always linked to one **Import** Purchase Order.

Create it from the Import PO: *Connections → Letter of Credit → +* or *Import → Letter of Credit*. For Local POs the
LC link is hidden in Connections and the server blocks creation and linking. By default the PO must be submitted
(NSA Import Settings → *Allow LC against Draft Purchase Order* relaxes this for creation; the LC itself can only be
submitted after the PO is submitted).

Tabs and fields:

- **Details**: Purchase Order, Supplier / Supplier Name, LC Number, LC Date, LC Payment Term, LC Type;
  PO Qty, PO Amount, Currency (read-only, always taken from the PO), LC Tolerance %, LC Amount, Exchange Rate;
  *Banking*: LC Bank, LC Bank Account (fills Bank GL Account), advising / confirming bank;
  *Insurance*: Insurance Company, Cover Note No., Insurance Limit, Insurance Expiry Date;
  *Shipment / FI*: LC Expiry Date, Plan To Move, Place, FI No., FI Validity, Latest Date of Shipment;
  *Additional LC Terms* (collapsed): ports, Incoterm, partial shipment / transhipment, documents required.
- **Charges**: LC Commission %, LC Commission Amount, LC AFTER, FED %, SWIFT Charges, Amendment Commission,
  SWIFT Charges Amended, LC Tolerance, FED on Commission, Total LC Charges; Other Bank Charges table; Margin.
- **Amendments & Utilization**: amendments (amount change, new expiry / shipment dates), shipped, retired, balance.
- **Expense Booked**: Charge Head, Expense Account, Amount, Posting Date, Reference Voucher (Dynamic Link), Remarks;
  Total Expense Booked and LC Charges Not Yet Booked.

Calculations (charges in company currency):

| Field | Formula |
|---|---|
| PO Qty / PO Amount / Currency | PO Total Qty / PO Grand Total / PO Currency |
| LC Tolerance | PO Amount × LC Tolerance % ÷ 100 |
| Max LC Amount | (LC Amount + amendments) × (1 + Tolerance % ÷ 100) |
| LC Commission Amount | Commission base × Exchange Rate × Commission % ÷ 100 (base per Settings: LC Amount, PO Amount, or LC Amount incl. Tolerance) |
| FED on Commission | (Commission + Amendment Commission\*) × FED % ÷ 100 (\*Settings switch) |
| Total LC Charges | Commission + FED + LC AFTER\* + SWIFT + Amendment Commission + SWIFT Amended (\*Settings switch) |
| Total Bank Charges | Total LC Charges + Other Bank Charges table (used by Import Cost Sheet) |

Default Commission % and FED % (16) come from NSA Import Settings, so rate changes need no code change.

Validations: PO mandatory, set once and never changed; only Import POs; LC Number unique across non-cancelled LCs
(switchable); percentages 0–100; amounts not negative; LC Expiry ≥ LC Date; Latest Date of Shipment between LC Date
and LC Expiry; warnings when Plan To Move is after the latest shipment date, or FI validity / insurance expires
before it. Closed or Expired LCs can only be edited by the role set in Settings (default Accounts Manager).

Expense booking: *Create → Book LC Charges (Journal Entry)* makes a draft JE for the margin (first time) and every
charge head not yet booked. Each line is tagged with its charge head, and the JE carries the LC link. When the JE is
submitted, its lines are copied to the **Expense Booked** tab automatically; cancelling the JE removes them. Any
manual JE can be linked the same way by selecting the Letter of Credit on it. Rows for other vouchers
(Payment Entry, Purchase Invoice) can be added by hand.

## Shipping Document

Replaces the earlier "Import Shipment" (existing records are renamed automatically by a migration patch).
Created from a submitted **Letter of Credit** → *Create → Shipping Document* (or PO → *Import → Shipping Document*,
which opens it through the PO's LC). The LC must have its bank LC Number. Creating one without an LC is blocked
unless *Allow Shipping Document without Letter of Credit* is ticked in NSA Import Settings (for TT / open-account imports).

Tabs:

- **Details**: Letter of Credit, Purchase Order, Supplier Name, LC No. (all fetched, read-only), Commercial Invoice
  No., Conversion Rate; Shipped Qty, S/QTY Amount, S/QTY Amount (PKR), PO Qty / Amount, Remaining Qty;
  **PO Items** table (only from the PO via *Get Items from Purchase Order*; rows cannot be added by hand);
  Original Documents Tracking (DOC Received in Bank, Sent to Agent, Received in ATS, Paid, DHL No., Arrival Notes
  Created — all editable after submit).
- **Packing List**: Packing, QTY, Number of Packages, Package Description, Net / Gross Weight, Weight UOM, Remarks;
  Container / Shipment Tracking table (container, size, seal, packages, package type, weight, remarks).
- **Charges**: Commission %, Commission, FED %, FED on Commission, SWIFT Charges, Total Charges, Remarks.
  PO Amount, Currency and Conversion Rate are not repeated here.
- **Bill of Lading**: B/L No., B/L Date, B/L Type, Shipping Line, Vessel, Voyage, ports, Final Destination, ETD, ETA,
  actual departure / arrival, Notify Party, B/L Remarks; Insurance; Documents Checklist.

PO Item columns: Item Code, Item Name, Qty (PO), Shipped Qty UOM, Rate, Amount (PO), Shipped Qty, Shipped Amount,
Origin, HS Code, Warehouse; Quantity Tracking: PO UOM, UOM factor, Shipped Qty (PO UOM), Previously Shipped,
Remaining Qty.

| Field | Formula |
|---|---|
| Shipped Qty (PO UOM) | Shipped Qty × Shipped-UOM-to-PO-UOM factor (1 when same UOM; from Item UOM conversions otherwise) |
| Shipped Amount | Shipped Qty (PO UOM) × PO Rate |
| Remaining Qty | PO Qty − previously shipped (submitted docs) − this document |
| Header Shipped Qty | Σ item Shipped Qty |
| S/QTY Amount | Σ item Shipped Amount (foreign currency) |
| S/QTY Amount (PKR) | S/QTY Amount × Conversion Rate |
| Commission | S/QTY Amount (PKR) × Commission % ÷ 100 |
| FED on Commission | Commission × FED % ÷ 100 |
| Total Charges | Commission + FED + SWIFT |

Controls: shipped qty cannot exceed the open PO quantity (+ over-shipment tolerance % from Settings); S/QTY Amount
cannot exceed the LC balance (incl. tolerance and amendments); partial shipments are supported and PO
*Shipped %* is updated on submit / cancel. Before submit these must be filled: Commercial Invoice No., B/L No.,
B/L Date, Packing, QTY, Net Weight, Weight UOM. Rows with zero Shipped Qty are dropped on submit.

*Create → Book Charges (Journal Entry)* makes a draft JE for Commission, FED and SWIFT, credited to the LC's Bank GL
Account; on submit these lines appear in the LC's Expense Booked tab (heads "Shipment ..."). Shipment charges are
also picked up by the Import Cost Sheet (pro-rata to the received value). Receiving warehouse on the GRN comes
from the Shipping Document row.

## Shipping Insurance

Created from a submitted Shipping Document → *Create → Shipping Insurance*. PO, Letter of Credit, LC No., Supplier,
Bank, Invoice Value in FC and items come from the Shipping Document and are read-only; vessel, BL/AWB, ETA and ports
are pre-filled from its Bill of Lading tab. Insurance Company, Policy Number, Insurance Total Policy and Policy
Expiry default from the LC's Insurance section.

| Field | Formula / rule |
|---|---|
| Insurance Amount (default) | Invoice Value × (1 + Insured Value Markup %) — Settings, default 10% |
| Premium Amount | Insurance Amount × Premium Rate % ÷ 100 |
| PKR amounts | amount × Exchange Rate |
| Utilized by Other Shipments | Σ Insurance Amount of other submitted Shipping Insurance on the same policy |
| Balance Insurance | Insurance Total Policy − Utilized by others − this Insurance Amount (system calculated) |
| Item Insurance Amount | auto-allocated by item Amount (button to re-allocate); must add up to Insurance Amount |

A policy is identified by its Policy Number; until the number is known, by Letter of Credit + Insurance Company.
Insurance Amount cannot exceed the balance unless *Allow Insurance Amount above Balance* is ticked by the role
set in Settings (default Accounts Manager). Policy Number, dates, ETA, Release Date and Remarks can be entered
after submit; all changes are kept in the document's version history.

Status: Draft → Submitted (no policy number yet) → Policy Issued (policy number, balance left, only shipment on
the policy) → Partially Utilized (more shipments on the policy) → Fully Utilized (no balance) / Cancelled. Statuses
and balances of every document on a policy are refreshed whenever one of them is submitted, changed or cancelled.

The *Related Import Documents* section shows the LC, Shipping Document (with its Packing List and Bill of Lading
tabs), Goods Declaration, Purchase Receipt and Import Cost Sheet. Freight Bill, Clearance Bill, Shipment Check And
Delays and Local Transporter show "Not set up yet" until those documents exist; they are picked up automatically
once they have a Shipping Document link. The Import Cost Sheet uses the actual insurance premium (PKR) instead
of the PO estimate.

Reports: **Insurance Tracking** (filter by LC, PO, supplier, shipping document or policy; tick *Show Items* for
item-wise allocation) and **Insurance Balance** (policy total, utilized, balance per policy).

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
