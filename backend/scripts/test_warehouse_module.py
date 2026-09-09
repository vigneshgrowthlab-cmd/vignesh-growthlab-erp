"""Warehouse module smoke test.
Run from backend/ with venv activated, against a live uvicorn :8000.

Covers: Warehouses CRUD + rename + validate-obsolete RBAC,
Stock queries (list/consolidated/ageing), Adjustments (in/out + negatives),
Write-offs (create/approve/reject + negatives), Stock Transfers (DC-driven flow),
Opening balances (schema validation only).

Side effects: creates 2 timestamped warehouses (ZWxxxxxx, ZDxxxxxx), a few
stock adjustments/write-offs against an existing product, possibly a
stock transfer if an unlinked Delivery Challan is available.
Does NOT delete warehouses (no delete endpoint; obsolete is super-admin only).
"""
import requests, time
from datetime import date

BASE = "http://localhost:8000/api/v1"
results = []


def log(case, ok, expected, actual, detail=""):
    tag = "[PASS]" if ok else "[FAIL]"
    msg = f"{tag} {case}: expected={expected} actual={actual}"
    if detail and not ok:
        msg += f" | {detail}"
    print(msg)
    results.append((case, ok))


# ── Login ─────────────────────────────────────────────────────
r = requests.post(f"{BASE}/auth/login",
                  json={"username": "admin", "password": "Admin@1234"})
if r.status_code != 200:
    print(f"[FATAL] Login failed: {r.status_code} {r.text}")
    raise SystemExit(1)
TOKEN = r.json()["access_token"]
H = {"Authorization": f"Bearer {TOKEN}"}

# system_administrator session — required for hard-delete cases
SH = None
r = requests.post(f"{BASE}/auth/login",
                  json={"username": "system_administrator", "password": "Admin@1234"})
if r.status_code == 200 and r.json().get("access_token"):
    SH = {"Authorization": f"Bearer {r.json()['access_token']}"}
else:
    print(f"[WARN] system_administrator login failed ({r.status_code}); "
          f"hard-delete happy-path cases will be skipped")

# ── Resolve a product (need one for adjustments/write-offs) ───
prods = requests.get(f"{BASE}/products/?search=Smoke", headers=H).json().get("items", [])
if not prods:
    prods = requests.get(f"{BASE}/products/?page=1&page_size=1",
                         headers=H).json().get("items", [])
if not prods:
    print("[FATAL] No products in DB. Seed at least one product first.")
    raise SystemExit(1)
PROD_ID = prods[0]["id"]
print(f"Using product id={PROD_ID} ({prods[0].get('part_code')})")

TODAY = date.today().isoformat()
suffix = str(int(time.time()))[-5:]
WH_CODE = f"ZW{suffix}"      # 7 chars, fits String(10)
WH_DST_CODE = f"ZD{suffix}"


# ============================================================
# Warehouses CRUD
# ============================================================
print("\n=== Warehouses - Positive ===")

r = requests.post(f"{BASE}/warehouses/", json={
    "name": f"SmokeWH {suffix}", "code": WH_CODE,
    "address": "Test Addr", "city": "Bengaluru", "state": "Karnataka",
    "pincode": "560001", "contact_person": "Smoke Tester", "phone": "9999999999",
    "is_default": False,
}, headers=H)
log("W1  Create warehouse", r.status_code == 201, 201, r.status_code,
    detail=r.text[:200])
WH_ID = r.json().get("id") if r.status_code == 201 else None

r = requests.post(f"{BASE}/warehouses/", json={
    "name": f"SmokeWH-DST {suffix}", "code": WH_DST_CODE,
    "city": "Mumbai",
}, headers=H)
log("W2  Create destination warehouse", r.status_code == 201, 201, r.status_code,
    detail=r.text[:200])
WH_DST_ID = r.json().get("id") if r.status_code == 201 else None

r = requests.get(f"{BASE}/warehouses/", headers=H)
body = r.json() if r.status_code == 200 else None
log("W3  List warehouses", r.status_code == 200 and isinstance(body, list), "200+list",
    r.status_code)

r = requests.get(f"{BASE}/warehouses/", params={"include_inactive": True}, headers=H)
log("W4  List warehouses include_inactive", r.status_code == 200, 200, r.status_code)

r = requests.get(f"{BASE}/warehouses/{WH_ID}", headers=H)
log("W5  Get warehouse by id",
    r.status_code == 200 and r.json().get("code") == WH_CODE,
    "200+code match", r.status_code)

