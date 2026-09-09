# -*- coding: utf-8 -*-
"""
Warehouse Role-Matrix Test
==========================
Tests warehouse operations against the role matrix for:
  - super_admin (no WH assigned)
  - admin       (no WH assigned)
  - warehouse   user assigned to WH-A
  - warehouse   user assigned to WH-B
  - sales       (no WH assigned)
  - accountant  (no WH assigned)

Runs against a live backend at http://localhost:8000.
Prerequisites: backend running, admin/Admin@1234 seeded.
"""

import sys
import json
import requests
from datetime import date

BASE = "http://127.0.0.1:8000/api/v1"
ADMIN_USER = "admin"
ADMIN_PASS = "Admin@1234"

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"

results = []


# ── helpers ───────────────────────────────────────────────────────────────────

def login(username, password):
    for attempt in range(3):
        try:
            r = requests.post(f"{BASE}/auth/login",
                              json={"username": username, "password": password},
                              timeout=10)
            if r.status_code != 200:
                return None
            return r.json().get("access_token")
        except requests.exceptions.ConnectionError:
            if attempt == 2:
                raise
            import time; time.sleep(1)
    return None


def headers(token):
    return {"Authorization": f"Bearer {token}"}


def record(test_id, description, role, expected_status, actual_status, detail=""):
    outcome = PASS if actual_status == expected_status else FAIL
    results.append({
        "id": test_id,
        "description": description,
        "role": role,
        "expected": expected_status,
        "actual": actual_status,
        "outcome": outcome,
        "detail": detail,
    })
    symbol = "OK" if outcome == PASS else "XX"
    print(f"  [{symbol}] {test_id} | {role:20s} | {description[:55]:55s} | "
          f"exp={expected_status} got={actual_status}")


# ── setup ─────────────────────────────────────────────────────────────────────

print("\n=== SETUP ===")

admin_token = login(ADMIN_USER, ADMIN_PASS)
if not admin_token:
    print("FATAL: cannot log in as admin — is the backend running?")
    sys.exit(1)
print("  [OK] Admin login OK")


def admin_get(path, **kwargs):
    return requests.get(f"{BASE}{path}", headers=headers(admin_token), **kwargs)

def admin_post(path, body):
    return requests.post(f"{BASE}{path}", json=body, headers=headers(admin_token))

def admin_put(path, body):
    return requests.put(f"{BASE}{path}", json=body, headers=headers(admin_token))


# ── 1. ensure warehouses ──────────────────────────────────────────────────────

existing = admin_get("/warehouses/").json()
wh_list = existing if isinstance(existing, list) else existing.get("items", [])

def find_wh(code):
    return next((w for w in wh_list if w.get("code") == code), None)

wh_a = find_wh("WHTA")
wh_b = find_wh("WHTB")

if not wh_a:
    r = admin_post("/warehouses/", {
        "name": "Test Warehouse Alpha",
        "address": "100 Alpha Lane",
        "city": "Chennai",
        "state": "Tamil Nadu",
        "state_code": 33,
        "pincode": "600001",
        "is_active": True,
        "is_default": False,
    })
    if r.status_code == 201:
        wh_a = r.json()
        print(f"  [OK] Created WH-A  id={wh_a['id']}  code={wh_a.get('code')}")
    else:
        print(f"  [!] WH-A create failed: {r.status_code} {r.text[:120]}")
        sys.exit(1)
else:
    print(f"  [OK] WH-A already exists  id={wh_a['id']}  code={wh_a.get('code')}")

if not wh_b:
    r = admin_post("/warehouses/", {
        "name": "Test Warehouse Beta",
        "address": "200 Beta Road",
        "city": "Mumbai",
        "state": "Maharashtra",
        "state_code": 27,
        "pincode": "400001",
        "is_active": True,
        "is_default": False,
    })
    if r.status_code == 201:
        wh_b = r.json()
        print(f"  [OK] Created WH-B  id={wh_b['id']}  code={wh_b.get('code')}")
    else:
        print(f"  [!] WH-B create failed: {r.status_code} {r.text[:120]}")
        sys.exit(1)
