"""Ad-hoc verification of the Tier B Purchase-module changes.
Not a persistent smoke — meant to be run once and inspected, then deleted
or folded into test_purchase_module.py."""
import requests, time

BASE = "http://localhost:8000/api/v1"

# Tolerate uvicorn --reload kicking in between edits and this run.
for _ in range(5):
    try:
        r = requests.post(f"{BASE}/auth/login",
                          json={"username": "admin", "password": "Admin@1234"},
                          timeout=4)
        if r.status_code == 200:
            T = r.json()["access_token"]
            break
    except requests.RequestException:
        pass
    time.sleep(1.5)
else:
    raise SystemExit("Could not reach backend after retries")
H = {"Authorization": f"Bearer {T}"}

results = []
def log(name, ok, detail=""):
    tag = "PASS" if ok else "FAIL"
    print(f"[{tag}] {name}" + (f"  | {detail}" if detail else ""))
    results.append(ok)

VENDOR_ID = 1       # VND1, state_code=33 after backfill
WAREHOUSE_ID = 2
PROD_ID = 14        # smoke product

# ─── A: cancel reversal on unconsumed purchase ───────────────
print("\n=== A: Create + immediate cancel (no consumption) ===")
r = requests.post(f"{BASE}/purchases/", headers=H, json={
    "vendor_id": VENDOR_ID, "warehouse_id": WAREHOUSE_ID,
    "vendor_invoice_number": "CANCEL-SMOKE-A",
    "invoice_date": "2026-05-20",
    "items": [{"product_id": PROD_ID, "quantity": 3, "unit_cost": 100,
               "gst_percent": 18, "hsn_code": "1234"}],
})
assert r.status_code == 201, r.text
pur = r.json()
PUR_ID = pur["id"]
log("A1 purchase created", True,
    f"id={PUR_ID} total={pur['total_amount']}")

stk_before = requests.get(f"{BASE}/products/{PROD_ID}",
                          headers=H).json().get("total_stock", 0)
log("A2 stock present before cancel", stk_before >= 3,
    f"total_stock={stk_before}")

c = requests.post(f"{BASE}/purchases/{PUR_ID}/cancel", headers=H)
log("A3 cancel returned 200", c.status_code == 200, c.text[:200])

stk_after = requests.get(f"{BASE}/products/{PROD_ID}",
                         headers=H).json().get("total_stock", 0)
log("A4 stock decremented by 3",
    abs((stk_before - stk_after) - 3) < 0.001,
    f"before={stk_before} after={stk_after}")

pur_now = requests.get(f"{BASE}/purchases/{PUR_ID}", headers=H).json()
log("A5 is_cancelled=True", pur_now["is_cancelled"] is True)

again = requests.post(f"{BASE}/purchases/{PUR_ID}/cancel", headers=H)
log("A6 second cancel rejected",
    again.status_code == 400 and "already" in again.text.lower(),
    again.text[:120])

# ─── B: cancel blocked when stock consumed ──────────────────
print("\n=== B: Cancel blocked when stock consumed ===")
r = requests.post(f"{BASE}/purchases/", headers=H, json={
    "vendor_id": VENDOR_ID, "warehouse_id": WAREHOUSE_ID,
    "vendor_invoice_number": "CANCEL-SMOKE-B",
    "invoice_date": "2026-05-20",
    "items": [{"product_id": PROD_ID, "quantity": 5, "unit_cost": 100,
               "gst_percent": 18, "hsn_code": "1234"}],
})
PUR2_ID = r.json()["id"]
log("B1 second purchase created", True, f"id={PUR2_ID}")

adj = requests.post(f"{BASE}/stock-adjustments/", headers=H, json={
    "product_id": PROD_ID, "warehouse_id": WAREHOUSE_ID,
    "adjustment_type": "out", "quantity": 2,
    "adjustment_date": "2026-05-21", "reason": "smoke consumption"
})
log("B2 consumed 2 units",
    adj.status_code in (200, 201), adj.text[:120])