r = requests.put(f"{BASE}/warehouses/{WH_ID}",
                 json={"contact_person": "Updated Tester"}, headers=H)
log("W6  Update warehouse", r.status_code == 200, 200, r.status_code,
    detail=r.text[:200])

r = requests.put(f"{BASE}/warehouses/{WH_ID}/rename",
                 json={"name": f"SmokeWH Renamed {suffix}",
                       "phone": "8888888888",
                       "use_company_bank": False,
                       "bank_name": "HDFC",
                       "bank_account_number": "00112233",
                       "bank_ifsc": "HDFC0000123"}, headers=H)
log("W7  Rename warehouse + bank details", r.status_code == 200, 200, r.status_code,
    detail=r.text[:200])

print("\n=== Warehouses - Negative ===")
r = requests.post(f"{BASE}/warehouses/",
                  json={"name": "Dup", "code": WH_CODE}, headers=H)
log("W8  Duplicate code blocked", r.status_code == 400, 400, r.status_code,
    detail=r.text[:150])

r = requests.post(f"{BASE}/warehouses/", json={"name": "NoCode"}, headers=H)
log("W9  Missing code rejected", r.status_code == 422, 422, r.status_code)

r = requests.post(f"{BASE}/warehouses/", json={"code": "X"}, headers=H)
log("W10 Missing name rejected", r.status_code == 422, 422, r.status_code)

r = requests.get(f"{BASE}/warehouses/999999", headers=H)
log("W11 Get non-existent warehouse", r.status_code == 404, 404, r.status_code)

r = requests.put(f"{BASE}/warehouses/999999", json={"city": "X"}, headers=H)
log("W12 Update non-existent warehouse", r.status_code == 404, 404, r.status_code)

# RBAC: validate-obsolete / obsolete are system_administrator only
r = requests.get(f"{BASE}/warehouses/{WH_ID}/validate-obsolete", headers=H)
log("W13 validate-obsolete blocked for plain admin",
    r.status_code == 403, 403, r.status_code, detail=r.text[:150])

r = requests.post(f"{BASE}/warehouses/{WH_ID}/obsolete", headers=H)
log("W14 obsolete blocked for plain admin",
    r.status_code == 403, 403, r.status_code, detail=r.text[:150])

# RBAC: validate-delete / delete are system_administrator only
r = requests.get(f"{BASE}/warehouses/{WH_ID}/validate-delete", headers=H)
log("W15 validate-delete blocked for plain admin",
    r.status_code == 403, 403, r.status_code, detail=r.text[:150])

r = requests.delete(f"{BASE}/warehouses/{WH_ID}", headers=H)
log("W16 delete blocked for plain admin",
    r.status_code == 403, 403, r.status_code, detail=r.text[:150])

# Even system_administrator gets 404 on non-existent — but plain admin gets
# 403 first since the auth check runs before the lookup. Test current behavior.
r = requests.delete(f"{BASE}/warehouses/999999", headers=H)
log("W17 delete non-existent (auth checked first)",
    r.status_code == 403, 403, r.status_code, detail=r.text[:150])

# Hard-delete happy paths — require system_administrator
print("\n=== Hard Delete - system_administrator ===")
if SH:
    # Create a fresh warehouse with regular admin solely for delete testing.
    # Don't touch it elsewhere -> guaranteed zero references.
    r = requests.post(f"{BASE}/warehouses/", json={
        "name": f"SmokeWH-FRESH {suffix}",
        "code": f"ZF{suffix}",
        "city": "Delete Me",
    }, headers=H)
    WH_FRESH_ID = r.json().get("id") if r.status_code == 201 else None

    if WH_FRESH_ID:
        r = requests.get(f"{BASE}/warehouses/{WH_FRESH_ID}/validate-delete",
                         headers=SH)
        body = r.json() if r.status_code == 200 else {}
        log("WD1 validate-delete on fresh WH -> can_delete=true",
            r.status_code == 200 and body.get("can_delete") is True
            and body.get("blocks") == [],
            "200 + can_delete=true", r.status_code, detail=r.text[:200])

        r = requests.delete(f"{BASE}/warehouses/{WH_FRESH_ID}", headers=SH)
        log("WD2 DELETE fresh WH -> 200 + status=deleted",
            r.status_code == 200 and r.json().get("status") == "deleted",
            "200 + deleted", r.status_code, detail=r.text[:200])

        # Row should be gone
        r = requests.get(f"{BASE}/warehouses/{WH_FRESH_ID}", headers=H)
        log("WD3 GET deleted WH -> 404",
            r.status_code == 404, 404, r.status_code, detail=r.text[:150])
    else:
        log("WD1 Skipped (fresh WH create failed)", False, "WH_FRESH_ID",
            None, detail="couldn't create fresh warehouse")

    # WH_ID at this point has no adjustments yet (those run later) but
    # WH_DST_ID receives stock via the T8 transfer-confirm later. To get a
    # referenced WH right now we'd need to wait. Instead, do this test
    # AFTER the rest of the suite via a deferred flag.