else:
    print(f"  [OK] WH-B already exists  id={wh_b['id']}  code={wh_b.get('code')}")

WH_A_ID = wh_a["id"]
WH_B_ID = wh_b["id"]


# ── 2. ensure test users ──────────────────────────────────────────────────────

def ensure_user(username, role, warehouse_id, password="Test@1234!"):
    # check if exists
    r = admin_get(f"/users-admin/?search={username}")
    data = r.json()
    items = data.get("items", data) if isinstance(data, dict) else data
    found = next((u for u in (items if isinstance(items, list) else []) if u.get("username") == username), None)
    if found:
        # make sure warehouse_id is set correctly
        admin_put(f"/users-admin/{found['id']}", {"warehouse_id": warehouse_id})
        print(f"  [OK] User '{username}' already exists (id={found['id']}) — warehouse_id updated")
        return found["id"]
    r = admin_post("/users-admin/", {
        "username": username,
        "full_name": f"Test {username}",
        "email": f"{username}@test.erp",
        "password": password,
        "role": role,
        "warehouse_id": warehouse_id,
    })
    if r.status_code == 201:
        uid = r.json().get("id")
        print(f"  [OK] Created user '{username}' role={role} wh={warehouse_id} id={uid}")
        return uid
    else:
        print(f"  [!] Failed to create '{username}': {r.status_code} {r.text[:200]}")
        return None

WH_A_USER = "test_wh_alpha"
WH_B_USER = "test_wh_beta"
SALES_USER = "test_sales_nwh"
ACCT_USER  = "test_acct_nwh"
# NOTE: only super_admin can create admin users; use seeded 'admin' for admin tests

uid_wh_a  = ensure_user(WH_A_USER, "warehouse", WH_A_ID)
uid_wh_b  = ensure_user(WH_B_USER, "warehouse", WH_B_ID)
uid_sales = ensure_user(SALES_USER, "sales",     None)
uid_acct  = ensure_user(ACCT_USER,  "accountant", None)

if not all([uid_wh_a, uid_wh_b, uid_sales, uid_acct]):
    print("FATAL: some users could not be created — check above errors")
    sys.exit(1)

# ── 3. login all users ────────────────────────────────────────────────────────

tok_wh_a  = login(WH_A_USER,  "Test@1234!")
tok_wh_b  = login(WH_B_USER,  "Test@1234!")
tok_sales = login(SALES_USER, "Test@1234!")
tok_acct  = login(ACCT_USER,  "Test@1234!")
tok_admin = admin_token   # seeded admin — role=admin, no warehouse

failed_logins = [u for u, t in [(WH_A_USER, tok_wh_a), (WH_B_USER, tok_wh_b),
                                  (SALES_USER, tok_sales), (ACCT_USER, tok_acct)] if not t]
if failed_logins:
    print(f"FATAL: login failed for {failed_logins}")
    sys.exit(1)
print("  [OK] All test users authenticated")
print(f"  [NOTE] Using seeded 'admin' (role=admin, no WH) for admin tests")


# ── 4. helper to GET with a given token ──────────────────────────────────────

def get_as(token, path):
    return requests.get(f"{BASE}{path}", headers=headers(token))

def post_as(token, path, body):
    return requests.post(f"{BASE}{path}", json=body, headers=headers(token))


# =============================================================================
# TC-WH-01: Dashboard / Login — sidebar visibility inferred from role
# We check /warehouses/ (all-users) and /warehouses/stock/ageing (warehouse_ops)
# =============================================================================
print("\n=== TC-WH-01: Warehouse list (all authenticated users) ===")

for role, tok in [("admin",       tok_admin),
                  ("warehouse_A", tok_wh_a),
                  ("warehouse_B", tok_wh_b),
                  ("sales",       tok_sales),
                  ("accountant",  tok_acct)]:
    r = get_as(tok, "/warehouses/")
    record("WH-01", "List warehouses (all roles allowed)", role, 200, r.status_code)


