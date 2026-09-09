# Wholesale ERP — Refactor & Bug-Fix Notes

Captured at the end of a focused Product + Billing module pass. Reads as the running notebook for anyone picking up the work later.

## Summary

| Module | Bugs fixed | Live tests | Commits |
|---|---|---|---|
| Product (backend) | 14 | 26-case smoke | `2017290`, `81d7973` |
| Product (frontend) | 7 + 2 bonus | vite build clean | `82c8656`, `f2f7560`, `2017290` |
| Billing (backend) | 17 | 12-case HTTP + 13-case direct | `3786af8`, `ee4246c` |
| Billing (frontend) | 7 | vite build clean | `bd430d2` |
| Cross-cutting | 1 invoice page activation | working | `566906b` |
| **Total** | **48** | | |

Parallel work landed during the same window (not in this audit) — Users module (`b783467`) and Purchase module (`e66bbe4`) — explicitly out of my scope but mirror the same patterns.

## Reusable helpers added

These live in `backend/app/utils/helpers.py` and should be the first stop for similar problems in other modules.

### `next_sequence_number(db, key, prefix, fy, seed_from=None)`
Atomic row-locked counter over `invoice_sequences`. Replace any `db.query(Model).count() + 1` numbering pattern with this. Optional `seed_from(db, fy)` callback returns the max already-issued numeric suffix so the new counter doesn't collide with legacy data — and self-heals when sibling code paths advance the count without going through the helper.

**Still using the unsafe `count() + 1` pattern** (need migration):
- `app/services/accounting_service.py:376` — JE in accounting
- `app/services/warehouse_service.py:800` — JE in writeoff approve
- `app/services/purchase_service.py:37` — JE in purchase create (per Grep earlier; not personally re-verified after parallel commit `e66bbe4`)

The self-heal absorbs the collisions today, but the cleaner long-term state is to move them all through `next_sequence_number`.

### `_seed_from_suffix(db, fy, table, column)`
Callback for `next_sequence_number`. Parses the trailing numeric suffix off existing rows in `table.column` for the given financial year. Used today for `journal_entries.entry_number` and `customer_payments.payment_number`.

### `fmt_inr(amount)`
Indian-grouped currency formatting: `12,34,567.89`. Last group of 3, others of 2. Used in WhatsApp invoice share. Drop-in for any user-facing currency string.

### `_validate_hsn(v)` and `ALLOWED_HSN_LENGTHS = (4, 6, 8)`
Pydantic field-validator factory in `backend/app/schemas/products.py`. Enforces Indian HSN format (4, 6, or 8 digits, numeric only) at the API boundary. Reused by `ProductCreate`, `ProductUpdate`, `CategoryCreate`, `CategoryUpdate`, `InvoiceItemCreate`.

### IST-aware "today"
`_today_ist()` in `app/services/price_history_service.py` returns the current date in `Asia/Kolkata` regardless of where uvicorn runs. Matches the MariaDB session `+05:30` setting. Worth promoting to `app/utils/helpers.py` if more services need it.

## Architecture / pattern notes

### Cancel/void reversal pattern (Billing B-1)
On cancel of a transactional document, reverse all side effects rather than just flipping `is_cancelled`:
1. Post offsetting customer ledger entry (credit if original was debit)
2. Post reversing journal entry (DR/CR swapped)
3. Restore stock via `StockService.add_stock` with `return_in` transaction type
4. Set the document's own `outstanding_amount = 0`

Apply the same shape to Purchase cancel (the parallel commit `e66bbe4` already does this) and to any other transactional document.

### Outstanding calculation seam (Billing B-14)
When excluding cancelled invoices' ledger entries, exclude BOTH `reference_type='invoice'` AND `reference_type='invoice_cancellation'`. Otherwise the original debit and the reversal credit both get subtracted from outstanding — a 2× over-correction. Discovered by the HTTP smoke test, not static analysis.

### Pydantic v2 migration markers
- `min_items` → `min_length` on `List[]` fields
- `validator` → `field_validator` decorator
- `class Config:` → `model_config = ConfigDict(...)`

Pattern was hit in `schemas/billing.py`; same cleanup likely needed in `schemas/purchase.py`, `schemas/warehouse.py`, `schemas/accounting.py`, etc.

### React Query v4 → v5 migration markers
- `keepPreviousData: true` → `placeholderData: keepPreviousData` (with helper import)

Pattern was already swept across 9 list pages in commit `f2f7560`. Watch for new usages.

