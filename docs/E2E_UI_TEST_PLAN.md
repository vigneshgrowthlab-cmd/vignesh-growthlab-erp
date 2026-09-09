# End-to-End UI Test Case — "First-Time Client, Full Business Cycle"

**Persona:** A new wholesale toy distributor ("NextGen Toys") onboarding onto the ERP for the first time.
**Scope:** One continuous business scenario executed live through the UI at `http://localhost:5173`, touching all 10 modules in natural dependency order: buy stock → sell it → collect money → verify books, tax, and reports.
**Pre-conditions:** MariaDB running, backend at `:8000`, frontend at `:5173`, seeded admin user (`admin` / `Admin@1234`), chart of accounts and sequences seeded, `CLEARTAX_SANDBOX=true`.

**Test data used throughout (created during the run):**

| Entity | Value |
|---|---|
| Product | "RC Racing Car 1:18" — HSN 9503, GST 18%, cost ₹450, B2B ₹600, B2C ₹750, MRP ₹999 |
| Vendor | "Bright Toys Manufacturing" (B2B) |
| Customer | "Kiddo Retail Mart" (B2B) and a walk-in B2C sale |
| Purchase | 100 units @ ₹450 |
| Sale | 20 units @ B2B price |

---

## TC-01 — Login & Dashboard (Security module, part 1)

| # | Step | Expected |
|---|---|---|
| 1.1 | Open `/` while logged out | Redirect to `/login` |
| 1.2 | Login with wrong password `admin` / `wrong` | Error message, stay on login |
| 1.3 | Login `admin` / `Admin@1234` | Redirect to Dashboard `/` |
| 1.4 | Inspect dashboard | KPI cards/widgets render without errors; sidebar shows all modules for admin role |

## TC-02 — Products & Inventory

| # | Step | Expected |
|---|---|---|
| 2.1 | Products → Create product (name, category, HSN 9503, GST 18%, unit Nos, cost 450, B2B 600, B2C 750, MRP 999) | Saves; part code auto-generated from category prefix |
| 2.2 | Validation: try saving without name/HSN; try bad HSN (3 digits) | Blocked with clear messages |
| 2.3 | Products list: search by name, filter by category | New product found; stock shows 0 |
| 2.4 | Edit product (change low-stock threshold to 10) | Persists on reload |

## TC-03 — Purchase (Vendor → PO → Receive stock)

| # | Step | Expected |
|---|---|---|
| 3.1 | Purchase → Vendors → Create vendor (trade name, GSTIN, state, credit days) | Vendor saved, appears in list |
| 3.2 | Purchase Entry → New: vendor, warehouse, vendor invoice no `BTM-001`, today's date, line: product, qty 100, cost 450 | HSN/GST auto-fill from product; totals auto-compute (taxable 45,000 + 18% GST = 53,100) |
| 3.3 | Save purchase | Purchase created; stock should increase to 100 (FIFO entry created) |
| 3.4 | Verify in Products/Warehouse | Stock = 100 in chosen warehouse |
| 3.5 | Vendor Payments: record a part payment (e.g. ₹20,000) | Payment saved; vendor outstanding reduces to 33,100 |

## TC-04 — Billing & Sales (Customer → Invoice → Receipt)

| # | Step | Expected |
|---|---|---|
| 4.1 | Billing → Customers → Create B2B customer (trade name, GSTIN, state, credit limit) | Customer saved |
| 4.2 | Billing → New Invoice: B2B type, customer, line: product qty 20 | Unit price auto-fills B2B ₹600; totals: 12,000 + 18% = 14,160 |
| 4.3 | Save invoice | Invoice number generated per FY sequence; status unpaid |
| 4.4 | Invoice detail page | Lines, taxes, outstanding shown correctly |
| 4.5 | Stock check | Product stock reduced 100 → 80 (FIFO consumption) |
| 4.6 | Record receipt (full ₹14,160, mode UPI) | Outstanding 0, status paid; receipt listed under Billing → Receipts |
| 4.7 | Print view `/billing/:id/print` | Printable invoice renders with GST breakup |
| 4.8 | Create a Quotation, then convert to invoice (if available) | Quotation does not move stock; conversion creates invoice |

