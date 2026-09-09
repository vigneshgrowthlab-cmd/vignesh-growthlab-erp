# Wholesale ERP — Session Summary (Sessions 1–7)
**For continuing in Claude Code or new Claude chat**

---

## Project Details
- **Path:** `C:\Sindhu\D\WholesaleERPModule\wholesale-erp-final-build\`
- **Backend:** Python 3.11 + FastAPI + SQLAlchemy + MariaDB
- **Frontend:** React 18 + Vite + Tailwind CSS
- **DB:** `wholesale_erp` / user: `erp_user` / pass: `erp_password` / port: 3306
- **Default login:** `admin` / `Admin@1234`
- **System admin login:** `system_administrator` / (same password)

---

## Project Structure
```
wholesale-erp-final-build/
├── backend/
│   └── app/
│       ├── main.py                    ← startup + auto_migrate
│       ├── core/config.py             ← settings (env vars)
│       ├── models/models.py           ← all SQLAlchemy models
│       ├── schemas/
│       │   ├── billing.py             ← InvoiceCreate, InvoiceItemCreate etc
│       │   ├── purchase.py            ← PurchaseCreate, PurchaseItemCreate
│       │   ├── products.py            ← ProductCreate, StockAdjustmentCreate etc
│       │   ├── warehouse.py           ← StockWriteoffCreate etc
│       │   └── gst.py                 ← EWayBillGenerateRequest etc
│       ├── api/v1/endpoints/
│       │   ├── billing.py             ← invoice CRUD + print-data + eway-bill
│       │   ├── settings.py            ← company settings, sequences
│       │   ├── warehouse.py           ← warehouse CRUD + transfers + adjustments
│       │   ├── price_history.py       ← price trend, scheduled, valuation, alerts
│       │   ├── gst.py                 ← eway bill, einvoice, GSTR routers
│       │   └── price_history.py       ← new price system
│       └── services/
│           ├── billing_service.py
│           ├── purchase_service.py
│           ├── product_service.py
│           ├── warehouse_service.py
│           ├── price_history_service.py
│           ├── gst_service.py
│           └── security_service.py
└── frontend/
    └── src/
        ├── api/
│       ├── billing.js
│       ├── settings.js
│       └── warehouse.js
        ├── store/authStore.js
        └── pages/
            ├── billing/
            │   ├── InvoiceDetailPage.jsx   ← primary invoice view + print
            │   ├── InvoiceFormPage.jsx
            │   ├── BillingPage.jsx
            │   └── CustomerFormPage.jsx
            ├── purchase/PurchaseFormPage.jsx
            ├── warehouse/WarehousePage.jsx
            ├── settings/SettingsPage.jsx
            ├── gst/GSTPage.jsx
            └── billing/PriceTrendPage.jsx  ← new price trend feature