# =============================================================================
# TC-WH-02: Stock view (all authenticated users)
# =============================================================================
print("\n=== TC-WH-02: Stock view (all authenticated users) ===")

for role, tok in [("admin",      tok_admin),
                  ("warehouse_A", tok_wh_a),
                  ("warehouse_B", tok_wh_b),
                  ("sales",      tok_sales),
                  ("accountant", tok_acct)]:
    r = get_as(tok, "/warehouses/stock")
    record("WH-02", "View stock (all roles allowed)", role, 200, r.status_code)


# =============================================================================
# TC-WH-03: Stock Ageing — only warehouse_ops (super_admin, admin, warehouse)
# =============================================================================
print("\n=== TC-WH-03: Stock Ageing (warehouse_ops only) ===")

for role, tok, exp in [("admin",       tok_admin,  200),
                       ("warehouse_A", tok_wh_a,   200),
                       ("warehouse_B", tok_wh_b,   200),
                       ("sales",       tok_sales,  403),
                       ("accountant",  tok_acct,   403)]:
    r = get_as(tok, "/warehouses/stock/ageing")
    record("WH-03", "Stock ageing (warehouse_ops gate)", role, exp, r.status_code)


# =============================================================================
# TC-WH-04: Create warehouse — admin only
# =============================================================================
print("\n=== TC-WH-04: Create warehouse (admin only) ===")

dummy_wh = {
    "name": "Dummy WH for role test",
    "address": "1 Test St",
    "city": "Delhi",
    "state": "Delhi",
    "state_code": 7,
    "pincode": "110001",
    "is_active": True,
    "is_default": False,
}

for role, tok, exp in [("admin",      tok_admin,      201),
                       ("warehouse_A", tok_wh_a,       403),
                       ("sales",      tok_sales,       403),
                       ("accountant", tok_acct,        403)]:
    r = post_as(tok, "/warehouses/", dummy_wh)
    detail = ""
    if r.status_code == 201:
        # clean up immediately to avoid polluting
        new_id = r.json().get("id")
        requests.put(f"{BASE}/warehouses/{new_id}",
                     json={"is_active": False},
                     headers=headers(tok_admin))
        detail = f"created id={new_id} (deactivated)"
    record("WH-04", "Create warehouse (admin gate)", role, exp, r.status_code, detail)


# =============================================================================
# PRE-TEST: Seed stock into WH_A so transfer business logic can proceed
# =============================================================================
print("\n=== PRE-TEST: Seed stock into WH-A ===")

today = str(date.today())

# Get any product id from the system
prod_r = admin_get("/products/?page_size=1")
prod_data = prod_r.json()
prod_items = prod_data.get("items", prod_data) if isinstance(prod_data, dict) else prod_data
test_product_id = prod_items[0]["id"] if prod_items else 1  # fallback to 1

seed_adj = {
    "warehouse_id": WH_A_ID,
    "product_id": test_product_id,
    "adjustment_type": "in",
    "quantity": "50.000",
    "reason": "role-matrix test seed",
    "adjustment_date": today,
}
seed_r = admin_post("/stock-adjustments/", seed_adj)
if seed_r.status_code == 201:
    print(f"  [OK] Seeded 50 units of product {test_product_id} into WH-A (id={WH_A_ID})")
else:
    print(f"  [WARN] Stock seed failed: {seed_r.status_code} {seed_r.text[:80]} — transfers may 400")


# =============================================================================
# TC-WH-05: Stock Transfer — warehouse-mapping guard (access control only)
# Strategy: auth gate checked first (403 = blocked), then business logic runs.
# We accept ANY non-403 for authorised roles.
# NOTE: admin role (not super_admin) without warehouse assignment gets 403 —
# this is a documented finding (F-WH-01): the transfer guard only exempts
# super_admin; admin is treated same as warehouse role re: WH mapping.
# =============================================================================
print("\n=== TC-WH-05: Create stock transfer ===")