## TC-05 — Warehouse

| # | Step | Expected |
|---|---|---|
| 5.1 | Warehouse → Stock tab | Product shows qty 80 with FIFO value (80 × 450 = 36,000) |
| 5.2 | Stock adjustment (-2, reason damage) | Stock 78; adjustment listed in Adjustments tab |
| 5.3 | Transfer (if ≥2 warehouses; else create via modal or skip) | Source decreases, destination increases |
| 5.4 | Ageing tab | Stock age buckets render |

## TC-06 — Accounting (double-entry verification)

| # | Step | Expected |
|---|---|---|
| 6.1 | Accounting → Journal | Journal entries exist for purchase, sale, receipt, vendor payment |
| 6.2 | Trial Balance | Debits = Credits (balanced) |
| 6.3 | Add an expense (e.g. ₹500 office expense, cash) | Saved; appears in journal |
| 6.4 | Customer ageing / Vendor dues tabs | Reflect 0 customer outstanding, vendor due ₹33,100 |

## TC-07 — GST (sandbox)

| # | Step | Expected |
|---|---|---|
| 7.1 | GST → E-Invoice: generate IRN for the B2B invoice | Mock IRN returned (sandbox), stored on invoice |
| 7.2 | GSTR-1 for current month | Shows the B2B invoice with correct taxable value/tax |
| 7.3 | GSTR-3B summary | Outward tax matches invoice tax |

## TC-08 — Reports

| # | Step | Expected |
|---|---|---|
| 8.1 | Reports page: run sales/stock/ledger reports for today | Data matches transactions created above |
| 8.2 | Customer ledger from customer row | Shows invoice + receipt, closing balance 0 |

## TC-09 — Banking

| # | Step | Expected |
|---|---|---|
| 9.1 | Bank → generate bank stock statement as of today | Statement includes stock value + receivables; locks after generation |
| 9.2 | Other tabs (reconciliation, notifications) | Render without errors |

## TC-10 — Security, Users, Audit & Configuration

| # | Step | Expected |
|---|---|---|
| 10.1 | Users → create a `sales` role user | User created |
| 10.2 | Activity log / login history | Shows this session's actions (creates from TC-02..09) |
| 10.3 | Audit Log page (super-admin) | Write actions recorded |
| 10.4 | Settings → Configuration: open a domain (GST), view value history; propose a draft change and revoke it | History renders; draft lifecycle works |
| 10.5 | Logout, login as new sales user | Menu restricted per role (no Users/Settings/Audit) |
| 10.6 | Logout | Returns to login page |

---

**Pass criteria:** every step's "Expected" observed in the UI with no console/network errors; cross-module consistency holds (stock counts, vendor/customer outstanding, trial balance).

---

# Execution Results — 12 Jun 2026 (live run, admin/Admin@1234, pre-existing data in DB)

