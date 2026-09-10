# Vignesh GrowthLab Wholesale ERP — Complete Enterprise Suite

> A modern, full-featured Wholesale Enterprise Resource Planning (ERP) platform purpose-built for Indian wholesale distributors, CCTV/security installation contractors, and tech retail enterprises.

🌐 **Live Production App:** [https://erp.vigneshgrowthlab.dev/](https://erp.vigneshgrowthlab.dev/)  
🔑 **Demo Login:** `admin` | **Password:** `Admin@1234` (Role: Super Admin)

---

## 📑 Complete Documentation & Technical Specifications

All official architecture, business workflows, QA test suites, and compliance documentation are maintained inside the [`docs/`](docs/) directory:

| Document | Format | Description |
| :--- | :---: | :--- |
| **[Module Workflows](docs/MODULE_WORKFLOWS.md)** | [MD](docs/MODULE_WORKFLOWS.md) \| [HTML](docs/module-workflows.html) | Complete architectural specifications and Mermaid flowcharts for all 10 core ERP modules. |
| **[Business Process Flows](docs/BUSINESS_PROCESS_FLOWS.md)** | [MD](docs/BUSINESS_PROCESS_FLOWS.md) \| [HTML](docs/business-process-flows.html) | Cross-departmental swimlane workflows: Procure-to-Pay (P2P), Order-to-Cash (O2C), Multi-Warehouse Stock Transfers, and Treasury/Banking. |
| **[Master Test Cases (490 Cases)](docs/TEST_CASES.md)** | [MD](docs/TEST_CASES.md) \| [XLSX](docs/TEST_CASES.xlsx) | Exhaustive test suite covering 490 positive and negative test cases across validation rules, price tiers, and RBAC guards. |
| **[E2E UI Test Plan](docs/E2E_UI_TEST_PLAN.md)** | [MD](docs/E2E_UI_TEST_PLAN.md) | End-to-end user journeys, responsive screen validation, and UI interaction test plans. |
| **[Multi-Warehouse Stock Audit](docs/WAREHOUSE_COMPLETE_TEST.md)** | [MD](docs/WAREHOUSE_COMPLETE_TEST.md) | Test procedures for inter-warehouse transfers, delivery challan linkages, adjustments, and write-offs. |
| **[Warehouse RBAC Matrix](docs/WAREHOUSE_ROLE_MATRIX_TEST.md)** | [MD](docs/WAREHOUSE_ROLE_MATRIX_TEST.md) | Role permission matrix validating warehouse-scoped data isolation for warehouse users vs. admins. |
| **[Config & Sequences Migration](docs/CONFIG_MIGRATION_PLAN.md)** | [MD](docs/CONFIG_MIGRATION_PLAN.md) | Blueprint for financial year rollover, tax band configuration, and document prefix sequence counters. |
| **[Initial Data Import Templates](docs/data-migration-templates/ERP_Initial_Data_Templates.xlsx)** | [XLSX](docs/data-migration-templates/ERP_Initial_Data_Templates.xlsx) | Pre-formatted multi-sheet Excel templates for bulk importing Products, Customers, Vendors, and Opening Stock. |
| **[Sample GST E-Invoice](docs/sample_einvoice.html)** | [HTML](docs/sample_einvoice.html) | Indian standard GST B2B tax invoice layout featuring IRN, QR code, and tax breakdown. |

---

## 🚀 Modules Included (All 10 Core Modules)

1. **M1 — Architecture & DB Schema:** 65+ relational tables in MariaDB with JWT authentication, active session tracking, and account lockout protection.
2. **M2 — Products & Inventory:** Multi-category catalog, 5-tier pricing model (Purchase Cost ≤ Floor Price ≤ B2B Price ≤ B2C Price ≤ MRP), Low Stock Alerts, and FIFO inventory tracking.
3. **M3 — Purchases & Vendors:** Vendor onboarding with state-wise GSTIN auto-validation, Purchase Orders, Goods Receipt Notes (GRN), and Vendor Payments.
4. **M4 — Sales & Billing:** B2B Tax Invoices, B2C Retail Counter sales, Quotations with 1-click invoice conversion, Delivery Challans (DC), and WhatsApp sharing.
5. **M5 — Multi-Warehouse Management:** Central godowns, retail showrooms, service hubs, and inter-warehouse stock movements.
6. **M6 — Double-Entry Accounting:** Auto-posted General Ledger, Day Book, Profit & Loss (P&L), operational expense approval workflows, cheque clearance, and TDS registers.
7. **M7 — GST / E-Invoice / E-Way Bill:** Automated E-Way Bill qualification (> ₹50,000 threshold), IRN generation (Cleartax sandbox/live), GSTR-1, GSTR-2B, and GSTR-3B registers.
8. **M8 — Reports & Live Dashboard:** Executive KPIs (Today's Sales, Month Sales, Stock Valuation, Receivables, Overdue 30+ Days, Payables, Today's Collections) and 6-month sales trend graphs.
9. **M9 — Banking & Treasury:** Bank statement reconciliation, cash register closings, and notifications.
10. **M10 — Security & User Management:** Granular Role-Based Access Control (Super Admin, Admin, Accountant, Sales, Warehouse), activity audit logs, and 2FA support.

---

## 🛠️ Technology Stack

- **Backend:** Python 3.11, FastAPI, SQLAlchemy 2.0, Pydantic v2, Alembic, MariaDB connector (`pymysql`).
- **Frontend:** React 18, Vite, Tailwind CSS, Lucide Icons, React Query (`@tanstack/react-query`), Zustand, Recharts.
- **Database:** MariaDB 10.6+ with double-entry accounting constraints and decimal-accurate financial types (`DECIMAL(14,2)`).
- **Compliance:** Indian GST rules (HSN 4/6/8-digit validation, state codes 33-TN, 29-KA, etc., April-start FY).

---

## 💻 Local Development Setup (Windows)

### Prerequisites
- Python 3.11+
- Node.js 18+
- MariaDB 10.6+

### 1. Database Setup
```sql
CREATE DATABASE wholesale_erp CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'erp_user'@'localhost' IDENTIFIED BY 'erp_password';
GRANT ALL PRIVILEGES ON wholesale_erp.* TO 'erp_user'@'localhost';
FLUSH PRIVILEGES;
```

### 2. Backend Setup
```powershell
cd backend
copy .env.example .env
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
python seed.py
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
- API Docs / Swagger: `http://localhost:8000/api/docs`

### 3. Frontend Setup
```powershell
cd frontend
npm install
npm run dev
```
- Web Application: `http://localhost:5173`

---

## 🌱 Demo Seeder Scripts

To populate a complete, realistic dataset for demonstration (products, purchases, B2B/B2C invoices, overdue ageing, receipts, and expenses):

```powershell
# Run the comprehensive live seeder against the API
python seed_live_complete.py
```

---

## 🔐 User Roles & Permissions

| Role | Access Scope |
| :--- | :--- |
| **Super Admin** | Unrestricted access across all warehouses, settings, user management, audit logs, and master overrides. |
| **Admin** | Full operational access across all 10 modules and warehouse management. |
| **Accountant** | Financial journals, expenses, customer/vendor ledgers, GST filings, and P&L reports. |
| **Sales** | Billing, Quotations, Customer Directory, and Catalog (cost prices hidden). |
| **Warehouse** | Warehouse-scoped dispatch, DC receipts, stock adjustments, and inventory tracking. |

---

## 📄 License & Attribution
Proprietary software built by **Vignesh GrowthLab** (Pollachi, Tamil Nadu).  
Founder: **Vignesh Prabhu M** | Website: [vigneshgrowthlab.dev](https://vigneshgrowthlab.dev/)