# Get any product id from the system (just need a valid int for the schema)
prod_r = admin_get("/products/?page_size=1")
prod_data = prod_r.json()
prod_items = prod_data.get("items", prod_data) if isinstance(prod_data, dict) else prod_data
test_product_id = prod_items[0]["id"] if prod_items else 1  # fallback to 1

transfer_payload = {
    "source_warehouse_id": WH_A_ID,
    "destination_warehouse_id": WH_B_ID,
    "product_id": test_product_id,
    "quantity": "1.000",
    "transfer_date": today,
    "notes": "Role-matrix test transfer",
}

wrong_payload = {
    "source_warehouse_id": WH_B_ID,
    "destination_warehouse_id": WH_B_ID,
    "product_id": test_product_id,
    "quantity": "1.000",
    "transfer_date": today,
    "notes": "should fail - wrong WH for WH-A user",
}

created_transfer_id = None  # transfer whose dest = WH_B_ID, for TC-06

def record_auth(test_id, description, role, allow_bool, actual_status, detail=""):
    """allow_bool=True means authorised (any non-403 passes); False means expect 403."""
    if allow_bool:
        outcome = PASS if actual_status != 403 else FAIL
        expected_label = "not_403"
    else:
        outcome = PASS if actual_status == 403 else FAIL
        expected_label = "403"
    results.append({
        "id": test_id, "description": description, "role": role,
        "expected": expected_label, "actual": actual_status,
        "outcome": outcome, "detail": detail,
    })
    symbol = "OK" if outcome == PASS else "XX"
    print(f"  [{symbol}] {test_id} | {role:20s} | {description[:55]:55s} | "
          f"exp={expected_label} got={actual_status}")

# 5a: admin — FINDING F-WH-01: admin without WH is blocked (code only exempts super_admin)
# The transfer guard (_assert_user_can_transfer) checks is_super_admin() first,
# then falls through to the warehouse-mapping check. admin role != super_admin,
# so admin without warehouse_id gets 403. This differs from the role matrix intention
# (which shows admin as having broader transfer access). Recording actual behaviour.
r = post_as(tok_admin, "/stock-transfers/", transfer_payload)
admin_transfer_actual = r.status_code
# Record as FINDING: expected=not_403 per role-matrix intent, actual=403 per code
record("WH-05a", "Transfer create: admin (no WH) [FINDING F-WH-01]", "admin",
       "not_403", str(r.status_code),
       f"FINDING: admin role without WH gets 403 -- only super_admin exempt. "
       f"Role matrix shows admin can create transfers but code requires WH mapping.")
if r.status_code == 201:
    created_transfer_id = r.json().get("id")

# 5b: warehouse_A user (mapped to source WH_A) — authorised
r = post_as(tok_wh_a, "/stock-transfers/", transfer_payload)
record_auth("WH-05b", "Transfer create: WH-A user (source match)", "warehouse_A", True, r.status_code)
if r.status_code == 201 and not created_transfer_id:
    created_transfer_id = r.json().get("id")

# 5c: warehouse_B user (mapped to destination WH_B) — authorised
r = post_as(tok_wh_b, "/stock-transfers/", transfer_payload)
record_auth("WH-05c", "Transfer create: WH-B user (dest match)", "warehouse_B", True, r.status_code)
if r.status_code == 201 and not created_transfer_id:
    created_transfer_id = r.json().get("id")

# 5d: sales user (no warehouse) — blocked: 403
r = post_as(tok_sales, "/stock-transfers/", transfer_payload)
record_auth("WH-05d", "Transfer create: sales (no WH) -> 403", "sales", False, r.status_code)

# 5e: accountant (no warehouse) — blocked: 403
r = post_as(tok_acct, "/stock-transfers/", transfer_payload)
record_auth("WH-05e", "Transfer create: accountant (no WH) -> 403", "accountant", False, r.status_code)

# 5f: warehouse_A user, transfer between WH_B<->WH_B (user not involved) — blocked: 403
r = post_as(tok_wh_a, "/stock-transfers/", wrong_payload)
record_auth("WH-05f", "Transfer create: WH-A user, neither WH -> 403", "warehouse_A", False, r.status_code)