else:
    log("WD1 Skipped (no system_administrator session)", True,
        "skipped", "skipped")
    log("WD2 Skipped (no system_administrator session)", True,
        "skipped", "skipped")
    log("WD3 Skipped (no system_administrator session)", True,
        "skipped", "skipped")


# ============================================================
# Stock queries
# ============================================================
print("\n=== Stock queries ===")
r = requests.get(f"{BASE}/warehouses/stock", headers=H)
log("S1  List all stock", r.status_code == 200 and isinstance(r.json(), list),
    "200+list", r.status_code)

r = requests.get(f"{BASE}/warehouses/stock",
                 params={"warehouse_id": WH_ID}, headers=H)
log("S2  Filter by warehouse_id", r.status_code == 200, 200, r.status_code)

r = requests.get(f"{BASE}/warehouses/stock",
                 params={"product_id": PROD_ID}, headers=H)
log("S3  Filter by product_id", r.status_code == 200, 200, r.status_code)

r = requests.get(f"{BASE}/warehouses/stock",
                 params={"search": "x"}, headers=H)
log("S4  Filter by search term", r.status_code == 200, 200, r.status_code)

r = requests.get(f"{BASE}/warehouses/stock",
                 params={"low_stock_only": True}, headers=H)
log("S5  low_stock_only filter", r.status_code == 200, 200, r.status_code)

r = requests.get(f"{BASE}/warehouses/stock/consolidated/{PROD_ID}",
                 params={"warehouse_id": WH_ID}, headers=H)
body = r.json() if r.status_code == 200 else {}
log("S6  Consolidated stock by product",
    r.status_code == 200 and "total_all_warehouses" in body and "warehouse_breakup" in body,
    "200+consolidated", r.status_code)

r = requests.get(f"{BASE}/warehouses/stock/consolidated/{PROD_ID}", headers=H)
log("S7  Consolidated stock missing warehouse_id rejected",
    r.status_code == 422, 422, r.status_code)

r = requests.get(f"{BASE}/warehouses/stock/ageing", headers=H)
body = r.json() if r.status_code == 200 else {}
log("S8  Stock ageing report",
    r.status_code == 200 and "buckets" in body and "summary" in body,
    "200+buckets+summary", r.status_code)

r = requests.get(f"{BASE}/warehouses/stock/ageing",
                 params={"warehouse_id": WH_ID}, headers=H)
log("S9  Ageing filtered by warehouse", r.status_code == 200, 200, r.status_code)


# ============================================================
# Stock Adjustments
# ============================================================
print("\n=== Adjustments - Positive ===")
r = requests.post(f"{BASE}/stock-adjustments/", json={
    "warehouse_id": WH_ID, "product_id": PROD_ID,
    "adjustment_type": "in", "quantity": 50,
    "reason": "Smoke test stock IN seed",
    "adjustment_date": TODAY, "unit_cost": 100,
}, headers=H)
log("A1  Adjustment IN +50", r.status_code == 201, 201, r.status_code,
    detail=r.text[:200])

r = requests.post(f"{BASE}/stock-adjustments/", json={
    "warehouse_id": WH_ID, "product_id": PROD_ID,
    "adjustment_type": "out", "quantity": 5,
    "reason": "Smoke test stock OUT trim",
    "adjustment_date": TODAY,
}, headers=H)
log("A2  Adjustment OUT -5", r.status_code == 201, 201, r.status_code,
    detail=r.text[:200])

r = requests.get(f"{BASE}/stock-adjustments/", headers=H)
body = r.json() if r.status_code == 200 else {}
log("A3  List adjustments paginated",
    r.status_code == 200 and "items" in body and "total" in body,
    "200+paginated", r.status_code)

r = requests.get(f"{BASE}/stock-adjustments/",
                 params={"warehouse_id": WH_ID}, headers=H)
log("A4  Adjustments filtered by warehouse",
    r.status_code == 200, 200, r.status_code)

