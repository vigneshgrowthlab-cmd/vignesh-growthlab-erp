# Warehouse Module — Complete E2E Test Results

**Run date:** 2026-06-12  
**Backend:** `http://127.0.0.1:8000` (uvicorn, production mode)  
**Test script:** `backend/scripts/test_warehouse_complete.py`  
**Result:** **62 PASS / 0 FAIL** (62 assertions across 11 test cases)

---

## Test Users and Warehouses

| Resource | ID | Details |
|---|---|---|
| TestWH-Alpha | 73 | Chennai, Tamil Nadu — source warehouse |
| TestWH-Beta  | 74 | Mumbai, Maharashtra — destination warehouse |
| `twh_alpha`  | 19 | role=warehouse, assigned WH-A (id=73) |
| `twh_beta`   | 20 | role=warehouse, assigned WH-B (id=74) |
| `twh_sales`  | 21 | role=sales, no warehouse |
| `twh_acct`   | 22 | role=accountant, no warehouse |
| `admin`      | (seeded) | role=admin, no warehouse |

---

## Test Cases

### TC-01: Warehouse CRUD

| ID | Description | Expected | Got | Outcome |
|---|---|---|---|---|
| TC-01a | Create warehouse (admin) | 201 | 201 | **PASS** |
| TC-01b | Update warehouse (admin) | 200 | 200 | **PASS** |
| TC-01c | Get warehouse details (any auth) | 200 | 200 | **PASS** |
| TC-01d | Create warehouse (warehouse role) → 403 | 403 | 403 | **PASS** |
| TC-01e | Create warehouse (sales role) → 403 | 403 | 403 | **PASS** |

### TC-02: Stock Adjustment — seed + role gates

| ID | Description | Expected | Got | Outcome |
|---|---|---|---|---|
| TC-02a | Seed 100 units into WH-A (admin) | 201 | 201 | **PASS** |
| TC-02b | Seed 10 units WH-A (warehouse role) | 201 | 201 | **PASS** |
| TC-02c | Adjustment (sales role) → 403 | 403 | 403 | **PASS** |
| TC-02d | Adjustment (accountant role) → 403 | 403 | 403 | **PASS** |
| TC-02e | Stock-out adjustment (admin) | 201 | 201 | **PASS** |
| TC-02f | List adjustments (warehouse_ops) | 200 | 200 | **PASS** |
| TC-02g | List adjustments (sales) → 403 | 403 | 403 | **PASS** |

### TC-03: Stock View

| ID | Description | Expected | Got | Outcome |
|---|---|---|---|---|
| TC-03a | WH-A has stock after adjustment | qty>0 | True | **PASS** |
| TC-03b | View stock (admin) | 200 | 200 | **PASS** |
| TC-03b | View stock (warehouse_A) | 200 | 200 | **PASS** |
| TC-03b | View stock (sales) | 200 | 200 | **PASS** |
| TC-03b | View stock (accountant) | 200 | 200 | **PASS** |
| TC-03c | Filter stock by product_id | 200 | 200 | **PASS** |

> Stock endpoint returns `[{product_id, warehouses: [{warehouse_id, warehouse_name, quantity}]}]` — not a flat list.

### TC-04: Create Delivery Challan (DC)

| ID | Description | Expected | Got | Outcome |
|---|---|---|---|---|
| TC-04a | Create DC (admin) | 201 | 201 | **PASS** |
| TC-04b | DC appears in delivery-challan list | 200 | 200 | **PASS** |
| TC-04c | Create DC (warehouse user) — auth gate open | not_403 | 201 | **PASS** |
| TC-04d | Create DC (sales role) — gate check | 201 | 201 | **PASS** |
| TC-04e | DC creation: WH-A stock unchanged | same as before | unchanged | **PASS** |

> **Design note:** DC creation does NOT consume stock. Stock is deducted at transfer creation.  
> Confirm adds stock to destination; reject restores it to source.

### TC-05: Stock Transfer Linked to DC

| ID | Description | Expected | Got | Outcome |
|---|---|---|---|---|
| TC-05a | Create transfer with dc_ids=[DC_ID] (warehouse_A user) | 201 | 201 | **PASS** |
| TC-05b | Get transfer detail | 200 | 200 | **PASS** |
| TC-05c | Transfer has DC linked (dc_count=1) | 1 | 1 | **PASS** |
| TC-05d | pending_for_me: WH-B user sees transfer | 200 | 200 | **PASS** |
| TC-05e | pending_for_me: WH-A user does NOT see WH-B-dest transfer | False | False | **PASS** |

> Transfer creation requires at least one DC via `dc_ids` — business rule in `warehouse_service.py`.  
> Transfer creation deducts stock from source WH immediately.

### TC-06: DC Confirm — Destination User Flow

| ID | Description | Expected | Got | Outcome |
|---|---|---|---|---|
| TC-06a | Confirm DC by WH-A user (not dest) → 403 | 403 | 403 | **PASS** |
| TC-06b | Confirm DC by sales (no WH) → 403 | 403 | 403 | **PASS** |
| TC-06c | Confirm DC by admin (no WH) → 403 | 403 | 403 | **PASS** |
| TC-06d | Confirm DC by WH-B user (dest) → 200 | 200 | 200 | **PASS** |
| TC-06e | WH-B stock increased by 20 after confirm | True | True | **PASS** |

