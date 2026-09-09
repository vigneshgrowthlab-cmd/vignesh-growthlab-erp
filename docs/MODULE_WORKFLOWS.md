# Wholesale ERP — Module Workflows

High-level workflow diagrams for each functional module, grounded in the actual
service/endpoint code (not generic templates). Diagrams use [Mermaid](https://mermaid.js.org/)
and render automatically on GitHub and in VS Code (Markdown preview / Mermaid extension).

**Stack:** FastAPI + MariaDB backend, React 18 (Vite) frontend. Indian GST context throughout
(GSTIN, state codes, HSN, INR, April-start FY).

---

## How the modules interconnect

The transactional modules feed two shared backbones — **FIFO stock** (`StockEntry` /
`WarehouseStock`) and **double-entry accounting** (`journal_entries` / `journal_lines`) — which
the GST, Banking, and Reports modules then read.

```mermaid
flowchart LR
    SET[Settings<br/>prefixes, sequences, GSTIN] --> PUR
    SET --> BIL
    SEC[Security / Auth<br/>JWT, page permissions] --> ALL[All modules]
    PROD[Products & Inventory<br/>FIFO StockEntry] --> PUR[Purchase]
    PUR -->|stock-in layer + cost| PROD
    PUR -->|journal + vendor ledger| ACC[Accounting]
    PROD --> WH[Warehouse<br/>transfer / adjust / writeoff]
    WH -->|movements + loss journal| ACC
    PROD -->|FIFO consume + COGS| BIL[Billing & Sales]
    BIL -->|journal + customer ledger| ACC
    BIL -->|invoice| GST[GST / E-Invoice / E-Way]
    GST -->|IRN / QR / Ack| BIL
    ACC --> REP[Reports & Dashboard]
    BIL --> REP
    PUR --> REP
    PROD --> REP
    ACC --> BANK[Banking<br/>stock statement + recon]
    BIL --> BANK
```

---

## 1. Security, Users & Auth

**What it does:** JWT login with account-lockout after repeated failures, issues access +
refresh tokens, registers an active session and login history. Admins manage the user lifecycle
(create / update / reset-password / suspend / unlock / force-logout) behind super-admin role
gates; every privileged action writes to the activity log, and a suspicious-activity scan flags
repeated failed logins and bulk exports.

```mermaid
flowchart TD
    A[User submits username and password] --> B{Account locked?}
    B -->|Yes and window active| C[Reject with lockout message]
    B -->|No or expired| D{Password valid?}
    D -->|No| E[Increment failed count and lock at threshold]
    D -->|Yes| F[Reset failed count and issue access plus refresh tokens]
    F --> G[Register ActiveSession and record LoginHistory]
    G --> H[Authenticated requests via get_current_user]
    H --> I{Admin action?}
    I -->|Create or update user| J[UserService enforces super_admin role gate]
    I -->|Reset password or suspend or force logout| K[Clear refresh token and delete ActiveSession]
    K --> L[Record logout in LoginHistory]
    J --> M[Write ActivityLog audit entry]
    L --> M
    M --> N[Admin views sessions login history and suspicious scan]
    H --> O[Refresh token rotates new access token]
    H --> P[Logout clears session and 2FA OTP verify issues tokens]
```

**Triggers / feeds:** Self-contained auth/audit module — no stock, journal, or GST side effects.
Feeds `page_permissions` and `warehouse_id` consumed by every other module for access control;
`ActivityLog` records exports flagged from Reports.

---

## 2. Settings

**What it does:** Admin-managed configuration hub. Stores a single `CompanySettings` record
(identity, GSTIN/state, address, bank/UPI, invoice prefixes, e-way threshold, bank-stock margin,
FY start), lets admins edit invoice numbering sequences, upload a logo, and manage per-user
page-level permissions. Exposes read-only GST-rate and Indian-state master lists. Reads are open
to any authenticated user; all writes require admin.

```mermaid
flowchart TD
    A[Authenticated User] --> B{Admin?}
    A --> C[Read Company Settings]
    A --> D[Read Invoice Sequences]
    A --> E[Read GST Rates Master]
    A --> F[Read Indian States Master]
    B -->|Yes| G[Update Company Settings]
    B -->|Yes| H[Update Invoice Sequence]
    B -->|Yes| I[Upload Company Logo]
    B -->|Yes| J[Manage User Page Permissions]
    G --> K[CompanySettings Row Upsert]
    H --> L[InvoiceSequence prefix and last number]
    I --> M[Save file to uploads logos]
    M --> K
    J --> N[User page_permissions JSON or NULL]
    K --> O[Stamps prefixes thresholds bank FY]
    L --> P[Feeds document numbering across modules]
    N --> Q[Drives frontend page access control]
```

**Triggers / feeds:** Config provider — no stock/journal/GST calls. Invoice prefixes and
sequences feed document numbering in Billing/Purchase/GST; `eway_threshold`/`state_code`/GSTIN
feed GST and E-Way logic; `bank_stock_margin` feeds bank stock valuation; per-user
`page_permissions` drive Security/UI access control.

---

## 3. Products & Inventory

**What it does:** Manages category and product master data (HSN/GST setup, category-prefixed part
codes), enforces a `floor ≤ b2b ≤ b2c ≤ mrp` price ordering with a cost-floor guard, and runs a
versioned multi-type price-history engine supporting immediate or future-scheduled prices,
below-cost/low-margin alerts, and bulk updates. Stock is tracked through FIFO `StockEntry` layers
whose `remaining_qty` is consumed in batch-date order alongside a `WarehouseStock` running total —
feeding ageing, cost-trend, and FIFO-vs-latest valuation reports.

```mermaid
flowchart TD
    A[Admin manages Category prefix HSN GST] --> B[Create Product with HSN GST and price tiers]
    B --> Q{Price order valid floor le b2b le c2c le mrp and floor ge cost}
    Q -->|No| R[Reject 400 ordering error]
    Q -->|Yes| C[Generate part code from category counter]
    C --> D[Record initial cost history]
    B2[Edit or Bulk price update] --> E[Price History engine versioned product_prices]
    E --> Q2{Effective date in future}
    Q2 -->|Yes| F[Store scheduled inactive row]
    Q2 -->|No| G[Activate update product column and fire below-cost low-margin alerts]
    F --> H[activate_scheduled_prices on read or purchase]
    H --> G
    I[Stock In purchase adjustment opening] --> J[add_stock creates FIFO layer and bumps WarehouseStock]
    K[Stock Out sale adjustment] --> L[consume_fifo by batch date reduces remaining_qty and WarehouseStock]
    J --> M[Ageing and Stock Valuation FIFO vs latest cost]
    L --> M
    D --> N[Cost Trend and Margin reports per vendor]
```

**Triggers / feeds:** Purchase calls `add_stock`/`record_cost` to create FIFO layers and triggers
price activation; Billing/Warehouse call `consume_fifo` (returns weighted-avg cost feeding COGS
journal postings); HSN/`gst_percent` feed Billing and GST e-invoice. No GST API or journal
postings originate here.

---

## 4. Purchase

**What it does:** Manages vendors and inbound purchase bills. A vendor is created/looked-up
(GSTIN auto-derives state code), then a bill is recorded against a vendor + warehouse: each line
computes GST (CGST/SGST intra-state vs IGST inter-state), creates a FIFO `StockEntry` layer,
updates product cost and vendor-product pricing, and the whole bill posts a double-entry journal
plus a vendor-ledger credit. Vendor payments debit the ledger, post a CREDITORS/Cash-Bank
journal, and recompute cached paid/outstanding (specific payments first, then advances applied
FIFO). Cancellations and voids fully reverse stock, journal, and ledger — and are **blocked** if
stock was consumed or payments applied.

```mermaid
flowchart TD
    A[Create or Lookup Vendor] --> B[Derive State Code from GSTIN]
    B --> C[Create Purchase Bill]
    C --> Q{Duplicate Vendor Invoice?}
    Q -->|Yes| R[Reject 409]
    Q -->|No| D[Determine GST Type Intra or Inter State]
    D --> E[Per Line Compute Taxable and GST]
    E --> F[Add FIFO StockEntry Layer]
    F --> G[Update Product Cost and Reprice Tiers]
    G --> H[Post Vendor Ledger Credit]
    H --> I[Post Journal Stock and GST ITC Debit Creditors Credit]
    I --> J[Recompute Paid and Outstanding]
    J --> K[Record Vendor Payment]
    K --> L[Ledger Debit and Journal Creditors vs Cash Bank]
    L --> M[Apply Payments and Advances FIFO]
    C --> N[Cancel or Void Reverses Stock Journal Ledger]
```

**Triggers / feeds:** Writes FIFO `StockEntry`/`WarehouseStock` consumed by Billing/Inventory;
posts `JournalEntry`/`JournalLine` (STOCK, GST_ITC, CREDITORS, CASH/BANK) to Accounting; updates
`Product.purchase_cost` and `ProductCostHistory` feeding Products/Reports; calls Cleartax GSTIN
lookup for vendor onboarding.

---

## 5. Warehouse

**What it does:** Manages warehouses and their stock movements. Users create/obsolete/delete
warehouses (guarded by reference checks), then run four stock operations: **DC-linked transfers**
(deduct source on create, add destination on DC confirm, restore source on reject), **adjustments**
(in/out via FIFO), **write-offs** (pending → approved, consuming FIFO and posting a loss journal),
and **opening stock** (seeds `StockEntry` plus ledger/account openings). Each operation drives
`WarehouseStock` and `StockEntry`; write-offs and openings also touch the accounting ledger.

```mermaid
flowchart TD
    A[Warehouse Module] --> B[Manage Warehouse]
    A --> C[Stock Transfer]
    A --> D[Stock Adjustment]
    A --> E[Stock Write-off]
    A --> F[Opening Stock]
    B --> B1{Has references?}
    B1 -->|No| B2[Hard Delete]
    B1 -->|Yes| B3[Obsolete soft-delete]
    C --> C1[Create transfer linked to DCs]
    C1 --> C2[Deduct source WarehouseStock]
    C2 --> C3{Destination decision}
    C3 -->|Confirm DC| C4[Add destination WarehouseStock mark delivered]
    C3 -->|Reject DC| C5[Restore source stock mark rejected]
    D --> D1{Adjustment type}
    D1 -->|In| D2[Add StockEntry FIFO layer]
    D1 -->|Out| D3[Consume FIFO]
    E --> E1[Create pending write-off]
    E1 --> E2{Approve?}
    E2 -->|Yes| E3[Consume FIFO and post loss journal]
    E2 -->|No| E4[Reject]
    F --> F1[Seed StockEntry plus ledger openings]
```

**Triggers / feeds:** Reads Delivery Challans/Invoices from Billing to drive transfers; consumes
Product FIFO via `StockService`; write-off approval and opening balances post to Accounting
`journal_entries`/`journal_lines`, customer/vendor `LedgerEntry`, and Account opening balances.
No GST/E-Invoice calls.

---

## 6. Billing & Sales

**What it does:** Manages customers (credit limits, GSTIN lookup, addresses, running
ledger/outstanding) and creates sales documents (B2B/B2C invoices, quotations, delivery challans,
credit notes). On invoice creation it validates stock and credit limit, determines GST type from
warehouse vs shipping state, consumes stock FIFO to capture COGS cost, posts a customer ledger
debit and a double-entry journal (DR Debtors, CR Sales, CR GST Payable), then records receipts
that pay invoices oldest-first (FIFO) with a CASH/BANK debit and Debtors credit.

```mermaid
flowchart TD
    A[Manage Customer with GSTIN credit limit addresses] --> B[Create Sales Document]
    B --> C{Document type?}
    C -->|Quotation| D[Save quotation no stock no accounting]
    C -->|Delivery Challan| E[Save DC validate stock only no FIFO no accounting]
    C -->|B2B or B2C Invoice| F[Validate addresses stock and credit limit]
    D -->|Convert| F
    F --> G[Determine GST type from warehouse vs shipping state]
    G --> H[Consume FIFO stock capture COGS cost per line]
    H --> I[Compute taxable CGST SGST IGST and total]
    I --> J[Post customer ledger debit and update outstanding]
    J --> K[Post journal DR Debtors CR Sales CR GST Payable]
    K --> L[Record Receipt]
    L --> M[Apply payment FIFO oldest invoices first]
    M --> N[Post receipt journal DR Cash or Bank CR Debtors]
    F -->|Return goods| O[Create Credit Note reverse GST add stock back credit ledger]
```

**Triggers / feeds:** Writes/consumes `StockEntry` FIFO layers via `StockService` for stock
movement and COGS cost; posts `journal_entries`/`journal_lines` against the chart of accounts;
produces CGST/SGST/IGST output liability and invoice records feeding GST/E-Invoice and Reports;
receipts touch CASH/BANK (Banking).

---

## 7. Accounting

**What it does:** Double-entry bookkeeping and treasury: a cheque register with
received→deposited→cleared/bounced lifecycle (bounce reverses the customer ledger), daily cash
closing reconciled from cash receipts minus approved cash expenses, expense capture with
threshold-based admin approval (posts DR Expenses / CR Cash-or-Bank), TDS recording and Form 26AS
reconciliation, customer receivables ageing with collection-priority scoring, vendor payment-due
alerts, and read-only journal listing plus trial balance against the chart of accounts.

```mermaid
flowchart TD
    A[Accountant or Admin] --> B{Action?}
    B --> C[Record Cheque received]
    C --> D[Deposit then Clear or Bounce]
    D --> E{Bounced?}
    E -->|Yes| F[Reverse Customer LedgerEntry debit]
    B --> G[Create Expense]
    G --> H{Amount over threshold?}
    H -->|Yes| I[Pending Admin Approval]
    H -->|No| J[Auto approved]
    I --> J
    J --> K[Post JournalEntry debit EXPENSES credit CASH or BANK]
    B --> L[Cash Closing today]
    L --> M[Opening plus cash Receipts minus approved cash Expenses then Approve]
    B --> N[Record TDS or Import Form 26AS reconcile]
    B --> O[View Customer Ageing buckets and priority]
    B --> P[View Journal list and Trial Balance]
    K --> P
```

**Triggers / feeds:** Reads `CustomerPayment` receipts and invoice outstanding from Billing (cash
closing, ageing, ledger reversal) and `payment_due_date` from Purchase (vendor due alerts); writes
`JournalEntry`/`JournalLine` and Account postings consumed by Reports' trial balance; writes
reversing `LedgerEntry` rows back to the customer ledger on cheque bounce.

---

## 8. GST / E-Invoice / E-Way Bill

**What it does:** Integrates with Cleartax for statutory compliance. **E-Invoice:** generates an
IRN + signed QR + acknowledgement for a sales invoice — calling the real API with retries, or
returning a deterministic mock when `CLEARTAX_SANDBOX` is on and no auth token is set — then
persists IRN/QR/Ack on the invoice; cancellation is allowed only within 24 hours. **E-Way Bill:**
generated against an invoice with transporter/vehicle/distance. **Returns:** GSTR-1 is built from
outward invoices for a period, GSTR-2B reconciles imported supplier data against recorded
purchases, and GSTR-3B produces the summary. Transporter and vehicle masters support e-way logistics.

```mermaid
flowchart TD
    A[GST Module] --> B[Manage Transporter and Vehicle masters]
    A --> C[Generate E-Invoice for Sales Invoice]
    C --> Q1{Invoice valid and no existing IRN?}
    Q1 -->|No| R1[Reject cancelled or already generated]
    Q1 -->|Yes| M1{Sandbox and no auth token?}
    M1 -->|Yes| MOCK[Return deterministic MOCK IRN]
    M1 -->|No| API[Call Cleartax with retries]
    API --> S1{Success?}
    S1 -->|No| F1[Mark failed store irn_error]
    S1 -->|Yes| P1[Persist IRN signed QR Ack number and date on Invoice]
    MOCK --> P1
    P1 --> CAN[Cancel IRN within 24 hours with reason]
    A --> EW[Generate E-Way Bill from Invoice]
    EW --> EW1[Attach transporter vehicle and distance then call Cleartax or mock]
    A --> G1[GSTR-1 from outward Invoices for period]
    A --> G2[GSTR-2B reconcile imported supplier data vs Purchases]
    A --> G3[GSTR-3B summary for period]
```

**Triggers / feeds:** Reads Billing invoices (and their GST breakup) to push IRN/E-Way and to
build GSTR-1; reads Purchase records to reconcile GSTR-2B; writes IRN/QR/Ack and e-way fields back
onto the invoice. Uses Settings GSTIN/state/`eway_threshold`. External calls go to Cleartax
(mocked in sandbox).

---

## 9. Banking

**What it does:** Bank-facing financial reporting and reconciliation. The core flow generates a
**Bank Stock Statement** (drawing-power certificate) by valuing FIFO stock from `StockEntry` and
summing outstanding debtors from open invoices, then derives drawing power against a CC limit and
locks the statement. A separate flow **imports bank statement lines** and auto-matches them
against accounting `LedgerEntry` rows by amount and date to produce matched/unmatched buckets plus
a closing-balance difference. It also manages email-notification settings, scheduled-report
config, and backup status.

```mermaid
flowchart TD
    A[Admin or Accountant] --> B{Choose Banking Action}
    B --> C[Generate Bank Stock Statement]
    B --> D[Import Bank Statement Lines]
    B --> E[Manage Notification Settings]
    C --> F[Value FIFO Stock from StockEntry remaining qty]
    C --> G[Sum Outstanding Debtors from open Invoices]
    F --> H[Compute Total Value and Drawing Power vs CC Limit]
    G --> H
    H --> I[Persist Locked BankStockStatement with breakups]
    D --> J[Load LedgerEntry rows for period]
    J --> K[Auto Match by amount and date tolerance]
    K --> L[Split into Matched Unmatched Bank Unmatched Books]
    L --> M[Report Closing Balances and Difference]
    E --> N[Save SMTP and alert flags to settings file]
    N --> O[Send Test Email via SMTP]
```

**Triggers / feeds:** Reads Inventory `StockEntry` FIFO costs and Billing invoice outstanding for
valuation; reconciles against Accounting `LedgerEntry` postings; emits SMTP notifications and
exposes scheduled-report and backup status. Read-only across modules.

---

## 10. Reports & Dashboard

**What it does:** Read-only aggregation layer. Thin routers delegate to service classes that
aggregate already-posted data from across the ERP. The dashboard runs each metric in isolation
(rolling back on failure so one bad metric degrades gracefully) to return sales, receivables,
payables, FIFO stock value, low-stock counts, cash balance and trends. Separate report services
produce sales, purchase, stock valuation, P&L, day-book and customer/vendor ledger views over
chosen date ranges and financial year.

```mermaid
flowchart TD
    U[User requests report or dashboard] --> R[Reports and Dashboard routers]
    R --> Q{Which view}
    Q -->|Dashboard| D[DashboardService get_metrics per FY]
    D --> SAFE[Run each metric isolated rollback on error]
    SAFE --> AGG[Sales receivables payables stock value low stock cash trend]
    Q -->|Sales report| SR[Aggregate Invoices by date and customer]
    Q -->|Purchase report| PR[Aggregate Purchases by date and vendor]
    Q -->|Stock report| ST[Sum WarehouseStock with FIFO StockEntry value]
    Q -->|P and L| PL[Revenue minus FIFO COGS minus approved Expenses]
    Q -->|Day book| DB[Combine sales purchases receipts expenses for a day]
    Q -->|Ledger| LG[Customer or Vendor LedgerEntry running balance]
    AGG --> OUT[JSON metrics and rows to UI]
    SR --> OUT
    PR --> OUT
    ST --> OUT
    PL --> OUT
    DB --> OUT
    LG --> OUT
```

**Triggers / feeds:** Read-only consumer with no side effects — aggregates Billing invoices and
`InvoiceItem.fifo_cost`, Purchase records, `WarehouseStock`/`StockEntry` FIFO layers,
Accounting expenses/cash-closing, `LedgerEntry`, and vendor outstanding. Posts no journals, makes
no stock movements, triggers no GST calls.