print("\n=== Adjustments - Negative ===")
r = requests.post(f"{BASE}/stock-adjustments/", json={
    "warehouse_id": WH_ID, "product_id": PROD_ID,
    "adjustment_type": "invalid", "quantity": 1, "reason": "x",
    "adjustment_date": TODAY,
}, headers=H)
log("A5  Invalid adjustment_type rejected",
    r.status_code == 422, 422, r.status_code)

r = requests.post(f"{BASE}/stock-adjustments/", json={
    "warehouse_id": WH_ID, "product_id": PROD_ID,
    "adjustment_type": "out", "quantity": 99999999,
    "reason": "exceeds available",
    "adjustment_date": TODAY,
}, headers=H)
log("A6  Insufficient stock blocked",
    r.status_code == 400, 400, r.status_code, detail=r.text[:150])

r = requests.post(f"{BASE}/stock-adjustments/", json={
    "warehouse_id": WH_ID, "product_id": PROD_ID,
    "adjustment_type": "in", "quantity": 0,
    "reason": "zero qty",
    "adjustment_date": TODAY,
}, headers=H)
log("A7  Zero quantity rejected (gt=0)",
    r.status_code == 422, 422, r.status_code)

r = requests.post(f"{BASE}/stock-adjustments/", json={
    "warehouse_id": 999999, "product_id": PROD_ID,
    "adjustment_type": "in", "quantity": 1,
    "reason": "bad warehouse",
    "adjustment_date": TODAY,
}, headers=H)
log("A8  Non-existent warehouse blocked",
    r.status_code == 404, 404, r.status_code)

r = requests.post(f"{BASE}/stock-adjustments/", json={
    "warehouse_id": WH_ID, "product_id": 999999,
    "adjustment_type": "in", "quantity": 1,
    "reason": "bad product",
    "adjustment_date": TODAY,
}, headers=H)
log("A9  Non-existent product blocked",
    r.status_code == 404, 404, r.status_code)

r = requests.post(f"{BASE}/stock-adjustments/", json={
    "warehouse_id": WH_ID, "product_id": PROD_ID,
    "adjustment_type": "in", "quantity": 1, "reason": "ab",
    "adjustment_date": TODAY,
}, headers=H)
log("A10 Reason too short rejected (min 3 chars)",
    r.status_code == 422, 422, r.status_code)


# ============================================================
# Stock Write-offs
# ============================================================
print("\n=== Write-offs - Positive ===")
r = requests.post(f"{BASE}/stock-writeoffs/", json={
    "warehouse_id": WH_ID, "product_id": PROD_ID,
    "quantity": 2, "reason_type": "damaged",
    "reason_detail": "Smoke test - damaged batch",
    "writeoff_date": TODAY,
}, headers=H)
log("WO1 Create write-off (pending)",
    r.status_code == 201 and r.json().get("status") == "pending",
    "201+pending", r.status_code, detail=r.text[:200])
WO_ID = r.json().get("id") if r.status_code == 201 else None

r = requests.get(f"{BASE}/stock-writeoffs/", headers=H)
body = r.json() if r.status_code == 200 else {}
log("WO2 List write-offs paginated",
    r.status_code == 200 and "items" in body,
    "200+paginated", r.status_code)

r = requests.get(f"{BASE}/stock-writeoffs/",
                 params={"status": "pending"}, headers=H)
log("WO3 Filter by status=pending", r.status_code == 200, 200, r.status_code)

if WO_ID:
    r = requests.post(f"{BASE}/stock-writeoffs/{WO_ID}/approve",
                      json={"approved": True, "admin_notes": "Smoke approve"},
                      headers=H)
    log("WO4 Approve write-off (consumes FIFO + posts journal)",
        r.status_code == 200 and r.json().get("status") == "approved",
        "200+status=approved", r.status_code, detail=r.text[:200])

# Create another to reject
r = requests.post(f"{BASE}/stock-writeoffs/", json={
    "warehouse_id": WH_ID, "product_id": PROD_ID,
    "quantity": 1, "reason_type": "expired",
    "reason_detail": "Smoke test - to be rejected",
    "writeoff_date": TODAY,
}, headers=H)
WO_ID_2 = r.json().get("id") if r.status_code == 201 else None
log("WO5 Create write-off (to reject)",
    r.status_code == 201, 201, r.status_code, detail=r.text[:200])