### `_auto_migrate()` track record
Two new entries landed via this pass:
1. `products.low_stock_threshold` Integer → `DECIMAL(12,3)`
2. `product_cost_history.recorded_at` made `NOT NULL DEFAULT CURRENT_TIMESTAMP` + idempotent `UPDATE … SET recorded_at = NOW() WHERE NULL` backfill

Still the project's accepted (if ugly) migration path. The startup hook now also activates due scheduled prices.

## Smoke test scripts

Lives in `backend/scripts/`. Run from `backend/` with venv activated.

- `test_product_module.py` — 26 cases via HTTP against the live API
- `test_product_authorization.py` — auth + stock retry
- `test_billing_module.py` — 12 cases via HTTP including B-1/B-14 seam check
- `test_billing_direct.py` — 13 cases via direct service calls (faster, bypasses uvicorn reload races)

Pattern for future modules: write a `test_<module>_direct.py` for fast iteration during fix work, then a `test_<module>_module.py` to catch integration / seam issues.

## Known remaining issues (not fixed in this pass)

Captured for the next person to pick up.

### High-value
- `accounting_service.py`, `warehouse_service.py`, `purchase_service.py` JE numbering still uses `count() + 1`. Helper absorbs collisions but the underlying race is still there.
- `StockService.adjust_stock` in product_service was fixed (Product B-22), but the parallel `StockAdjustmentService` in warehouse_service.py needs the same audit — it routes through `add_stock`/`consume_fifo` per my earlier read, so it might be fine already.
- `_send_invoice_email` in billing_service.py is a `pass` stub — caller flows through it on every invoice create. Either delete the call site or implement SMTP wiring.
- Outstanding calc N+1: `list_invoices` issues a customer-lookup query per row. Refactor to a single join.
- `is_active` toggle for customers is reachable only via direct API — no UI affordance. Either expose in CustomerFormPage (admin-only) or document as intentional.

### Medium
- `CustomersPage` "Active (this page)" / "Outstanding (this page)" stats are correctly labelled now but ideally would be backend-computed totals.
- `convert_quotation` backend endpoint (`POST /invoices/{id}/convert-to-invoice`) is dead — frontend always does conversion via form pre-fill + standard `/invoices/` POST. Decide: keep both, remove the dedicated endpoint, or use it from frontend.
- `BillingPage` payment modal assumes `invoice.customer_id` is set — true for B2B/B2C invoices, may not hold if a non-invoice doc ever falls into the modal flow.

### Low
- Pydantic v1 `class Config:` deprecation across all `schemas/*.py` (lots of files, cosmetic)
- N+1 customer/warehouse lookups in several list endpoints
- `BillingService.list_invoices` issues `db.commit()` during a GET to sync `paid_amount` — side effect on a read

### UX (frontend)
- `CustomerFormPage`: still lets non-admin select state but never lets them see credit_limit. Acceptable, but visually empty grid cell.
- `InvoiceDetailPage`: print stylesheet injected on `handlePrint` survives — never removed. Probably fine since it's `@media print` only, but could clean up.
- Phone validation accepts only Indian mobile patterns; some businesses use landlines. Tighten/loosen as needed.

## Recommended next module orders

1. **Warehouse** — FIFO drift, stock adjustment numbering, transfer flow. Highest data-integrity payoff.
2. **Accounting** — JE numbering migration, expense approval flow, TDS rules.
3. **GST** — Cleartax integration error paths, E-Invoice/E-Way bill state machines.
4. **Reports** — Mostly read-only; lower risk; do last.

## Commit graph (final state of this pass)

```
ee4246c Fix Billing B-1 + B-14 double-count seam + cancelled outstanding response
e66bbe4 Purchase module: 13 correctness fixes + cancel/void reversal (parallel)
bd430d2 Billing frontend: 7 fixes (admin-guard, NaN price, stat scope, validation)
b783467 Users module: login history, auto-unlock, profile, bug fixes (parallel)
3786af8 Billing module: 15 correctness + safety fixes
566906b Scheduled price activation (once-per-day) + fix vehicle add/select 404
f2f7560 Migrate keepPreviousData to v5 syntax across 9 pages
82c8656 Fix ProductsPage TypeError when search/filter changes
ba5bf6a Add Product module smoke test scripts + document in CLAUDE.md
81d7973 Fix cost-trend 500 from NULL recorded_at in product_cost_history
2017290 Product module: fix 14 bugs across schema, FIFO, frontend
654da00 Fix write-off approve raising false 'insufficient stock' + add project rules
428bbc4 Add CLAUDE.md with project guidance for Claude Code
2af02d9 Initial commit
```
