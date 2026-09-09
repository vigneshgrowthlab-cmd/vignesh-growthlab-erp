# Warehouse Role-Matrix Test Results

**Run date:** 2026-06-12  
**Backend:** `http://127.0.0.1:8000` (uvicorn, no --reload)  
**Test script:** `backend/scripts/test_warehouse_role_matrix.py`  
**Result:** **38 PASS / 1 FAIL** (39 assertions across 8 test cases)

---

## Test Users Created

| Username | Role | Warehouse | Purpose |
|---|---|---|---|
| `test_wh_alpha` | warehouse | WH-A (new, code WH14) | WH-A source user |
| `test_wh_beta` | warehouse | WH-B (new, code WH15) | WH-B destination user |
| `test_sales_nwh` | sales | None | No-warehouse sales role |
| `test_acct_nwh` | accountant | None | No-warehouse accountant role |
| `admin` (seeded) | admin | None | Admin role, no WH assigned |

> `super_admin` role (`system_administrator` user) not tested separately — password unknown in test env; the seeded `admin` role covers the `require_admin` gate.

---

## Role Matrix Validated

| Operation | admin | warehouse (own WH) | warehouse (other WH) | sales | accountant |
|---|:---:|:---:|:---:|:---:|:---:|
| List warehouses | PASS | PASS | PASS | PASS | PASS |
| View stock | PASS | PASS | PASS | PASS | PASS |
| Stock ageing | PASS (200) | PASS (200) | PASS (200) | PASS (403) | PASS (403) |
| Create warehouse | PASS (201) | PASS (403) | — | PASS (403) | PASS (403) |
| Create transfer (mapped WH) | FAIL* | PASS | PASS (403) | PASS (403) | PASS (403) |
| Confirm DC (dest WH) | PASS (403) | PASS (200/400) | PASS (403) | PASS (403) | — |
| Reject DC (dest WH) | PASS (403) | PASS (200/400) | PASS (403) | PASS (403) | — |
| Stock adjustment | PASS (201) | PASS (201) | — | PASS (403) | PASS (403) |
| pending_for_me filter | PASS | PASS | — | PASS (empty) | — |

*See Finding F-WH-01 below.

---

## Detailed Results

### TC-WH-01: Warehouse List — all authenticated users

| ID | Role | Expected | Got | Outcome |
|---|---|---|---|---|
| WH-01 | admin | 200 | 200 | **PASS** |
| WH-01 | warehouse_A | 200 | 200 | **PASS** |
| WH-01 | warehouse_B | 200 | 200 | **PASS** |
| WH-01 | sales | 200 | 200 | **PASS** |
| WH-01 | accountant | 200 | 200 | **PASS** |

### TC-WH-02: Stock View — all authenticated users

| ID | Role | Expected | Got | Outcome |
|---|---|---|---|---|
| WH-02 | admin | 200 | 200 | **PASS** |
| WH-02 | warehouse_A | 200 | 200 | **PASS** |
| WH-02 | warehouse_B | 200 | 200 | **PASS** |
| WH-02 | sales | 200 | 200 | **PASS** |
| WH-02 | accountant | 200 | 200 | **PASS** |

### TC-WH-03: Stock Ageing — `require_warehouse_ops` gate

Gate allows: `super_admin`, `admin`, `warehouse`. Blocks: `sales`, `accountant`.

| ID | Role | Expected | Got | Outcome |
|---|---|---|---|---|
| WH-03 | admin | 200 | 200 | **PASS** |
| WH-03 | warehouse_A | 200 | 200 | **PASS** |
| WH-03 | warehouse_B | 200 | 200 | **PASS** |
| WH-03 | sales | 403 | 403 | **PASS** |
| WH-03 | accountant | 403 | 403 | **PASS** |

### TC-WH-04: Create Warehouse — `require_admin` gate

| ID | Role | Expected | Got | Outcome |
|---|---|---|---|---|
| WH-04 | admin | 201 | 201 | **PASS** |
| WH-04 | warehouse_A | 403 | 403 | **PASS** |
| WH-04 | sales | 403 | 403 | **PASS** |
| WH-04 | accountant | 403 | 403 | **PASS** |

### TC-WH-05: Create Stock Transfer — warehouse-mapping guard

**Auth rule in code:** `_assert_user_can_transfer` — only `super_admin` is fully exempt;  
everyone else must have `warehouse_id` matching source or destination.

