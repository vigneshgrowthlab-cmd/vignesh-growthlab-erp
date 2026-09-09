"""Retry S3, S4 with correct payload and run authorization tests."""
import requests
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

# Admin login
r = requests.post(f"{BASE}/auth/login", json={"username": "admin", "password": "Admin@1234"})
ADMIN_TOKEN = r.json()["access_token"]
AH = {"Authorization": f"Bearer {ADMIN_TOKEN}"}

# Find product
prods = requests.get(f"{BASE}/products/?search=Smoke", headers=AH).json().get("items", [])
PROD_ID = prods[0]["id"] if prods else None

warehouses = requests.get(f"{BASE}/warehouses/", headers=AH).json()
WH_ID = warehouses["items"][0]["id"] if isinstance(warehouses, dict) else warehouses[0]["id"]

# ===== Stock retry with correct payload =====
print("=== Stock (retry with proper payload) ===")
today = date.today().isoformat()
payload = {
    "product_id": PROD_ID, "warehouse_id": WH_ID,
    "adjustment_type": "out", "quantity": 5,
    "reason": "Smoke test adjustment - sufficient stock",
    "adjustment_date": today,
}
r = requests.post(f"{BASE}/stock-adjustments/", json=payload, headers=AH)
log("S3  Adjust OUT (sufficient)", r.status_code in (200, 201), "200/201", r.status_code,
    detail=r.text[:300])

payload2 = {
    "product_id": PROD_ID, "warehouse_id": WH_ID,
    "adjustment_type": "out", "quantity": 99999999,
    "reason": "Smoke test adjustment - overflow",
    "adjustment_date": today,
}
r = requests.post(f"{BASE}/stock-adjustments/", json=payload2, headers=AH)
ok = r.status_code == 400 and "Insufficient stock" in r.text
log("S4  Adjust OUT > available (Insufficient stock)", ok, "400 + 'Insufficient stock'",
    r.status_code, detail=r.text[:200] if not ok else "")

# ===== Authorization =====
print()
print("=== Authorization ===")

# List users to find sales / accountant usernames
users_data = requests.get(f"{BASE}/users/", headers=AH).json()
users_list = users_data if isinstance(users_data, list) else users_data.get("items", [])
sales = next((u for u in users_list if u.get("role") == "sales"), None)
acct = next((u for u in users_list if u.get("role") == "accountant"), None)
print(f"  sales: {sales.get('username') if sales else None}, accountant: {acct.get('username') if acct else None}")

# Try logging in as them with default password Admin@1234 (likely works if seed-created)
def try_login(username, pw="Admin@1234"):
    r = requests.post(f"{BASE}/auth/login", json={"username": username, "password": pw})
    if r.status_code == 200:
        return r.json()["access_token"]
    return None

sales_tok = None
acct_tok = None
if sales:
    sales_tok = try_login(sales["username"])
    if not sales_tok:
        # Try a common alternate password
        sales_tok = try_login(sales["username"], "Sales@1234")
if acct:
    acct_tok = try_login(acct["username"])
    if not acct_tok:
        acct_tok = try_login(acct["username"], "Accountant@1234")

if sales_tok:
    SH = {"Authorization": f"Bearer {sales_tok}"}
    # AZ1: sales lists products, purchase_cost hidden
    r = requests.get(f"{BASE}/products/?page_size=5", headers=SH)
    items = r.json().get("items", []) if r.status_code == 200 else []
    has_cost = any("purchase_cost" in it for it in items)
    log("AZ1 Sales user lists products w/o purchase_cost",
        r.status_code == 200 and not has_cost,
        "200 + no purchase_cost", f"{r.status_code} + has_cost={has_cost}")

    # AZ2: sales gets product detail without purchase_cost/profit
    r = requests.get(f"{BASE}/products/{PROD_ID}", headers=SH)
    b = r.json() if r.status_code == 200 else {}
    hidden = {"purchase_cost", "profit_percent", "profit_value"}
    leak = [k for k in hidden if k in b]
    log("AZ2 Sales gets product detail w/o purchase fields",
        r.status_code == 200 and not leak,
        "200 + no leaked fields", f"{r.status_code} + leaked={leak}")

    # AZ3: sales tries to create product
    r = requests.post(f"{BASE}/products/", json={
        "part_name": "AZ3-sales", "category_id": 1,
        "purchase_cost": 1, "b2b_price": 1, "b2c_price": 1, "mrp": 1, "floor_price": 1
    }, headers=SH)
    log("AZ3 Sales cannot create product", r.status_code == 403, 403, r.status_code,
        detail=r.text[:120])
else:
    print("  Skipping AZ1/AZ2/AZ3 - couldn't log in as sales user")

if acct_tok:
    AccH = {"Authorization": f"Bearer {acct_tok}"}
    # AZ4: accountant accesses cost trend
    r = requests.get(f"{BASE}/products/{PROD_ID}/cost-trend", headers=AccH)
    log("AZ4 Accountant accesses cost trend", r.status_code == 200, 200, r.status_code,
        detail=r.text[:120])
else:
    print("  Skipping AZ4 - couldn't log in as accountant user")

print()
print("=" * 60)
passed = sum(1 for _, ok in results if ok)
failed = sum(1 for _, ok in results if not ok)
print(f"Retry+AZ total: {passed}/{len(results)} passed, {failed} failed")