> Only super_admin or the destination-warehouse user can confirm a DC.  
> Admin without a warehouse assignment is blocked (same F-WH-01 pattern as transfers).

### TC-07: DC Reject Flow

| ID | Description | Expected | Got | Outcome |
|---|---|---|---|---|
| TC-07a | Create rejection-test DC (admin) | 201 | 201 | **PASS** |
| TC-07b | Create rejection transfer (WH-A user, source) | not_403 | 201 | **PASS** |
| TC-07c | Reject DC by WH-A user (not dest) → 403 | 403 | 403 | **PASS** |
| TC-07d | Reject DC by WH-B user (dest) → 200 | 200 | 200 | **PASS** |
| TC-07e | WH-A stock restored after DC rejection | restored | True | **PASS** |

> Rejection restores the deducted stock to source WH. Stock balance returns to the pre-transfer baseline.

### TC-08: Transfer List and Filters

| ID | Description | Expected | Got | Outcome |
|---|---|---|---|---|
| TC-08a | List transfers (admin) | 200 | 200 | **PASS** |
| TC-08a | List transfers (warehouse_A) | 200 | 200 | **PASS** |
| TC-08a | List transfers (sales) | 200 | 200 | **PASS** |
| TC-08a | List transfers (accountant) | 200 | 200 | **PASS** |
| TC-08b | Filter transfers by warehouse_id | 200 | 200 | **PASS** |
| TC-08c | pending_for_me for sales (no WH) | 200 | 200 | **PASS** |
| TC-08d | sales pending_for_me total = 0 | 0 | 0 | **PASS** |

### TC-09: Stock Write-off Workflow

| ID | Description | Expected | Got | Outcome |
|---|---|---|---|---|
| TC-09a | Create write-off (warehouse role) | 201 | 201 | **PASS** |
| TC-09b | Create write-off (admin) | 201 | 201 | **PASS** |
| TC-09c | Create write-off (sales) → 403 | 403 | 403 | **PASS** |
| TC-09d | List write-offs (warehouse_ops) | 200 | 200 | **PASS** |
| TC-09e | List write-offs (sales) → 403 | 403 | 403 | **PASS** |
| TC-09f | Approve write-off (admin) | 200 | 200 | **PASS** |
| TC-09g | Approve write-off (warehouse role) → 403 | 403 | 403 | **PASS** |
| TC-09h | Stock reduced after write-off approval | True | True | **PASS** |
| TC-09i | Reject write-off (approved=False) | 200 | 200 | **PASS** |

> Write-offs have a two-step workflow: warehouse creates request (pending) → admin approves or rejects.  
> Stock is consumed only on approval. Rejection leaves stock unchanged.

### TC-10: Stock Ageing

| ID | Description | Expected | Got | Outcome |
|---|---|---|---|---|
| TC-10a | Stock ageing (admin) | 200 | 200 | **PASS** |
| TC-10a | Stock ageing (warehouse_A) | 200 | 200 | **PASS** |
| TC-10a | Stock ageing (warehouse_B) | 200 | 200 | **PASS** |
| TC-10a | Stock ageing (sales) → 403 | 403 | 403 | **PASS** |
| TC-10a | Stock ageing (accountant) → 403 | 403 | 403 | **PASS** |
| TC-10b | Stock ageing filtered by WH-A | 200 | 200 | **PASS** |

> Ageing endpoint requires `require_warehouse_ops` (admin or warehouse roles only).

### TC-11: Final Stock Balance

| ID | Description | Expected | Got | Outcome |
|---|---|---|---|---|
| TC-11a | WH-B received stock via confirmed DC transfer | qty>0 | 60.0 | **PASS** |
| TC-11b | WH-A still has remaining stock | qty>0 | 264.0 | **PASS** |

---

## Stock Movement Model (Verified)

```
DC create       → stock UNCHANGED in source WH (DC is a physical document only)
Transfer create → stock DEDUCTED from source WH immediately
Transfer confirm → stock CREDITED to destination WH
Transfer reject  → stock RESTORED to source WH (reverses transfer creation deduction)
Write-off create → stock UNCHANGED (pending approval)
Write-off approve → stock CONSUMED from WH
Write-off reject  → stock UNCHANGED
```

---

## Findings

### F-WH-01 — Admin role blocked from transfers without warehouse assignment (Open)

**Severity:** Medium  
**Affects:** TC-07b used `tok_wh_a` (WH-A user) as workaround; the admin token would have received 403.

Same finding documented in [`docs/WAREHOUSE_ROLE_MATRIX_TEST.md`](./WAREHOUSE_ROLE_MATRIX_TEST.md).

**Root cause:** `_assert_user_can_transfer` in `backend/app/api/v1/endpoints/warehouse.py:36`
exempts only `is_super_admin(user)`. Admin role without a warehouse_id hits the WH-mapping guard.

**Proposed fix:**
```python
# warehouse.py line 40
if is_super_admin(user) or _role_str(user) == "admin":
    return
```

The same pattern applies to `_assert_user_can_approve_destination` for confirm/reject.

---

## Notes

- Test is additive (idempotent warehouses/users, cumulative stock). Stock totals grow on repeat runs.
- `admin` role user does not have a warehouse assignment — super_admin credentials were not available in test env.
- Sales role can create DC invoices (billing endpoint is not gated for sales); this is expected per billing module design.
- The `dc_ids` field on `StockTransferCreate` requires at least one DC — enforced in `warehouse_service.py`.