| ID | Role | Warehouse mapping | Expected | Got | Outcome |
|---|---|---|---|---|---|
| WH-05a | admin | None | not_403 | **403** | **FAIL** — see F-WH-01 |
| WH-05b | warehouse_A | source WH | not_403 | 400 (no DC) | **PASS** — gate opened |
| WH-05c | warehouse_B | dest WH | not_403 | 400 (no DC) | **PASS** — gate opened |
| WH-05d | sales | None | 403 | 403 | **PASS** |
| WH-05e | accountant | None | 403 | 403 | **PASS** |
| WH-05f | warehouse_A | neither WH | 403 | 403 | **PASS** |

> WH-05b/c 400 = business logic: transfer requires at least one linked DC invoice. The **auth gate opened** (not 403), which is the tested property.

### TC-WH-06: Confirm / Reject DC — destination WH guard

**Setup:** Transfer TRF-202627-0010 (id=19, source=WH 2, dest=WH 8) used.  
`test_wh_beta` temporarily reassigned to WH 8 as destination user; restored afterward.

| ID | Role | Warehouse | Expected | Got | Outcome |
|---|---|---|---|---|---|
| WH-06a | warehouse_B (dest=WH 8) | 8 | not_403 | 400 (no DC) | **PASS** — guard opened |
| WH-06b | warehouse_A (not dest) | WH-A | 403 | 403 | **PASS** |
| WH-06c | sales | None | 403 | 403 | **PASS** |
| WH-06d | admin | None | 403 | 403 | **PASS** |
| WH-06e | warehouse_A (not dest) reject | WH-A | 403 | 403 | **PASS** |
| WH-06f | warehouse_B (dest=WH 8) reject | 8 | not_403 | 400 (no DC) | **PASS** — guard opened |

### TC-WH-07: Stock Adjustment — `require_warehouse_ops` gate

| ID | Role | Expected | Got | Outcome |
|---|---|---|---|---|
| WH-07 | admin | not_403 | 201 | **PASS** |
| WH-07 | warehouse_A | not_403 | 201 | **PASS** |
| WH-07 | sales | 403 | 403 | **PASS** |
| WH-07 | accountant | 403 | 403 | **PASS** |

### TC-WH-08: pending_for_me Transfer Filter

| ID | Role | WH | Expected | Got | Outcome |
|---|---|---|---|---|---|
| WH-08 | warehouse_B | WH-B | 200 | 200 | **PASS** |
| WH-08 | warehouse_A | WH-A | 200 | 200 | **PASS** |
| WH-08 | sales | None | 200 | 200 | **PASS** |
| WH-08x | sales | None | 0 items | 0 items | **PASS** — correctly empty |

---

## Findings

### F-WH-01 — Admin role cannot create stock transfers without a warehouse assignment

**Severity:** Medium  
**Test case:** WH-05a  
**Actual HTTP:** 403  
**Error message:** `"You must be mapped to a warehouse to create transfers. Ask a super-admin to assign your warehouse."`

**Root cause:** `_assert_user_can_transfer` in [`backend/app/api/v1/endpoints/warehouse.py:36`](../backend/app/api/v1/endpoints/warehouse.py) exempts only `is_super_admin(user)` (role == `super_admin`). The `admin` role is not `super_admin`, so an admin with `warehouse_id=NULL` hits the no-WH guard and gets 403.

**Intended behaviour (per role matrix):** `admin` should be able to create transfers between any warehouses, similar to `super_admin`, without needing to be assigned to a warehouse themselves.

**Fix options:**
1. Extend the exempt check to also skip `admin`:
   ```python
   # warehouse.py line 40
   if is_super_admin(user) or _role_str(user) == "admin":
       return
   ```
2. OR always assign admin users to a warehouse (operational workaround — not scalable).

**Impact:** Admin users managing warehouse operations will be blocked from initiating transfers unless they're manually assigned to a warehouse. Only `system_administrator` (super_admin) can currently create transfers without a warehouse mapping.

---

## Notes

- `super_admin` login credentials not available in test env (`system_administrator` password unknown); super_admin transfer behaviour was inferred from code (`is_super_admin` check).
- The `admin` role maps to the seeded `admin` / `Admin@1234` user — this is the `require_admin` decorator's target role.
- Stock transfer creation currently mandates at least one linked Delivery Challan (DC invoice) — the auth gate was tested by observing 400 vs 403 responses.
- Test script is idempotent on re-runs: warehouses get created fresh each run; users already-existing get warehouse_id corrected; temporary reassignments are restored.