# =============================================================================
# TC-WH-06: DC Approve/Reject — destination WH guard
# We probe the guard using a non-existent dc_id=999999.
# Guard PASS  → response is NOT 403 (could be 400/404 — business logic ran).
# Guard BLOCK → response IS  403.
# For this test, we MUST use a transfer whose dest = WH_B_ID so the WH-B user
# is expected to be authorised. We create one now specifically for this.
# =============================================================================
print("\n=== TC-WH-06: Confirm/Reject DC (destination WH guard) ===")

# Strategy: use transfer 19 (dest=WH 8) from the existing system.
# Temporarily re-assign test_wh_beta to warehouse 8 so they ARE the dest user.
# After all guard tests, restore test_wh_beta to WH_B_ID.
fake_dc_id = 999999

# Find a usable existing transfer (any dest)
r = get_as(tok_admin, "/stock-transfers/?page_size=100")
t_items = r.json().get("items", [])
usable_transfer = None
for t in t_items:
    if t.get("destination_warehouse_id") and t["id"]:
        usable_transfer = t
        break  # just pick the first available

if usable_transfer:
    tid = usable_transfer["id"]
    dest_wh_id = usable_transfer["destination_warehouse_id"]
    print(f"  [OK] Using transfer id={tid} (dest=WH {dest_wh_id}) for DC guard tests")

    # Reassign test_wh_beta to dest_wh_id so they are the "destination user"
    admin_put(f"/users-admin/{uid_wh_b}", {"warehouse_id": dest_wh_id})
    # Re-login to get fresh token with updated WH mapping
    tok_wh_b_dc = login(WH_B_USER, "Test@1234!")
    print(f"  [OK] test_wh_beta temporarily reassigned to WH {dest_wh_id}")

    # 6a: WH-B user (now dest) — authorised
    r = post_as(tok_wh_b_dc, f"/stock-transfers/{tid}/confirm-dc", {"dc_id": fake_dc_id})
    record_auth("WH-06a", "Confirm DC: dest-WH user guard passes", "warehouse_B(dest)",
                True, r.status_code, f"http={r.status_code} wh={dest_wh_id}")

    # 6b: WH-A user (not dest) — blocked
    r = post_as(tok_wh_a, f"/stock-transfers/{tid}/confirm-dc", {"dc_id": fake_dc_id})
    record_auth("WH-06b", "Confirm DC: WH-A user (not dest) -> 403", "warehouse_A",
                False, r.status_code)

    # 6c: sales user (no WH) — blocked
    r = post_as(tok_sales, f"/stock-transfers/{tid}/confirm-dc", {"dc_id": fake_dc_id})
    record_auth("WH-06c", "Confirm DC: sales (no WH) -> 403", "sales", False, r.status_code)

    # 6d: admin (no WH) → 403 (code only exempts super_admin)
    r = post_as(tok_admin, f"/stock-transfers/{tid}/confirm-dc", {"dc_id": fake_dc_id})
    record_auth("WH-06d", "Confirm DC: admin (no WH) -> 403", "admin",
                False, r.status_code, f"http={r.status_code}")

    # 6e: WH-A user (not dest) — reject blocked
    r = post_as(tok_wh_a, f"/stock-transfers/{tid}/reject-dc",
                {"dc_id": fake_dc_id, "reason": "role test rejection"})
    record_auth("WH-06e", "Reject DC: WH-A user (not dest) -> 403", "warehouse_A",
                False, r.status_code)

    # 6f: WH-B user (dest) — reject authorised
    r = post_as(tok_wh_b_dc, f"/stock-transfers/{tid}/reject-dc",
                {"dc_id": fake_dc_id, "reason": "role test rejection"})
    record_auth("WH-06f", "Reject DC: dest-WH user guard passes", "warehouse_B(dest)",
                True, r.status_code, f"http={r.status_code}")

    # Restore test_wh_beta to WH_B_ID
    admin_put(f"/users-admin/{uid_wh_b}", {"warehouse_id": WH_B_ID})
    print(f"  [OK] test_wh_beta restored to WH_B_ID={WH_B_ID}")