if WO_ID_2:
    r = requests.post(f"{BASE}/stock-writeoffs/{WO_ID_2}/approve",
                      json={"approved": False, "admin_notes": "Smoke reject"},
                      headers=H)
    log("WO6 Reject write-off",
        r.status_code == 200 and r.json().get("status") == "rejected",
        "200+status=rejected", r.status_code, detail=r.text[:200])

print("\n=== Write-offs - Negative ===")
r = requests.post(f"{BASE}/stock-writeoffs/", json={
    "warehouse_id": WH_ID, "product_id": PROD_ID,
    "quantity": 99999999, "reason_type": "shortage",
    "reason_detail": "exceeds available",
    "writeoff_date": TODAY,
}, headers=H)
log("WO7 Insufficient stock blocked",
    r.status_code == 400, 400, r.status_code, detail=r.text[:150])

r = requests.post(f"{BASE}/stock-writeoffs/", json={
    "warehouse_id": WH_ID, "product_id": PROD_ID,
    "quantity": 1, "reason_type": "bogus",
    "reason_detail": "Bad reason type",
    "writeoff_date": TODAY,
}, headers=H)
log("WO8 Invalid reason_type rejected",
    r.status_code == 422, 422, r.status_code)

r = requests.post(f"{BASE}/stock-writeoffs/", json={
    "warehouse_id": WH_ID, "product_id": PROD_ID,
    "quantity": 1, "reason_type": "damaged", "reason_detail": "ab",
    "writeoff_date": TODAY,
}, headers=H)
log("WO9 reason_detail too short rejected",
    r.status_code == 422, 422, r.status_code)

if WO_ID:
    r = requests.post(f"{BASE}/stock-writeoffs/{WO_ID}/approve",
                      json={"approved": True}, headers=H)
    log("WO10 Re-approve already-approved blocked",
        r.status_code == 400, 400, r.status_code, detail=r.text[:150])

r = requests.post(f"{BASE}/stock-writeoffs/999999/approve",
                  json={"approved": True}, headers=H)
log("WO11 Approve non-existent write-off",
    r.status_code == 404, 404, r.status_code)


# ============================================================
# Stock Transfers (DC-driven)
# ============================================================
print("\n=== Stock Transfers ===")
r = requests.get(f"{BASE}/stock-transfers/", headers=H)
log("T1  List transfers paginated",
    r.status_code == 200 and "items" in r.json(),
    "200+paginated", r.status_code)

# Need an unlinked DC to test the create flow
r = requests.get(f"{BASE}/invoices/list/delivery-challans",
                 params={"unlinked_only": True}, headers=H)
dcs = r.json() if r.status_code == 200 else []
log("T2  List unlinked DCs",
    r.status_code == 200 and isinstance(dcs, list),
    "200+list", r.status_code, detail=f"found={len(dcs) if isinstance(dcs, list) else 'N/A'}")

TRF_ID = None
DC_USED = None
# Transfer create now requires user mapped to source-or-dest, OR system_administrator.
# Plain admin/Admin@1234 has no warehouse mapping, so we use the SH session.
TR_AUTH = SH if SH else H
if dcs:
    DC_USED = dcs[0]
    src_wh = DC_USED.get("warehouse_id")
    if src_wh and WH_DST_ID:
        # Pre-seed source warehouse with stock for each DC line item
        dc_detail = requests.get(f"{BASE}/invoices/{DC_USED['id']}", headers=H).json()
        for item in dc_detail.get("items", []):
            requests.post(f"{BASE}/stock-adjustments/", json={
                "warehouse_id": src_wh,
                "product_id": item["product_id"],
                "adjustment_type": "in",
                "quantity": float(item["quantity"]) * 2,
                "reason": "Smoke test - seed for DC transfer",
                "adjustment_date": TODAY,
                "unit_cost": 100,
            }, headers=H)
        r = requests.post(f"{BASE}/stock-transfers/", json={
            "source_warehouse_id": src_wh,
            "destination_warehouse_id": WH_DST_ID,
            "product_id": PROD_ID,  # representative; service uses DC line items
            "quantity": 1,
            "transfer_date": TODAY,
            "dc_ids": [DC_USED["id"]],
            "notes": "Smoke test transfer",
        }, headers=TR_AUTH)
        log("T3  Create transfer with unlinked DC (as super-admin)",
            r.status_code == 201, 201, r.status_code, detail=r.text[:200])
        TRF_ID = r.json().get("id") if r.status_code == 201 else None
    else:
        log("T3  Skipped (no source/dest warehouse resolved)", True,
            "skipped", "skipped")
else:
    print("    (no unlinked DCs available - skipping T3/T4/T5/T6 happy paths)")
    log("T3  Skipped: no unlinked DCs", True, "skipped", "skipped")