```

---

## Key Technical Patterns

### Raw SQL for new/unmapped columns (CRITICAL)
```python
# ALWAYS use raw SQL for columns added via ALTER TABLE
db.execute(text("UPDATE invoice_items SET notes=:n WHERE id=:id"), {"n": val, "id": item_id})
row = db.execute(text("SELECT state_code FROM customer_addresses WHERE id=:id"), {"id": addr_id}).fetchone()
# Order: db.add(obj) → db.flush() → raw SQL UPDATE
```

### Auto-migrate pattern (main.py)
```python
# Columns added via ALTER TABLE:
cols = [("table_name", "col_name", "DATATYPE"), ...]
# Tables created via CREATE TABLE IF NOT EXISTS in _tables list
# BOTH must be inside: with engine.connect() as c:
```

### authStore helpers (frontend)
```js
getUserWarehouse()     // returns warehouse_id (int) or null
isAdmin()              // role === 'admin' || role === 'super_admin'
isSuperAdmin()         // role === 'super_admin'
isWarehouseRole()      // role === 'warehouse'
```

### JSX multiple rows in table map
```jsx
items.map((item, idx) => (
  <>   {/* Use <> shorthand, NOT React.Fragment - avoids "React is not defined" */}
    <tr>...</tr>
    {condition && <tr>extra row</tr>}
  </>
))
```

---

## Price System (New — Sessions 6-7)

### Price Types (4 only — selling_price REMOVED)
| Field | Purpose | Used in billing |
|---|---|---|
| `purchase_cost` | Buying price | FIFO/COGS |
| `b2b_price` | Wholesale | B2B invoices + Quotation(B2B) + DC(B2B) |
| `b2c_price` | Retail/dealer | B2C invoices + Quotation(B2C) + DC(B2C) |
| `mrp` | Display only | Reference only |

### New DB Tables
```sql
product_prices     -- multi-type price history with effective dates
price_alerts       -- low margin / below cost / scheduled activation alerts
```

### Price History Service (price_history_service.py)
- `record_price_change(db, product_id, price_type, new_price, effective_from, user_id)`
  - Future date → saved as `is_scheduled=TRUE, is_active=FALSE`
  - Today/past → activates immediately, updates products table
- `activate_scheduled_prices(db, product_id=None)` — called on every invoice/purchase create
- `get_price_history(db, product_id)` → returns history + trends + scheduled
- `get_stock_valuation(db, warehouse_id)` → FIFO vs latest cost
- `get_margin_trend(db, product_id)` → margin per purchase event

### PriceTrendPage.jsx Tabs
1. **Trend Chart** — 4 line chart (purchase_cost, b2b, b2c, mrp)
2. **Price History** — all changes, audit trail (superadmin sees who/why)
3. **Scheduled** — all pending future prices across all products, search, cancel with confirmation
4. **Stock Valuation** — FIFO vs latest cost side by side
5. **Alerts** — critical/warning/info, mark read, bell badge

---

## FIFO Implementation
- **Table:** `stock_entries` (product_id, warehouse_id, unit_cost, remaining_qty, batch_date)
- **On purchase:** `StockService.add_stock()` in `product_service.py`
- **On sale:** `StockService.consume_fifo()` in `product_service.py`
- **Frozen cost:** `invoice_items.fifo_cost` set at invoice creation, never changed
- **COGS:** `SUM(fifo_cost * quantity)` in `reports_service.py`
- **⚠️ Known gap:** Invoice cancellation does NOT restore FIFO batches

---

## Invoice Number Format
- Format: `PREFIX/YY-YY/NNN` e.g. `GLB/26-27/001`
- Code: `f"{seq.prefix}/{fy_short}/{seq.last_number:03d}"`
- `fy_short` = `"26-27"` from FY `"2026-27"`

---

## Roles & Permissions
| Feature | system_administrator | Admin (unmapped WH) | Admin (mapped WH) | Others |
|---|---|---|---|---|
| Edit any warehouse | ✅ | ✅ | Own only | ❌ |
| Obsolete warehouse | ✅ | ❌ | ❌ | ❌ |
| Price audit trail | ✅ | ❌ | ❌ | ❌ |
| Price alerts | ✅ | ✅ | ✅ | ❌ |

---

## Invoice Detail Page (InvoiceDetailPage.jsx)
- Primary view AND print (InvoicePrintPage.jsx deprecated)
- Shows: E. & O.E, GST summary with CGST%/SGST%/IGST%, Declaration (B2B/B2C only)
- State: `State: Tamil Nadu (33)` for seller, bill-to, ship-to
- Bank details in footer (from company settings)
- Manual E-Way Bill entry: `+ Add E-Way Bill No.` button → `PATCH /api/v1/invoices/{id}/eway-bill`
- Notes displayed below product name in line items

---

## GST / E-Way Bill
- E-Way bill: Manual entry in InvoiceDetailPage OR generate via GSTPage
- `CLEARTAX_SANDBOX=true` in `.env` → skip real API, generate mock number immediately
- Routers registered in main.py: transporter, vehicle, einvoice, eway, gstr1, gstr2b, gstr3b

---

## SQL — Run on Fresh Setup
```sql
-- New price system
ALTER TABLE products ADD COLUMN IF NOT EXISTS b2b_price DECIMAL(12,2) DEFAULT 0;
ALTER TABLE products ADD COLUMN IF NOT EXISTS b2c_price DECIMAL(12,2) DEFAULT 0;
ALTER TABLE products ADD COLUMN IF NOT EXISTS mrp DECIMAL(12,2) DEFAULT 0;

-- Address state codes
ALTER TABLE customer_addresses ADD COLUMN IF NOT EXISTS state_code SMALLINT;

-- Company bank details
ALTER TABLE company_settings ADD COLUMN IF NOT EXISTS bank_name VARCHAR(100);
ALTER TABLE company_settings ADD COLUMN IF NOT EXISTS bank_account_number VARCHAR(30);
ALTER TABLE company_settings ADD COLUMN IF NOT EXISTS bank_ifsc VARCHAR(11);
ALTER TABLE company_settings ADD COLUMN IF NOT EXISTS bank_branch VARCHAR(100);
ALTER TABLE company_settings ADD COLUMN IF NOT EXISTS bank_account_name VARCHAR(100);
ALTER TABLE company_settings ADD COLUMN IF NOT EXISTS upi_id VARCHAR(50);
ALTER TABLE company_settings ADD COLUMN IF NOT EXISTS state_code SMALLINT;

-- Invoice/purchase items
ALTER TABLE invoice_items ADD COLUMN IF NOT EXISTS notes TEXT;
ALTER TABLE invoice_items ADD COLUMN IF NOT EXISTS serial_number VARCHAR(100);

-- Warehouse bank
ALTER TABLE warehouses ADD COLUMN IF NOT EXISTS use_company_bank BOOLEAN DEFAULT TRUE;
ALTER TABLE warehouses ADD COLUMN IF NOT EXISTS bank_name VARCHAR(100);
ALTER TABLE warehouses ADD COLUMN IF NOT EXISTS bank_account_number VARCHAR(30);
ALTER TABLE warehouses ADD COLUMN IF NOT EXISTS bank_ifsc VARCHAR(11);
ALTER TABLE warehouses ADD COLUMN IF NOT EXISTS bank_branch VARCHAR(100);
ALTER TABLE warehouses ADD COLUMN IF NOT EXISTS bank_account_name VARCHAR(100);
ALTER TABLE warehouses ADD COLUMN IF NOT EXISTS upi_id VARCHAR(50);