else:
    print("  [SKIP] No usable transfer found — TC-WH-06 skipped")


# =============================================================================
# TC-WH-07: Stock Adjustment — warehouse_ops only
# Correct route: /stock-adjustments/  (prefix defined on adjustment_router)
# Use type="in" so no existing stock is required.
# =============================================================================
print("\n=== TC-WH-07: Stock Adjustment (warehouse_ops gate) ===")

# Get any product id
if not test_product_id:
    prod_r2 = admin_get("/products/?page_size=1")
    pd2 = prod_r2.json()
    pi2 = pd2.get("items", pd2) if isinstance(pd2, dict) else pd2
    test_product_id = pi2[0]["id"] if pi2 else None

if test_product_id:
    adj_payload = {
        "warehouse_id": WH_A_ID,
        "product_id": test_product_id,
        "adjustment_type": "in",    # "in" — no existing stock required
        "quantity": 0.001,
        "reason": "role-matrix test",
        "adjustment_date": today,
    }
    for role, tok, allow in [("admin",       tok_admin, True),
                              ("warehouse_A", tok_wh_a,  True),
                              ("sales",       tok_sales, False),
                              ("accountant",  tok_acct,  False)]:
        r = post_as(tok, "/stock-adjustments/", adj_payload)
        record_auth("WH-07", "Stock adjustment (warehouse_ops gate)", role, allow, r.status_code,
                    r.text[:80] if r.status_code not in (201, 403) else "")
else:
    print("  [SKIP] No products found — TC-WH-07 skipped")


# =============================================================================
# TC-WH-08: pending_for_me filter — confirms WH-scoped transfer list
# =============================================================================
print("\n=== TC-WH-08: pending_for_me=true filter ===")

# WH-B user should get transfers destined for WH-B
r_b = get_as(tok_wh_b, "/stock-transfers/?pending_for_me=true")
# WH-A user should get transfers destined for WH-A
r_a = get_as(tok_wh_a, "/stock-transfers/?pending_for_me=true")
# Sales user (no WH) should get empty list
r_s = get_as(tok_sales, "/stock-transfers/?pending_for_me=true")

for role, r, exp in [("warehouse_B", r_b, 200),
                     ("warehouse_A", r_a, 200),
                     ("sales",       r_s, 200)]:
    record("WH-08", "pending_for_me filter response", role, exp, r.status_code)

# additionally verify sales returns empty
sales_items = r_s.json().get("items", [])
if isinstance(r_s.json(), dict) and r_s.json().get("total", -1) == 0:
    record("WH-08x", "sales pending_for_me = empty (no WH)", "sales", 0,
           r_s.json().get("total", -1))
elif isinstance(r_s.json(), dict):
    record("WH-08x", "sales pending_for_me = empty (no WH)", "sales", 0,
           len(r_s.json().get("items", [])))


# =============================================================================
# RESULTS SUMMARY
# =============================================================================
print("\n" + "="*90)
print("RESULTS SUMMARY")
print("="*90)

total = len(results)
passed = sum(1 for r in results if r["outcome"] == PASS)
failed = sum(1 for r in results if r["outcome"] == FAIL)

print(f"\n{'ID':<8} {'Role':<20} {'Description':<55} {'Exp':<12} {'Got':<12} {'Outcome'}")
print("-"*120)
for r in results:
    marker = "OK" if r["outcome"] == PASS else "XX"
    print(f"[{marker}] {r['id']:<6} {r['role']:<20} {r['description']:<55} "
          f"{str(r['expected']):<12} {str(r['actual']):<12} {r['outcome']}"
          + (f"  ← {r['detail']}" if r["detail"] else ""))

print(f"\nTotal: {total}  PASS: {passed}  FAIL: {failed}")
print("="*90)

# ── output JSON for the doc writer ──
print("\n\nJSON_RESULTS_BEGIN")
print(json.dumps({"wh_a_id": WH_A_ID, "wh_b_id": WH_B_ID, "results": results}, indent=2))
print("JSON_RESULTS_END")