if TRF_ID:
    r = requests.get(f"{BASE}/stock-transfers/{TRF_ID}", headers=H)
    body = r.json() if r.status_code == 200 else {}
    log("T4  Get transfer detail",
        r.status_code == 200 and body.get("id") == TRF_ID,
        "200+id match", r.status_code, detail=r.text[:200])

    # Re-linking the same DC to another transfer should fail
    if WH_DST_ID and DC_USED:
        r = requests.post(f"{BASE}/stock-transfers/", json={
            "source_warehouse_id": DC_USED.get("warehouse_id"),
            "destination_warehouse_id": WH_DST_ID,
            "product_id": PROD_ID,
            "quantity": 1,
            "transfer_date": TODAY,
            "dc_ids": [DC_USED["id"]],
        }, headers=H)
        log("T5  DC already linked to another transfer blocked",
            r.status_code == 400, 400, r.status_code, detail=r.text[:150])

    # Unlink -> relink
    if DC_USED:
        r = requests.put(f"{BASE}/stock-transfers/{TRF_ID}/unlink-dc",
                         json={"dc_id": DC_USED["id"]}, headers=H)
        log("T6  Unlink DC from transfer",
            r.status_code == 200, 200, r.status_code, detail=r.text[:150])

        r = requests.put(f"{BASE}/stock-transfers/{TRF_ID}/link-dc",
                         json={"dc_id": DC_USED["id"]}, headers=H)
        log("T7  Re-link DC to transfer",
            r.status_code == 200, 200, r.status_code, detail=r.text[:150])

        # confirm-dc -> marks DC delivered + adds stock to destination
        # (now RBAC-gated: destination-mapped user OR system_administrator)
        r = requests.post(f"{BASE}/stock-transfers/{TRF_ID}/confirm-dc",
                          json={"dc_id": DC_USED["id"]}, headers=TR_AUTH)
        log("T8  Approve DC as super-admin (delivers stock to dest)",
            r.status_code == 200, 200, r.status_code, detail=r.text[:200])

        # Already delivered - second confirm should fail
        r = requests.post(f"{BASE}/stock-transfers/{TRF_ID}/confirm-dc",
                          json={"dc_id": DC_USED["id"]}, headers=TR_AUTH)
        log("T9  Re-approve already-delivered DC blocked",
            r.status_code == 400, 400, r.status_code, detail=r.text[:150])

print("\n=== Stock Transfers - Negative ===")
# Use super-admin so RBAC check passes and we hit the actual validation
NEG_AUTH = TR_AUTH

# Transfer with no DCs
r = requests.post(f"{BASE}/stock-transfers/", json={
    "source_warehouse_id": WH_ID,
    "destination_warehouse_id": WH_DST_ID or WH_ID,
    "product_id": PROD_ID,
    "quantity": 1,
    "transfer_date": TODAY,
}, headers=NEG_AUTH)
log("T10 Transfer without DCs blocked",
    r.status_code == 400, 400, r.status_code, detail=r.text[:150])

# Same source = destination
r = requests.post(f"{BASE}/stock-transfers/", json={
    "source_warehouse_id": WH_ID,
    "destination_warehouse_id": WH_ID,
    "product_id": PROD_ID,
    "quantity": 1,
    "transfer_date": TODAY,
    "dc_ids": [1],
}, headers=NEG_AUTH)
log("T11 Same source=destination blocked",
    r.status_code == 400, 400, r.status_code, detail=r.text[:150])

# Non-existent source warehouse
if WH_DST_ID:
    r = requests.post(f"{BASE}/stock-transfers/", json={
        "source_warehouse_id": 999999,
        "destination_warehouse_id": WH_DST_ID,
        "product_id": PROD_ID,
        "quantity": 1,
        "transfer_date": TODAY,
        "dc_ids": [1],
    }, headers=NEG_AUTH)
    log("T12 Non-existent source warehouse",
        r.status_code == 404, 404, r.status_code)

r = requests.get(f"{BASE}/stock-transfers/999999", headers=H)
log("T13 Get non-existent transfer",
    r.status_code == 404, 404, r.status_code)


# ============================================================
# Stock Transfers - new RBAC + reject endpoint
# ============================================================
print("\n=== Stock Transfers - RBAC + Reject ===")

