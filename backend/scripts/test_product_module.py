"""Product module - remaining 24 use cases.
Run from backend/ with venv activated."""
import requests, time

BASE = "http://localhost:8000/api/v1"
results = []

def log(case, ok, expected, actual, detail=""):
    tag = "[PASS]" if ok else "[FAIL]"
    msg = f"{tag} {case}: expected={expected} actual={actual}"
    if detail and not ok:
        msg += f" | {detail}"
    print(msg)
    results.append((case, ok))

# Login
r = requests.post(f"{BASE}/auth/login", json={"username": "admin", "password": "Admin@1234"})
TOKEN = r.json()["access_token"]
H = {"Authorization": f"Bearer {TOKEN}"}

# Reuse smoke artefacts
cats = requests.get(f"{BASE}/categories/", headers=H).json()
CAT_ID = next((c["id"] for c in cats if c["prefix"] == "ZTST"), None)
prods = requests.get(f"{BASE}/products/?search=Smoke", headers=H).json().get("items", [])
PROD_ID = prods[0]["id"] if prods else None
print(f"Using category id={CAT_ID}, product id={PROD_ID}")
print()

# ===== Categories - Positive =====
print("=== Categories - Positive ===")
r = requests.get(f"{BASE}/categories/", headers=H)
log("C2  List categories", r.status_code == 200 and isinstance(r.json(), list), "200 + list", r.status_code)

r = requests.get(f"{BASE}/categories/{CAT_ID}", headers=H)
log("C3  Get category by ID", r.status_code == 200 and r.json().get("prefix") == "ZTST", "200 + prefix=ZTST", r.status_code)

r = requests.put(f"{BASE}/categories/{CAT_ID}", json={"description": "Updated by C4"}, headers=H)
log("C4  Update category partial", r.status_code == 200, 200, r.status_code)

print()
print("=== Categories - Negative ===")
r = requests.post(f"{BASE}/categories/", json={"name": "NoPrefix"}, headers=H)
log("C5  Cat missing prefix", r.status_code == 422, 422, r.status_code, detail=r.text[:120])

r = requests.post(f"{BASE}/categories/", json={"name": "DupZ", "prefix": "ztst"}, headers=H)
log("C6  Duplicate prefix case-insensitive", r.status_code == 400, 400, r.status_code, detail=r.text[:150])

r = requests.get(f"{BASE}/categories/999999", headers=H)
log("C8  Get cat non-existent", r.status_code == 404, 404, r.status_code)

r = requests.delete(f"{BASE}/categories/{CAT_ID}", headers=H)
log("C9  Delete cat with products blocked", r.status_code == 400, 400, r.status_code, detail=r.text[:120])

# ===== Products - Positive remainder =====
print()
print("=== Products - Positive ===")
r = requests.get(f"{BASE}/products/?page=1&page_size=5", headers=H)
d = r.json()
log("P2  List paginated", r.status_code == 200 and "items" in d and "total" in d, "200 + paginated", r.status_code)

r = requests.get(f"{BASE}/products/?search=Smoke", headers=H)
d = r.json()
log("P3  List with search", r.status_code == 200 and len(d.get("items", [])) >= 1, "200 + matches", r.status_code)

r = requests.get(f"{BASE}/products/?low_stock_only=true", headers=H)
log("P4  Low stock only", r.status_code == 200, 200, r.status_code,
    detail=f"items={len(r.json().get('items', []))}")

r = requests.get(f"{BASE}/products/{PROD_ID}", headers=H)
body = r.json()
need = {"profit_percent", "profit_value", "total_stock"}
log("P5  Get product detail w/ profit fields",
    r.status_code == 200 and need.issubset(body.keys() if isinstance(body, dict) else set()),
    "200 + profit fields", r.status_code)

print()
print("=== Products - Negative ===")
r = requests.post(f"{BASE}/products/", json={
    "part_name": "Bad", "category_id": CAT_ID, "hsn_code": "ABCD",
    "purchase_cost": 1, "b2b_price": 1, "b2c_price": 1, "mrp": 1, "floor_price": 1
}, headers=H)
log("P7  HSN non-numeric", r.status_code == 422, 422, r.status_code, detail=r.text[:120])