| TC | Module | Result | Notes |
|---|---|---|---|
| TC-01 | Login & Dashboard | **PASS** | Wrong password rejected; dashboard renders; "No warehouse assigned" warning for admin |
| TC-02 | Products | **PASS** | Inline category create (Toys/TOY), part code auto TOY1, HSN/required validation, search, edit persisted |
| TC-03 | Purchase | **PASS** | BTM-001: 100×₹450 = ₹53,100 auto-calc; stock 0→100; VP-202627-0020 ₹20,000 → outstanding ₹33,100 Partial. ⚠ tagged IGST (see F1) |
| TC-04 | Billing & Sales | **PASS** | BINV/26-27/031 ₹14,160 (B2B price auto); stock 100→80; receipt RCP-202627-0040 → Paid; tax invoice w/ CGST+SGST correct. ⚠ silent validation (F2) |
| TC-05 | Warehouse | **PASS** | Stock 80 @ ₹36,000 FIFO; ADJ-202627-0047 −2 damage → 78 @ ₹35,100; ageing 0d bucket correct. (Transfer not exercised) |
| TC-06 | Accounting | **PASS** | JEs auto-posted for purchase/payment/invoice/receipt; Trial Balance balanced ₹8,50,155.55; EXP-202627-0003 ₹500. ⚠ Vendor Dues empty (F5) |
| TC-07 | GST | **PARTIAL** | IRN MOCK-IRN-BINV/26-27/032-119 generated after .env fix (F4); HSN 4-digit vs 6-digit conflict (F3); GSTR-1 FY list missing 2026-27 (F6); GSTR-3B generated |
| TC-08 | Reports | **PASS** | Sales report exact (2 inv, ₹15,576, outstanding ₹1,416); customer ledger 0 → 14,160 → 0 → 1,416 closing |
| TC-09 | Banking | **FAIL** | Bank Stock Statement API 500 — `bank_stock_statements.statement_month` missing in DB (F7); Backup Status endpoint 404 (F8); Notifications tab OK |
| TC-10 | Security & Config | **PASS** | e2e_sales user created; role menu/route guards enforced (/users, /settings/config redirect); cost column hidden for sales; logout OK. Config admin page needs super_admin (not tested with seeded admin) |

## Findings

1. **F1 — Purchase GST type = IGST for intra-state vendor.** TN company + TN vendor (GSTIN 33…) purchase tagged IGST; sales side correctly splits CGST/SGST. Purchase accounting/ITC classification may be wrong.
2. **F2 — Invoice form fails silently.** With "Collecting payment" toggle on (default) and amount empty, or missing billing address, Save Invoice does nothing — error renders below the fold, no toast.
3. **F3 — HSN length rules conflict.** Product form accepts 4-digit HSN; e-invoice generation rejects anything < 6 digits. Client discovers at IRN time, after invoicing.
4. **F4 — Sandbox mock never triggers with default .env.** `CLEARTAX_AUTH_TOKEN=your-cleartax-token-here` placeholder makes `_should_mock()` false → real Cleartax API attempted and fails silently despite `CLEARTAX_SANDBOX=true`. Fixed during run by blanking the token.
5. **F5 — "Vendor Dues" tab misleading.** Only shows purchases with `payment_due_date` within next 7 days; excludes overdue (`>= today` filter makes `is_overdue` dead code) and purchases without due dates. ₹33,100 payable invisible.
6. **F6 — GST returns FY hardcoded** to `['2025-26','2024-25']` (GSTPage.jsx:401,559,598). Current FY 2026-27 unavailable → GSTR-1/2B/3B cannot be filed for current periods. Also GSTR-1 periods are Apr–Mar while GSTR-3B shows Jan–Dec.
7. **F7 — Bank Stock Statement module broken (500).** Model column `statement_month` (models.py:939) was never added to `bank_stock_statements` table by any migration or `_auto_migrate()`. All list/generate calls fail.
8. **F8 — Backup Status endpoint missing.** UI calls `GET /api/v1/backup/status` → 404; tab renders silently blank.
9. **Minor:** single refresh-token per user — an API login elsewhere kills the browser session on next refresh. New category not auto-selected after inline create. React "unique key" warnings on PurchaseFormPage/InvoiceFormPage/StockTab. Payment-number sequence gaps. Stock adjustments post no journal entry (write-offs do).

**Test data created:** category Toys (TOY), product TOY1 RC Racing Car 1:18 (HSN 95030030), vendor Bright Toys Manufacturing, customer Kiddo Retail Mart (+address), purchase BTM-001, invoices BINV/26-27/031 & 032, receipt RCP-202627-0040, vendor payment VP-202627-0020, adjustment ADJ-202627-0047, expense EXP-202627-0003, user e2e_sales (E2eSales@1234), mock IRN on /032. `.env` change: `CLEARTAX_AUTH_TOKEN` blanked.