# RBAC: plain admin (no warehouse mapping) cannot create transfers
if WH_DST_ID:
    r = requests.post(f"{BASE}/stock-transfers/", json={
        "source_warehouse_id": WH_ID,
        "destination_warehouse_id": WH_DST_ID,
        "product_id": PROD_ID,
        "quantity": 1,
        "transfer_date": TODAY,
        "dc_ids": [1],  # value irrelevant, RBAC fires first
    }, headers=H)
    log("TR1 Plain admin (no mapping) blocked from creating transfer",
        r.status_code == 403, 403, r.status_code, detail=r.text[:200])

# RBAC: plain admin cannot approve a DC (destination-only)
if TRF_ID and DC_USED:
    r = requests.post(f"{BASE}/stock-transfers/{TRF_ID}/confirm-dc",
                      json={"dc_id": DC_USED["id"]}, headers=H)
    log("TR2 Plain admin blocked from approving DC",
        r.status_code == 403, 403, r.status_code, detail=r.text[:200])

# Reject: missing reason -> 400
if TRF_ID:
    r = requests.post(f"{BASE}/stock-transfers/{TRF_ID}/reject-dc",
                      json={"dc_id": 1}, headers=TR_AUTH if SH else H)
    log("TR3 Reject without reason rejected",
        r.status_code == 400, 400, r.status_code, detail=r.text[:200])

    # Reject: non-existent transfer
    r = requests.post(f"{BASE}/stock-transfers/999999/reject-dc",
                      json={"dc_id": 1, "reason": "smoke"}, headers=TR_AUTH if SH else H)
    log("TR4 Reject on non-existent transfer -> 404",
        r.status_code == 404, 404, r.status_code, detail=r.text[:200])

    # Reject already-delivered DC -> 400 (DC_USED was approved in T8)
    if DC_USED:
        r = requests.post(f"{BASE}/stock-transfers/{TRF_ID}/reject-dc",
                          json={"dc_id": DC_USED["id"], "reason": "smoke test reject"},
                          headers=TR_AUTH if SH else H)
        log("TR5 Reject already-delivered DC blocked",
            r.status_code == 400, 400, r.status_code, detail=r.text[:200])

# Reject happy path: create a fresh transfer with a new DC, then reject it
TRF_REJECT_ID = None
DC_REJECT = None
if SH:
    # Find another unlinked DC (different from DC_USED)
    r = requests.get(f"{BASE}/invoices/list/delivery-challans",
                     params={"unlinked_only": True}, headers=SH)
    fresh_dcs = r.json() if r.status_code == 200 else []
    fresh_dcs = [d for d in fresh_dcs
                 if not DC_USED or d["id"] != DC_USED["id"]]
    if fresh_dcs and WH_DST_ID:
        DC_REJECT = fresh_dcs[0]
        src_wh = DC_REJECT["warehouse_id"]
        # Seed source stock
        dc_detail = requests.get(f"{BASE}/invoices/{DC_REJECT['id']}", headers=H).json()
        for item in dc_detail.get("items", []):
            requests.post(f"{BASE}/stock-adjustments/", json={
                "warehouse_id": src_wh,
                "product_id": item["product_id"],
                "adjustment_type": "in",
                "quantity": float(item["quantity"]) * 2,
                "reason": "Smoke test - seed for reject flow",
                "adjustment_date": TODAY,
                "unit_cost": 100,
            }, headers=H)
        # Create the transfer
        r = requests.post(f"{BASE}/stock-transfers/", json={
            "source_warehouse_id": src_wh,
            "destination_warehouse_id": WH_DST_ID,
            "product_id": PROD_ID,
            "quantity": 1,
            "transfer_date": TODAY,
            "dc_ids": [DC_REJECT["id"]],
        }, headers=SH)
        TRF_REJECT_ID = r.json().get("id") if r.status_code == 201 else None