r = requests.post(f"{BASE}/products/", json={
    "part_name": "BadGST", "category_id": CAT_ID, "gst_percent": 150,
    "purchase_cost": 1, "b2b_price": 1, "b2c_price": 1, "mrp": 1, "floor_price": 1
}, headers=H)
log("P8  gst_percent > 100", r.status_code == 422, 422, r.status_code, detail=r.text[:120])

r = requests.post(f"{BASE}/products/", json={
    "part_name": "OrphanCat", "category_id": 999999,
    "purchase_cost": 1, "b2b_price": 1, "b2c_price": 1, "mrp": 1, "floor_price": 1
}, headers=H)
log("P9  Non-existent category_id", r.status_code == 404, 404, r.status_code, detail=r.text[:120])

r = requests.get(f"{BASE}/products/999999", headers=H)
log("P10 Get product non-existent", r.status_code == 404, 404, r.status_code)

# ===== Bulk Upload =====
print()
print("=== Bulk Upload ===")
csv1 = ("part_name,category_prefix,hsn_code,gst_percent,purchase_cost,b2b_price,floor_price\n"
        "BU1A,ZTST,851620,18,100,110,105\nBU1B,ZTST,851620,18,200,220,210\n")
r = requests.post(f"{BASE}/products/bulk-upload",
                  files={"file": ("bu1.csv", csv1, "text/csv")}, headers=H)
body = r.json()
ok = r.status_code == 200 and body.get("success_count") == 2 and body.get("error_count") == 0
log("BU1 All-valid CSV", ok, "200 sc=2 ec=0",
    f"{r.status_code} sc={body.get('success_count')} ec={body.get('error_count')}")

csv3 = ("part_name,category_prefix,hsn_code,gst_percent,purchase_cost,b2b_price,floor_price\n"
        "BU3Bad,ZTST,123,18,100,110,105\n")
r = requests.post(f"{BASE}/products/bulk-upload",
                  files={"file": ("bu3.csv", csv3, "text/csv")}, headers=H)
body = r.json()
err_msg = ""
if body.get("errors"):
    err_msg = body["errors"][0].get("errors", [""])[0]
ok = r.status_code == 200 and body.get("error_count") == 1 and "4, 6, or 8" in err_msg
log("BU3 Invalid HSN row", ok, "200 1 err with 4/6/8 message",
    f"{r.status_code} ec={body.get('error_count')}", detail=f"msg='{err_msg[:80]}'" if not ok else "")

r = requests.post(f"{BASE}/products/bulk-upload",
                  files={"file": ("test.txt", "not csv", "text/plain")}, headers=H)
log("BU4 Non-CSV file rejected", r.status_code == 400, 400, r.status_code)

csv5 = "part_name,category_prefix,hsn_code,gst_percent,purchase_cost,b2b_price,floor_price\n"
r = requests.post(f"{BASE}/products/bulk-upload",
                  files={"file": ("bu5.csv", csv5, "text/csv")}, headers=H)
body = r.json()
log("BU5 Empty CSV header-only",
    r.status_code == 200 and body.get("success_count") == 0 and body.get("error_count") == 0,
    "200 sc=0 ec=0",
    f"{r.status_code} sc={body.get('success_count')} ec={body.get('error_count')}")

# Oversized (~12 MB)
header = "part_name,category_prefix,hsn_code,gst_percent,purchase_cost,b2b_price,floor_price\n"
row = "BU6Big" + "x" * 200 + ",ZTST,851620,18,100,110,105\n"
big = header + row * 60000
r = requests.post(f"{BASE}/products/bulk-upload",
                  files={"file": ("big.csv", big, "text/csv")}, headers=H)
log("BU6 Oversized > 10MB", r.status_code == 413, 413, r.status_code, detail=r.text[:120])

