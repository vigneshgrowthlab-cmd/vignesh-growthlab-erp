# Wholesale ERP — Complete Application (All 10 Modules)

## Modules Included
- M1 — Scaffold + DB Schema (65+ tables) + JWT Auth
- M2 — Products & Inventory (FIFO, cost tracking, categories, bulk upload)
- M3 — Purchase Module (vendors, GSTIN auto-fetch, purchases, vendor ledger)
- M4 — Sales & Billing (invoices, receipts, credit notes, WhatsApp share)
- M5 — Warehouse Management + Opening Balances
- M6 — Accounting (cheque register, TDS, expenses, ageing, trial balance)
- M7 — GST / E-Invoice / E-Way Bill (Cleartax integration)
- M8 — Reports & Dashboard (7 report types + live management dashboard)
- M9 — Bank Stock Statement + Bank Reconciliation + Notifications
- M10 — Security & User Management (sessions, activity log, 2FA, settings)

## First Time Setup (Windows)

### Prerequisites
- Python 3.11+
- Node.js 18+
- MariaDB 10.6+

### Step 1 — Database
Open MariaDB command line or phpMyAdmin and run:
```sql
CREATE DATABASE wholesale_erp CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'erp_user'@'localhost' IDENTIFIED BY 'erp_password';
GRANT ALL PRIVILEGES ON wholesale_erp.* TO 'erp_user'@'localhost';
FLUSH PRIVILEGES;
```

### Step 2 — Backend
```bat
cd backend
copy .env.example .env

REM Edit .env — set SECRET_KEY to any random 32+ character string

python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
python seed.py
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Step 3 — Frontend
Open a second terminal:
```bat
cd frontend
npm install
npm run dev
```

### Step 4 — Open browser
- App: http://localhost:5173
- API docs: http://localhost:8000/api/docs

## Default Login
- Username: `admin`
- Password: `Admin@1234`

## Key Configuration (.env)
```
SECRET_KEY=change-this-to-a-random-secret-key-minimum-32-chars
DATABASE_URL=mysql+pymysql://erp_user:erp_password@localhost:3306/wholesale_erp
COMPANY_GSTIN=29AAAAA0000A1Z5       # Your GSTIN
COMPANY_STATE_CODE=29               # Your state code
CLEARTAX_SANDBOX=true               # true = mock IRN, false = real Cleartax API
CLEARTAX_AUTH_TOKEN=                # Required only when CLEARTAX_SANDBOX=false
EWAY_BILL_THRESHOLD=50000           # Invoice value above which E-Way Bill required
EXPENSE_APPROVAL_THRESHOLD=5000    # Expense above this requires admin approval
SMTP_HOST=smtp.gmail.com            # For email alerts and 2FA OTP
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM_EMAIL=noreply@yourcompany.com
```

## Architecture
- Backend: Python 3.11 + FastAPI + SQLAlchemy + Alembic
- Database: MariaDB with 65+ tables
- Frontend: React 18 + Vite + Tailwind CSS + React Query + Recharts
- Auth: JWT (access + refresh tokens) + bcrypt
- GST: Cleartax API (sandbox mode by default)
- Stock: FIFO (First In First Out) valuation
- Accounting: Double-entry bookkeeping (auto-posted on every transaction)

## User Roles
| Role | Access |
|------|--------|
| Admin | Full access + user management + settings |
| Accountant | All modules except user management |
| Sales | Billing, products, customers only |

## Test Checklist
1. Login as admin
2. Products → New Product
3. Purchase → New Purchase (creates FIFO stock layers)
4. Billing → Customers → New Customer (GSTIN auto-fetch)
5. Billing → New Invoice → B2B Invoice
6. Accounting → Expenses → New Expense
7. GST → E-Invoice → Generate IRN (sandbox mode)
8. Warehouse → Stock → verify stock deducted from purchase
9. Reports → Dashboard → live KPIs
10. Bank Statement → Generate → Download Excel
11. Users → New User → set role → Force logout
12. Settings → Company info → Save