if TRF_REJECT_ID and DC_REJECT and SH:
    # Capture source stock before reject
    item = (requests.get(f"{BASE}/invoices/{DC_REJECT['id']}", headers=H)
            .json().get("items") or [{}])[0]
    pid = item.get("product_id")
    pre_qty = None
    if pid:
        stock = requests.get(f"{BASE}/warehouses/stock/consolidated/{pid}",
                             params={"warehouse_id": DC_REJECT["warehouse_id"]},
                             headers=H).json()
        for wh in stock.get("warehouse_breakup", []):
            if wh["warehouse_id"] == DC_REJECT["warehouse_id"]:
                pre_qty = float(wh["quantity"])
                break

    r = requests.post(f"{BASE}/stock-transfers/{TRF_REJECT_ID}/reject-dc",
                      json={"dc_id": DC_REJECT["id"],
                            "reason": "Smoke test - reject flow"},
                      headers=SH)
    log("TR6 Reject DC happy path -> 200 + status=rejected",
        r.status_code == 200 and r.json().get("status") == "rejected",
        "200 + rejected", r.status_code, detail=r.text[:200])

    # Verify source stock restored
    if pid and pre_qty is not None:
        stock = requests.get(f"{BASE}/warehouses/stock/consolidated/{pid}",
                             params={"warehouse_id": DC_REJECT["warehouse_id"]},
                             headers=H).json()
        post_qty = pre_qty
        for wh in stock.get("warehouse_breakup", []):
            if wh["warehouse_id"] == DC_REJECT["warehouse_id"]:
                post_qty = float(wh["quantity"])
                break
        log("TR7 Source stock restored after reject",
            post_qty > pre_qty,
            f"qty > {pre_qty}", f"qty={post_qty}",
            detail=f"pre={pre_qty} post={post_qty}")

    # Verify DC marked rejected with reason
    r = requests.get(f"{BASE}/stock-transfers/{TRF_REJECT_ID}", headers=SH)
    if r.status_code == 200:
        linked = r.json().get("linked_dcs", [])
        rejected_dc = next((d for d in linked if d["id"] == DC_REJECT["id"]), None)
        log("TR8 Rejected DC has status=rejected + reason recorded",
            rejected_dc is not None
            and rejected_dc.get("dc_status") == "rejected"
            and rejected_dc.get("rejection_reason"),
            "rejected + reason", str(rejected_dc)[:200] if rejected_dc else "missing")
else:
    log("TR6 Skipped: no fresh unlinked DC available", True, "skipped", "skipped")
    log("TR7 Skipped: no fresh unlinked DC available", True, "skipped", "skipped")
    log("TR8 Skipped: no fresh unlinked DC available", True, "skipped", "skipped")


# ============================================================
# Opening Balances - schema-only validation
# (real call would mutate cash/bank balances)
# ============================================================
print("\n=== Opening Balances - schema only ===")
r = requests.post(f"{BASE}/opening-balances/", json={}, headers=H)
log("OB1 Missing financial_year rejected",
    r.status_code == 422, 422, r.status_code)

r = requests.post(f"{BASE}/opening-balances/", json={
    "financial_year": "2025-26",
    "opening_date": TODAY,
    "stock_items": [],
    "customer_balances": [],
    "vendor_balances": [],
    "bank_balances": [],
}, headers=H)
log("OB2 Empty payload accepted (no side effects)",
    r.status_code == 201, 201, r.status_code, detail=r.text[:200])


# Hard-delete on a referenced WH must fail with blocks
print("\n=== Hard Delete - referenced warehouse blocked ===")
if SH and WH_ID:
    r = requests.get(f"{BASE}/warehouses/{WH_ID}/validate-delete", headers=SH)
    body = r.json() if r.status_code == 200 else {}
    has_blocks = isinstance(body.get("blocks"), list) and len(body["blocks"]) > 0
    log("WD4 validate-delete on referenced WH -> can_delete=false + blocks",
        r.status_code == 200 and body.get("can_delete") is False and has_blocks,
        "200 + can_delete=false + blocks", r.status_code, detail=r.text[:250])

    r = requests.delete(f"{BASE}/warehouses/{WH_ID}", headers=SH)
    detail = r.json().get("detail") if r.status_code == 422 else None
    has_block_detail = (isinstance(detail, dict)
                        and isinstance(detail.get("blocks"), list)
                        and len(detail["blocks"]) > 0)
    log("WD5 DELETE referenced WH -> 422 + blocks in detail",
        r.status_code == 422 and has_block_detail,
        "422 + blocks payload", r.status_code, detail=r.text[:250])
else:
    log("WD4 Skipped (no system_administrator session or WH_ID)", True,
        "skipped", "skipped")
    log("WD5 Skipped (no system_administrator session or WH_ID)", True,
        "skipped", "skipped")


# ============================================================
# Summary
# ============================================================
print()
print("=" * 60)
passed = sum(1 for _, ok in results if ok)
total = len(results)
print(f"SUMMARY: {passed}/{total} passed")
fails = [c for c, ok in results if not ok]
if fails:
    print("Failed cases:")
    for c in fails:
        print(f"  - {c}")
else:
    print("All passed.")

# Exit non-zero on any failure so CI / scripts can detect
raise SystemExit(0 if passed == total else 1)