# ===== Stock remainder =====
print()
print("=== Stock ===")
r = requests.get(f"{BASE}/products/{PROD_ID}/stock", headers=H)
log("S1  Get product stock per-warehouse",
    r.status_code == 200 and isinstance(r.json(), list), "200 + list", r.status_code)

warehouses = requests.get(f"{BASE}/warehouses/", headers=H).json()
WH_ID = warehouses["items"][0]["id"] if isinstance(warehouses, dict) else warehouses[0]["id"]

r = requests.post(f"{BASE}/stock-adjustments/", json={
    "product_id": PROD_ID, "warehouse_id": WH_ID,
    "adjustment_type": "out", "quantity": 10, "reason": "S3"
}, headers=H)
log("S3  Adjust OUT via /stock-adjustments/", r.status_code in (200, 201), "200/201", r.status_code,
    detail=r.text[:200])

r = requests.post(f"{BASE}/stock-adjustments/", json={
    "product_id": PROD_ID, "warehouse_id": WH_ID,
    "adjustment_type": "out", "quantity": 999999, "reason": "S4"
}, headers=H)
ok = r.status_code == 400 and "Insufficient stock" in r.text
log("S4  Adjust OUT > available", ok, "400 'Insufficient stock'", r.status_code,
    detail=r.text[:200] if not ok else "")

# ===== Alerts =====
print()
print("=== Alerts ===")
# Reset
requests.put(f"{BASE}/products/{PROD_ID}",
             json={"purchase_cost": 50, "cost_alert_threshold_pct": 5,
                   "b2b_price": 100, "min_margin_pct": 10},
             headers=H)
time.sleep(0.2)

# Bump cost by 200% (well above 5% threshold)
requests.put(f"{BASE}/products/{PROD_ID}", json={"purchase_cost": 200}, headers=H)
time.sleep(0.2)
alerts = requests.get(f"{BASE}/products/alerts/pending", headers=H).json()
rise = [a for a in alerts if a.get("product_id") == PROD_ID and a.get("alert_type") == "cost_rise"]
log("AL1 Cost rise alert created", len(rise) > 0, ">=1 cost_rise", f"{len(rise)} found")

# AL2: b2b-only change triggers margin alert
requests.put(f"{BASE}/products/{PROD_ID}",
             json={"purchase_cost": 100, "b2b_price": 200, "min_margin_pct": 50},
             headers=H)
time.sleep(0.2)
# Drop b2b only - margin = (90-100)/100 = -10% < 50%
requests.put(f"{BASE}/products/{PROD_ID}", json={"b2b_price": 90}, headers=H)
time.sleep(0.2)
alerts = requests.get(f"{BASE}/products/alerts/pending", headers=H).json()
margin = [a for a in alerts if a.get("product_id") == PROD_ID and a.get("alert_type") == "low_margin"]
log("AL2 Margin alert on b2b-only change (Fix #6)",
    len(margin) > 0, ">=1 low_margin", f"{len(margin)} found")

r = requests.get(f"{BASE}/products/alerts/pending", headers=H)
log("AL3 List pending alerts", r.status_code == 200 and isinstance(r.json(), list), "200 list", r.status_code)

# ===== Authorization (check user existence first) =====
print()
print("=== Authorization (best-effort) ===")
r_users = requests.get(f"{BASE}/users/", headers=H)
users_data = r_users.json() if r_users.status_code == 200 else []
users_list = users_data if isinstance(users_data, list) else users_data.get("items", [])

sales_user = next((u for u in users_list if u.get("role") == "sales"), None)
accountant_user = next((u for u in users_list if u.get("role") == "accountant"), None)

print(f"  Sales user found: {bool(sales_user)}, Accountant found: {bool(accountant_user)}")

# Sumary
print()
print("=" * 60)
passed = sum(1 for _, ok in results if ok)
failed = sum(1 for _, ok in results if not ok)
print(f"Total: {passed}/{len(results)} passed, {failed} failed")
if failed:
    print("\nFailed cases:")
    for c, ok in results:
        if not ok:
            print(f"  - {c}")
