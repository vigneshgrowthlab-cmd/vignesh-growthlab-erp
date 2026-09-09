# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Wholesale ERP for Indian businesses — 10 modules covering products/inventory, purchase, billing/sales, warehouse, accounting (double-entry), GST/E-Invoice/E-Way Bill, reports, banking, and security/user management. Built on FastAPI + MariaDB backend and React 18 (Vite) frontend.

## Common Commands

### Backend (run from `backend/`)
```powershell
# First time
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env          # then edit SECRET_KEY etc.
alembic upgrade head
python seed.py                  # creates superadmin/Admin@1234, chart of accounts, sequences

# Day-to-day
venv\Scripts\activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# API docs: http://localhost:8000/api/docs  (DEBUG=true required)

# Migrations
alembic revision --autogenerate -m "describe change"
alembic upgrade head
alembic downgrade -1

# Schema-repair / data scripts (one-off, NOT idempotent migrations)
python reset_db.py              # drops & recreates all tables (destroys data)
python reset_password.py
```

### Frontend (run from `frontend/`)
```powershell
npm install
npm run dev                     # http://localhost:5173
npm run build
npm run preview
```

### Helper scripts at repo root
- `start-erp.bat` — starts MariaDB service, backend, frontend, and opens the browser.
- `erp-tools.bat` — menu for DB reset, seed, password reset, full fresh start. Run as Administrator.

### Tests
No formal pytest/Vitest test suite. There are some **smoke scripts** under `backend/scripts/` (e.g. `test_product_module.py`) that hit the running API with `requests` and report pass/fail per case — run them against a live `uvicorn` + MariaDB:
```powershell
cd backend
venv\Scripts\activate
# (backend already running at :8000, superadmin/Admin@1234)
python scripts/test_product_module.py
```
These are exploratory smoke tests, not full coverage. Don't claim a fix is verified by "running tests" unless you exercised the real app.

## Architecture

### Backend layering — strict service pattern
- **`app/api/v1/endpoints/<feature>.py`** — thin FastAPI routers. Each feature module typically exports **multiple sub-routers** (e.g. `purchase.py` exports `vendor_router`, `purchase_router`, `payment_router`). All are aggregated in [backend/app/api/v1/router.py](backend/app/api/v1/router.py).
- **`app/services/<feature>_service.py`** — all business logic. Convention: a `Service` class per entity with `@staticmethod` methods (`get_all`, `get_by_id`, `create`, `update`, `delete`, …). Endpoints inject `db: Session` and a current-user dependency, then delegate immediately.
- **`app/models/models.py`** — **single file** holding all SQLAlchemy ORM classes for the 65+ tables. When adding tables, append here rather than splitting.
- **`app/schemas/<feature>.py`** — Pydantic v2 request/response schemas.
- **`app/core/config.py`** — Pydantic-Settings `Settings` class loaded from `.env`. New env vars go here.
- **`app/db/session.py`** — engine, `SessionLocal`, `get_db()` dependency. Sets MariaDB session timezone to `+05:30` on every connection.

### Frontend layering
- **`src/pages/<feature>/`** — route components, often `<Feature>Page.jsx` + `<Feature>FormPage.jsx` + `<Feature>DetailPage.jsx` triplets. Routes are registered in [frontend/src/router.jsx](frontend/src/router.jsx); the entire authenticated tree is wrapped by `RequireAuth` + `AppLayout`.
- **`src/api/<feature>.js`** — axios call modules, one per backend domain. Shared axios instance + interceptors live in [frontend/src/api/index.js](frontend/src/api/index.js): adds `Authorization: Bearer <access_token>` from `localStorage`, and on 401 auto-calls `/api/v1/auth/refresh` then retries the original request once.
- **`src/store/authStore.js`** — Zustand store for current user / loading. Server state (lists, details) uses **React Query** (`@tanstack/react-query`) — not Zustand.
- **Path alias `@/`** → `src/` (configured in `vite.config.js`).

### Cross-cutting concerns
- **Auth:** JWT access (60 min) + refresh (7 days) via `python-jose`, passwords with bcrypt. Refresh flow is handled transparently by the frontend axios interceptor.
- **Stock costing:** FIFO via `StockEntry` records with `remaining_quantity` consumed in order. Stock movements are written through services, never directly from endpoints.
- **Accounting:** Double-entry. Every transactional service (purchase, billing, expense, receipt, payment) posts to `journal_entries` / `journal_lines` against the chart of accounts seeded by `seed.py`.
- **GST integration:** [`app/services/gst_service.py`](backend/app/services/gst_service.py) calls Cleartax. `CLEARTAX_SANDBOX=true` (default) returns mock IRN / E-Way responses — flip to `false` only with a real `CLEARTAX_AUTH_TOKEN`.
- **Financial year:** April-start (`FINANCIAL_YEAR_START_MONTH=4`); FY is stamped on most transactional rows via `app/utils/helpers.py::get_current_fy`.

### CRITICAL quirk — the `_auto_migrate()` hack
[backend/app/main.py](backend/app/main.py) runs `_auto_migrate()` on every startup. It executes hundreds of `ALTER TABLE ... ADD COLUMN`, `MODIFY COLUMN ... NULL`, and `CREATE TABLE IF NOT EXISTS` statements wrapped in try/except, silently swallowing all errors. **Implications:**
- The live schema can differ from what Alembic migrations say it should be — the startup hook may have patched it in.
- When adding a column or table, do it through **Alembic** (the proper path), but also be aware your change may already have been added by the auto-migrate list. Search `_auto_migrate()` first.
- The `backend/fix_*.py`, `backend/add_*_columns.py`, `backend/migrate_db.py`, `backend/verify_columns_db.py` scripts at the backend root are **one-off repair tools accumulated over time**, not part of a clean migration pipeline. Don't model new work on them.
- Long-term: this should be consolidated into Alembic. Don't expand `_auto_migrate()` without discussing.

### Default credentials & ports
- Login: `superadmin` / `Admin@1234` (created by `seed.py`)
- Backend: `http://localhost:8000` — docs at `/api/docs`
- Frontend: `http://localhost:5173`
- DB: MariaDB, user `erp_user` / `erp_password`, database `wholesale_erp`

## Conventions

- **Service methods are `@staticmethod`** and take `db: Session` first, then payload, then `user_id` for audit fields. Match this signature when adding new ones.
- **Endpoints stay thin** — they validate via Pydantic schemas, pull `current_user`, and call a service. Business logic in an endpoint is a smell.
- **Indian context is assumed everywhere** — GSTIN format, state codes (SMALLINT), HSN codes, INR (`DECIMAL(12,2)` or `DECIMAL(14,2)`), April-start FY. Don't internationalize unless asked.
- **Money columns** are `DECIMAL(12,2)` or `DECIMAL(14,2)`; **quantity** is `DECIMAL(12,3)`. Never use `FLOAT`.
- **No comments unless non-obvious** — the codebase is already lean on comments; match that.

##Rules
- Never break APIs
- Add migrations for DB changes
- Maintain backward compatibility
- Do not assume anything. Ask for cinfirmation before making changes.
- Do not ask for access to powershell for validation. Only ask for modification or commit activity