blk = requests.post(f"{BASE}/purchases/{PUR2_ID}/cancel", headers=H)
ok = blk.status_code == 400 and "consumed" in blk.text.lower()
log("B3 cancel blocked on consumed stock", ok, blk.text[:250])

# ─── C: vendor payment void ─────────────────────────────────
print("\n=== C: Vendor payment void ===")
r = requests.post(f"{BASE}/purchases/", headers=H, json={
    "vendor_id": VENDOR_ID, "warehouse_id": WAREHOUSE_ID,
    "vendor_invoice_number": "PAY-SMOKE-C",
    "invoice_date": "2026-05-20",
    "items": [{"product_id": PROD_ID, "quantity": 1, "unit_cost": 500,
               "gst_percent": 18, "hsn_code": "1234"}],
})
created3 = r.json()
PUR3_ID = created3["id"]
TOTAL3 = float(created3["total_amount"])
log("C1 purchase for payment", True, f"id={PUR3_ID} total={TOTAL3}")

pay = requests.post(f"{BASE}/vendor-payments/", headers=H, json={
    "vendor_id": VENDOR_ID, "purchase_id": PUR3_ID,
    "payment_date": "2026-05-21", "amount": TOTAL3, "payment_mode": "cash"
})
assert pay.status_code == 201, pay.text
PAY_ID = pay.json()["id"]
log("C2 payment created", True,
    f"id={PAY_ID} amount={pay.json()['amount']}")

p_paid = requests.get(
    f"{BASE}/purchases/?vendor_id={VENDOR_ID}&page_size=50", headers=H
).json()
hit = next((x for x in p_paid["items"] if x["id"] == PUR3_ID), None)
log("C3 purchase outstanding=0 after payment",
    hit and hit["outstanding_amount"] < 0.01,
    f"outstanding={hit['outstanding_amount'] if hit else 'missing'}")

void = requests.delete(f"{BASE}/vendor-payments/{PAY_ID}", headers=H)
log("C4 void DELETE returned 200",
    void.status_code == 200, void.text[:200])

listed = requests.get(
    f"{BASE}/vendor-payments/?vendor_id={VENDOR_ID}&page_size=100", headers=H
).json()
hidden = not any(x["id"] == PAY_ID for x in listed["items"])
log("C5 default list excludes voided", hidden,
    f"items={len(listed['items'])}")

listed2 = requests.get(
    f"{BASE}/vendor-payments/?vendor_id={VENDOR_ID}&include_voided=true&page_size=100",
    headers=H
).json()
shown = next((x for x in listed2["items"] if x["id"] == PAY_ID), None)
log("C6 include_voided shows it w/ is_void flag",
    shown and shown.get("is_void") is True,
    f"is_void={shown.get('is_void') if shown else 'missing'}")

p_after = requests.get(
    f"{BASE}/purchases/?vendor_id={VENDOR_ID}&page_size=50", headers=H
).json()
hit2 = next((x for x in p_after["items"] if x["id"] == PUR3_ID), None)
log("C7 purchase outstanding restored after void",
    hit2 and abs(hit2["outstanding_amount"] - TOTAL3) < 0.01,
    f"outstanding={hit2['outstanding_amount'] if hit2 else 'missing'} expected={TOTAL3}")

twice = requests.delete(f"{BASE}/vendor-payments/{PAY_ID}", headers=H)
log("C8 double void rejected",
    twice.status_code == 400, twice.text[:150])

blocked_pay = requests.post(f"{BASE}/vendor-payments/", headers=H, json={
    "vendor_id": VENDOR_ID, "purchase_id": PUR_ID,
    "payment_date": "2026-05-22", "amount": 10, "payment_mode": "cash"
})
log("C9 payment against cancelled purchase blocked",
    blocked_pay.status_code == 400 and "cancel" in blocked_pay.text.lower(),
    blocked_pay.text[:200])

# ─── Summary ────────────────────────────────────────────────
passed = sum(results)
total = len(results)
print("\n" + "=" * 50)
print(f"Total: {passed}/{total} passed, {total - passed} failed")
