"""
seed_railway_demo.py - ASCII-only for Windows console
"""
import urllib.request
import urllib.error
import json

BASE = "https://vignesh-growthlab-erp-production-2955.up.railway.app/api/v1"

def api_call(method, path, data=None, token=None):
    url = f"{BASE}{path}"
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8")
            return json.loads(content) if content else {}
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8") if e.fp else ""
        print(f"  [ERR] {method} {path} -> {e.code}: {err[:200]}")
        return None
    except Exception as ex:
        print(f"  [ERR] {method} {path} -> {ex}")
        return None

def main():
    print("=== Seeding Demo Data on Railway ===")
    
    # 1. Login
    login_res = api_call("POST", "/auth/login", {"username": "admin", "password": "Admin@1234"})
    if not login_res or "access_token" not in login_res:
        print("Login failed!")
        return
    token = login_res["access_token"]
    print("[OK] Successfully authenticated as super_admin")

    # 2. Categories
    categories_data = [
        {"name": "Chargers & Adapters", "prefix": "CHG", "default_hsn": "85044090", "default_gst_percent": 18},
        {"name": "USB & Fast Cables", "prefix": "CBL", "default_hsn": "85444299", "default_gst_percent": 18},
        {"name": "Audio & Bluetooth", "prefix": "AUD", "default_hsn": "85183000", "default_gst_percent": 18},
        {"name": "Tempered Glass & Guards", "prefix": "GLS", "default_hsn": "70071900", "default_gst_percent": 18},
        {"name": "Cases & Back Covers", "prefix": "COV", "default_hsn": "39269099", "default_gst_percent": 18},
        {"name": "Power Banks", "prefix": "PWR", "default_hsn": "85044090", "default_gst_percent": 18},
    ]

    cat_map = {}
    existing_cats = api_call("GET", "/categories/", token=token) or []
    for c in existing_cats:
        cat_map[c["name"]] = c["id"]

    for c in categories_data:
        if c["name"] not in cat_map:
            res = api_call("POST", "/categories/", c, token=token)
            if res and "id" in res:
                cat_map[c["name"]] = res["id"]
                print(f"  [OK] Category created: {c['name']} (ID: {res['id']})")
        else:
            print(f"  - Category exists: {c['name']}")

    # 3. Products
    products_data = [
        {"part_name": "65W GaN Fast Charger Type-C", "category": "Chargers & Adapters", "hsn_code": "85044090", "gst_percent": 18, "purchase_cost": 450, "b2b_price": 580, "b2c_price": 750, "mrp": 999, "floor_price": 520, "low_stock_threshold": 10},
        {"part_name": "20W PD iPhone Fast Adapter", "category": "Chargers & Adapters", "hsn_code": "85044090", "gst_percent": 18, "purchase_cost": 220, "b2b_price": 310, "b2c_price": 420, "mrp": 599, "floor_price": 280, "low_stock_threshold": 15},
        {"part_name": "Braided Type-C to Type-C 60W (1.5m)", "category": "USB & Fast Cables", "hsn_code": "85444299", "gst_percent": 18, "purchase_cost": 65, "b2b_price": 110, "b2c_price": 160, "mrp": 249, "floor_price": 95, "low_stock_threshold": 25},
        {"part_name": "USB to Lightning Fast Cable (1m)", "category": "USB & Fast Cables", "hsn_code": "85444299", "gst_percent": 18, "purchase_cost": 55, "b2b_price": 95, "b2c_price": 140, "mrp": 199, "floor_price": 80, "low_stock_threshold": 30},
        {"part_name": "Wireless TWS Earbuds ENC Bass", "category": "Audio & Bluetooth", "hsn_code": "85183000", "gst_percent": 18, "purchase_cost": 480, "b2b_price": 690, "b2c_price": 899, "mrp": 1299, "floor_price": 620, "low_stock_threshold": 10},
        {"part_name": "Neckband Magnetic Bluetooth Earphones", "category": "Audio & Bluetooth", "hsn_code": "85183000", "gst_percent": 18, "purchase_cost": 290, "b2b_price": 420, "b2c_price": 550, "mrp": 799, "floor_price": 380, "low_stock_threshold": 12},
        {"part_name": "Super D 9H Matte Tempered Glass", "category": "Tempered Glass & Guards", "hsn_code": "70071900", "gst_percent": 18, "purchase_cost": 18, "b2b_price": 45, "b2c_price": 99, "mrp": 149, "floor_price": 35, "low_stock_threshold": 50},
        {"part_name": "Privacy Anti-Spy Tempered Glass", "category": "Tempered Glass & Guards", "hsn_code": "70071900", "gst_percent": 18, "purchase_cost": 32, "b2b_price": 65, "b2c_price": 130, "mrp": 199, "floor_price": 55, "low_stock_threshold": 40},
        {"part_name": "Shockproof Clear Hybrid Armor Case", "category": "Cases & Back Covers", "hsn_code": "39269099", "gst_percent": 18, "purchase_cost": 45, "b2b_price": 85, "b2c_price": 149, "mrp": 199, "floor_price": 75, "low_stock_threshold": 25},
        {"part_name": "10000mAh 22.5W Fast Pocket Power Bank", "category": "Power Banks", "hsn_code": "85044090", "gst_percent": 18, "purchase_cost": 620, "b2b_price": 840, "b2c_price": 1099, "mrp": 1499, "floor_price": 780, "low_stock_threshold": 8},
    ]

    prod_resp = api_call("GET", "/products/", token=token) or {}
    existing_prods = prod_resp.get("items", []) if isinstance(prod_resp, dict) else prod_resp
    existing_part_names = {p["part_name"] for p in existing_prods if isinstance(p, dict)}

    for p in products_data:
        if p["part_name"] not in existing_part_names:
            cat_id = cat_map.get(p["category"])
            if not cat_id:
                continue
            payload = {
                "part_name": p["part_name"],
                "category_id": cat_id,
                "hsn_code": p["hsn_code"],
                "gst_percent": p["gst_percent"],
                "purchase_cost": p["purchase_cost"],
                "b2b_price": p["b2b_price"],
                "b2c_price": p["b2c_price"],
                "mrp": p["mrp"],
                "floor_price": p["floor_price"],
                "unit_of_measure": "Nos",
                "low_stock_threshold": p["low_stock_threshold"],
            }
            res = api_call("POST", "/products/", payload, token=token)
            if res and "id" in res:
                print(f"  [OK] Product created: {p['part_name']} (SKU: {res.get('sku')})")
        else:
            print(f"  - Product exists: {p['part_name']}")

    # 4. Customers
    cust_data = [
        {"name": "Sri Agni Mobiles", "trade_name": "Sri Agni Mobiles Retail Branch", "phone": "9842100001", "email": "retail@agnimobiles.com", "is_b2b": True, "gstin": "33AABCS1429B1Z8", "credit_limit": 50000, "credit_days": 15},
        {"name": "Pollachi Tech Point", "trade_name": "Pollachi Tech Point", "phone": "9842100002", "email": "sales@pollachiteck.in", "is_b2b": True, "gstin": "33AAECP1122C1Z4", "credit_limit": 30000, "credit_days": 10},
        {"name": "Kovai Mobile Zone", "trade_name": "Kovai Mobile Zone", "phone": "9842100003", "email": "kovaimobilezone@gmail.com", "is_b2b": False, "credit_limit": 10000, "credit_days": 0},
    ]
    for c in cust_data:
        res = api_call("POST", "/customers/", c, token=token)
        if res and "id" in res:
            print(f"  [OK] Customer created: {c['name']} (ID: {res['id']})")

    # 5. Vendors
    vendor_data = [
        {"name": "Tamilnadu Mobile Accessories Hub", "trade_name": "Tamilnadu Mobile Accessories Hub", "contact_person": "Karthik Raja", "phone": "9840011223", "email": "karthik@tnmobilehub.com", "gstin": "33AADCT5566D1Z1", "state": "Tamil Nadu", "state_code": 33},
        {"name": "Bangalore Impex Electronics", "trade_name": "Bangalore Impex Electronics", "contact_person": "Suresh Babu", "phone": "9880044556", "email": "orders@bangaloreimpex.com", "gstin": "29AABCB3344E1Z5", "state": "Karnataka", "state_code": 29},
    ]
    for v in vendor_data:
        res = api_call("POST", "/vendors/", v, token=token)
        if res and "id" in res:
            print(f"  [OK] Vendor created: {v['name']} (ID: {res['id']})")

    print("\n=== Demo Data Seeding Complete! ===")

if __name__ == "__main__":
    main()