-- E-way bill logs
ALTER TABLE eway_bill_logs ADD COLUMN IF NOT EXISTS valid_upto DATETIME;
ALTER TABLE eway_bill_logs ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'pending';
ALTER TABLE eway_bill_logs ADD COLUMN IF NOT EXISTS request_payload TEXT;
ALTER TABLE eway_bill_logs ADD COLUMN IF NOT EXISTS response_payload TEXT;
ALTER TABLE eway_bill_logs ADD COLUMN IF NOT EXISTS error_message TEXT;
ALTER TABLE eway_bill_logs ADD COLUMN IF NOT EXISTS vehicle_id INT;
ALTER TABLE eway_bill_logs ADD COLUMN IF NOT EXISTS driver_name VARCHAR(100);
ALTER TABLE eway_bill_logs ADD COLUMN IF NOT EXISTS lr_number VARCHAR(50);
ALTER TABLE eway_bill_logs ADD COLUMN IF NOT EXISTS transporter_name VARCHAR(100);
ALTER TABLE eway_bill_logs ADD COLUMN IF NOT EXISTS transport_mode VARCHAR(20);
ALTER TABLE eway_bill_logs ADD COLUMN IF NOT EXISTS distance_km INT;
ALTER TABLE eway_bill_logs ADD COLUMN IF NOT EXISTS from_pincode VARCHAR(6);
ALTER TABLE eway_bill_logs ADD COLUMN IF NOT EXISTS to_pincode VARCHAR(6);
ALTER TABLE eway_bill_logs ADD COLUMN IF NOT EXISTS dc_destination_warehouse_id INT;
ALTER TABLE eway_bill_logs ADD COLUMN IF NOT EXISTS dc_status VARCHAR(20);

-- New tables (auto-created on restart)
CREATE TABLE IF NOT EXISTS product_prices (
    id INT AUTO_INCREMENT PRIMARY KEY,
    product_id INT NOT NULL,
    price_type VARCHAR(20) NOT NULL,
    price DECIMAL(12,2) NOT NULL,
    previous_price DECIMAL(12,2),
    effective_from DATE NOT NULL,
    effective_to DATE,
    is_active BOOLEAN DEFAULT TRUE,
    is_scheduled BOOLEAN DEFAULT FALSE,
    change_reason VARCHAR(200),
    notes TEXT,
    created_by INT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_pp_product_type (product_id, price_type)
);
CREATE TABLE IF NOT EXISTS price_alerts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    product_id INT NOT NULL,
    alert_type VARCHAR(30) NOT NULL,
    message TEXT NOT NULL,
    severity VARCHAR(10) DEFAULT 'warning',
    is_read BOOLEAN DEFAULT FALSE,
    email_sent BOOLEAN DEFAULT FALSE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS stock_adjustments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    adjustment_number VARCHAR(30) UNIQUE,
    warehouse_id INT NOT NULL, product_id INT NOT NULL,
    adjustment_type VARCHAR(10), quantity DECIMAL(12,3) NOT NULL,
    unit_cost DECIMAL(12,2), reason TEXT, notes TEXT,
    adjustment_date DATE, created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_by INT, updated_by INT
);
CREATE TABLE IF NOT EXISTS stock_writeoffs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    writeoff_number VARCHAR(30) UNIQUE,
    warehouse_id INT NOT NULL, product_id INT NOT NULL,
    quantity DECIMAL(12,3) NOT NULL, reason_type VARCHAR(30),
    reason_detail TEXT, writeoff_date DATE,
    status VARCHAR(20) DEFAULT 'pending',
    approved_by INT, approved_at DATETIME,
    admin_notes TEXT, notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_by INT, updated_by INT
);
```

---

## Known Issues / Pending Work
- Invoice cancellation does NOT restore FIFO batches (stock_entries.remaining_qty not reversed)
- `fifo_cost = NULL` for items with no purchase history → COGS understated
- No warehouse-wise / salesperson-wise profit reports
- No `sale_item → stock_entry` audit trail table
- Email alerts for price changes not yet implemented (in-app only)
- Tally export not built
- Dashboard charts not built
- GSTR-1 / GSTR-3B export UI not built

---

## Common Error Patterns
| Error | Cause | Fix |
|---|---|---|
| `React is not defined` | Used `React.Fragment` without import | Use `<>` shorthand |
| `Unknown column X in INSERT` | Column not in DB yet | Run ALTER TABLE or restart |
| `selling_price attribute error` | Old schema used selling_price | Use b2b_price/b2c_price |
| `price_type not in PRICE_TYPES` | Payload fields extracted after use | Extract before validation |
| `activate_scheduled_prices` commit | Was committing inside transaction | Removed — caller commits |
| `504 on eway bill` | Real Cleartax API timeout | Set CLEARTAX_SANDBOX=true |
